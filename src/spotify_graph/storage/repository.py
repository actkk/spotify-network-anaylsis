from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from spotify_graph.logging import get_logger
from spotify_graph.models.profile import Profile, Relationship
from spotify_graph.storage.json_store import JsonGraphStore

LOGGER = get_logger(__name__)


@dataclass
class GraphRepository:
    store: JsonGraphStore = field(default_factory=JsonGraphStore)
    profiles: Dict[str, Profile] = field(default_factory=dict)
    edges: List[Relationship] = field(default_factory=list)

    def __post_init__(self) -> None:
        try:
            self.profiles = self.store.load_profiles()
            self.edges = self.store.load_edges()
            LOGGER.debug(
                "Loaded repository state with %d profiles and %d edges",
                len(self.profiles),
                len(self.edges),
            )
            follower_map: Dict[str, List[str]] = {}
            for edge in self.edges:
                if edge.relation_type == "follower":
                    follower_map.setdefault(edge.target_id, []).append(edge.source_id)
            for pid, followers in follower_map.items():
                profile = self.profiles.get(pid)
                if profile:
                    profile.followers_fetch_attempted = True
                    profile.followers_fetched = bool(followers)
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Failed to load existing data: %s", exc)
            self.profiles = {}
            self.edges = []

    def upsert_profile(self, profile: Profile) -> None:
        existing = self.profiles.get(profile.id)
        if existing:
            profile.followers_fetch_attempted = (
                profile.followers_fetch_attempted or existing.followers_fetch_attempted
            )
            profile.followers_fetched = (
                profile.followers_fetched or existing.followers_fetched
            )
        self.profiles[profile.id] = profile

    def add_edge(self, edge: Relationship) -> None:
        if edge not in self.edges:
            self.edges.append(edge)

    def find_profile(self, profile_id: str) -> Optional[Profile]:
        return self.profiles.get(profile_id)

    def get_followers(self, profile_id: str) -> List[Profile]:
        follower_ids = [edge.source_id for edge in self.edges if edge.relation_type == "follower" and edge.target_id == profile_id]
        return [self.profiles[fid] for fid in follower_ids if fid in self.profiles]

    def persist(self) -> None:
        self.store.save_profiles(self.profiles)
        self.store.save_edges(self.edges)

    def bulk_add_profiles(self, profiles: Iterable[Profile]) -> None:
        for profile in profiles:
            self.upsert_profile(profile)

    def bulk_add_edges(self, edges: Iterable[Relationship]) -> None:
        for edge in edges:
            self.add_edge(edge)


__all__ = ["GraphRepository"]
