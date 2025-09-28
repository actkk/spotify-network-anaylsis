from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple

from selenium.webdriver.remote.webdriver import WebDriver

from spotify_graph.config import Settings, get_settings
from spotify_graph.logging import get_logger
from spotify_graph.models.profile import Profile, Relationship
from spotify_graph.crawlers.profile_page import ProfilePageScraper
from spotify_graph.storage.repository import GraphRepository

LOGGER = get_logger(__name__)


class SpotifyGraphCrawler:
    """Breadth-first traversal of the Spotify social graph via Selenium."""

    def __init__(
        self,
        driver: WebDriver,
        *,
        repository: Optional[GraphRepository] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.driver = driver
        self.repository = repository or GraphRepository()
        self.settings = settings or get_settings()
        self.scraper = ProfilePageScraper(driver, settings=self.settings)

    def crawl(self, root_profile: str, max_depth: Optional[int] = None) -> None:
        depth_limit = max_depth or self.settings.crawl_max_depth
        LOGGER.info("Starting crawl at %s (depth=%d)", root_profile, depth_limit)

        queue: Deque[Tuple[str, int]] = deque([(root_profile, 0)])
        visited: Set[str] = set()
        queued: Set[str] = {root_profile}

        while queue:
            profile_id, depth = queue.popleft()
            if profile_id in visited:
                continue
            visited.add(profile_id)

            if depth > depth_limit:
                LOGGER.debug("Skipping %s because depth %d exceeds limit", profile_id, depth)
                continue

            cached_profile = self.repository.find_profile(profile_id)
            if cached_profile and cached_profile.followers_fetch_attempted:
                profile = cached_profile
                profile.last_seen_at = datetime.utcnow()
                if cached_profile.followers_fetched:
                    followers = self.repository.get_followers(profile_id)
                    connections = {"followers": followers}
                else:
                    connections = {}
                LOGGER.debug(
                    "Using cached data for %s (followers fetched=%s)",
                    profile_id,
                    cached_profile.followers_fetched,
                )
            else:
                try:
                    profile, connections = self.fetch_profile(profile_id)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.error("Failed to fetch profile %s: %s", profile_id, exc)
                    if cached_profile:
                        profile = cached_profile
                        connections = {}
                    else:
                        continue

            if profile.followers and profile.followers >= self.settings.follower_threshold:
                LOGGER.info(
                    "Skipping %s due to follower threshold (%d >= %d)",
                    profile_id,
                    profile.followers,
                    self.settings.follower_threshold,
                )
                continue

            self.repository.upsert_profile(profile)

            edges_to_add: List[Relationship] = []
            for relation, neighbors in connections.items():
                for neighbor in neighbors:
                    if neighbor.followers and neighbor.followers >= self.settings.follower_threshold:
                        LOGGER.debug("Omitting neighbor %s due to follower threshold", neighbor.id)
                        continue

                    self.repository.upsert_profile(neighbor)

                    if relation == "following":
                        edge = Relationship(
                            source_id=profile.id,
                            target_id=neighbor.id,
                            relation_type="following",
                        )
                        next_id = neighbor.id
                    else:  # followers
                        edge = Relationship(
                            source_id=neighbor.id,
                            target_id=profile.id,
                            relation_type="follower",
                        )
                        next_id = neighbor.id

                    edges_to_add.append(edge)

                    if depth + 1 <= depth_limit and next_id not in visited and next_id not in queued:
                        queue.append((next_id, depth + 1))
                        queued.add(next_id)

            if edges_to_add:
                self.repository.bulk_add_edges(edges_to_add)
            self.repository.persist()

    def fetch_profile(self, profile_id: str) -> Tuple[Profile, Dict[str, List[Profile]]]:
        """Navigate to a profile page and return metadata plus connections."""
        profile = self.scraper.fetch_profile_overview(profile_id)
        profile.last_seen_at = datetime.utcnow()
        existing = self.repository.find_profile(profile_id)
        if existing:
            profile.followers_fetch_attempted = existing.followers_fetch_attempted
            profile.followers_fetched = existing.followers_fetched
            profile.followers_oversized = existing.followers_oversized
        connections: Dict[str, List[Profile]] = {}

        follower_limit = self.settings.followers_download_limit
        if (
            profile.followers is not None
            and follower_limit
            and profile.followers >= follower_limit
        ):
            profile.followers_fetch_attempted = True
            profile.followers_oversized = True
            LOGGER.info(
                "Skipping follower fetch for %s due to size limit (%d >= %d)",
                profile_id,
                profile.followers,
                follower_limit,
            )
            return profile, connections

        if profile.is_private:
            profile.followers_fetch_attempted = True
            LOGGER.debug("Profile %s marked as private; skipping connections", profile_id)
            return profile, connections

        for relation in ("followers",):
            try:
                expected_count = profile.followers if relation == "followers" else None
                neighbors, accessible = self.scraper.fetch_connections(
                    profile_id,
                    relation,
                    expected_count=expected_count,
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Error while fetching %s for %s: %s", relation, profile_id, exc)
                continue

            if not accessible:
                LOGGER.debug("%s list for %s not accessible", relation, profile_id)
                profile.is_private = True
                profile.followers_fetch_attempted = True
                break

            profile.followers_fetch_attempted = True
            if relation == "followers":
                profile.followers_fetched = True

            if neighbors:
                connections[relation] = neighbors

        if not connections and not profile.followers_oversized:
            LOGGER.debug("No follower connections recorded for %s", profile_id)

        return profile, connections


__all__ = ["SpotifyGraphCrawler"]
