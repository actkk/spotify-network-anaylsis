from __future__ import annotations

import re
import time
from typing import List, Optional, Tuple

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webdriver import WebDriver

from spotify_graph.config import Settings, get_settings
from spotify_graph.logging import get_logger
from spotify_graph.models import Profile

LOGGER = get_logger(__name__)

DISPLAY_NAME_SELECTORS: Tuple[str, ...] = (
    "h1[data-testid='entityTitle']",
    "h1[data-testid='profile-entity-name']",
    "h1",
)

FOLLOW_LINK_PATTERNS: Tuple[str, ...] = (
    "/followers",
    "/following",
)

PRIVATE_MESSAGE_SELECTORS: Tuple[str, ...] = (
    "[data-testid='profile-private-notice']",
    "div[data-testid='message-bar']",
    "div[data-testid='empty-state-message']",
)

PROFILE_LINK_REGEX = re.compile(r"/user/([a-zA-Z0-9]+)")
NUMBER_SANITIZER = re.compile(r"[^0-9]")


class ProfilePageScraper:
    """High-level helpers to extract profile metadata and connections."""

    def __init__(
        self,
        driver: WebDriver,
        *,
        settings: Optional[Settings] = None,
    ) -> None:
        self.driver = driver
        self.settings = settings or get_settings()
        self.wait = WebDriverWait(driver, 10)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_profile_overview(self, profile_id: str) -> Profile:
        """Load the profile overview page and extract core metadata."""
        profile_url = f"{self.settings.spotify_base_url}/user/{profile_id}"
        LOGGER.debug("Loading profile overview: %s", profile_url)
        self.driver.get(profile_url)
        self._dismiss_cookie_banner()

        display_name = self._extract_display_name() or self._fallback_profile_name()
        followers = self._extract_count_from_links("followers")
        following = self._extract_count_from_links("following")
        is_private = self._detect_private_message()

        profile = Profile(
            id=profile_id,
            display_name=display_name,
            followers=followers,
            following=following,
            profile_url=profile_url,
            is_private=is_private,
        )
        LOGGER.debug(
            "Overview for %s -> display=%s, followers=%s, following=%s, private=%s",
            profile_id,
            display_name,
            followers,
            following,
            is_private,
        )
        return profile

    def fetch_connections(
        self,
        profile_id: str,
        relation: str,
        *,
        expected_count: Optional[int] = None,
    ) -> Tuple[List[Profile], bool]:
        """Return a list of connections (followers or following) for the user.

        The boolean flag indicates whether the list was accessible (False for private/inaccessible).
        """
        relation = relation.lower()
        if relation not in {"followers", "following"}:
            raise ValueError("relation must be either 'followers' or 'following'")

        list_url = f"{self.settings.spotify_base_url}/user/{profile_id}/{relation}"
        LOGGER.debug("Loading %s list for %s", relation, profile_id)
        self.driver.get(list_url)
        self._dismiss_cookie_banner()

        section = self._get_list_section(relation)
        if section is None:
            LOGGER.info("%s list appears to be private or inaccessible", relation)
            return [], False

        connections = self._collect_cards(section, expected_count=expected_count)
        LOGGER.info("Found %d %s entries for %s", len(connections), relation, profile_id)
        return connections, True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_display_name(self) -> Optional[str]:
        for selector in DISPLAY_NAME_SELECTORS:
            try:
                element = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                text = element.text.strip()
                if text:
                    return text
            except TimeoutException:
                continue
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("Display name selector %s failed: %s", selector, exc)
        return None

    def _fallback_profile_name(self) -> Optional[str]:
        try:
            heading = self.driver.find_element(By.XPATH, "//h1")
            text = heading.text.strip()
            if text:
                return text
        except Exception:  # noqa: BLE001
            pass
        title = self.driver.title
        if title:
            return title.replace("Spotify – Web Player", "").replace("on Spotify", "").strip(" -") or None
        return None

    def _extract_count_from_links(self, keyword: str) -> Optional[int]:
        try:
            links = self.driver.find_elements(By.CSS_SELECTOR, f"a[href*='{keyword}']")
        except Exception:  # noqa: BLE001
            links = []
        for link in links:
            text = link.text.strip()
            if not text:
                continue
            digits_only = NUMBER_SANITIZER.sub("", text)
            if digits_only:
                try:
                    return int(digits_only)
                except ValueError:
                    continue
        return None

    def _get_list_section(self, relation: str) -> Optional[WebElement]:
        title = "Following" if relation == "following" else "Followers"
        xpath = f"//section[.//h1[contains(normalize-space(.), '{title}')]]"

        try:
            return WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
        except TimeoutException:
            if self._detect_private_message():
                return None
            LOGGER.warning("Timed out waiting for %s section", relation)
            return None

    def _detect_private_message(self) -> bool:
        for selector in PRIVATE_MESSAGE_SELECTORS:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                if elem and elem.is_displayed():
                    LOGGER.debug("Detected private notice via selector %s", selector)
                    return True
            except Exception:  # noqa: BLE001
                continue
        try:
            elem = self.driver.find_element(By.XPATH, "//h2[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'private')]")
            if elem and elem.is_displayed():
                return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _collect_cards(self, section: WebElement, expected_count: Optional[int] = None) -> List[Profile]:
        collected: List[Profile] = []
        seen_ids: set[str] = set()
        previous_count = -1
        stagnant_rounds = 0

        for _ in range(self.settings.max_scroll_iterations):
            cards = section.find_elements(
                By.XPATH,
                ".//div[contains(@class,'Card') and .//a[contains(@href,'/user/')]]",
            )
            if len(cards) == previous_count:
                stagnant_rounds += 1
                if stagnant_rounds >= 2:
                    break
            else:
                stagnant_rounds = 0
                previous_count = len(cards)

            for card in cards:
                profile = self._profile_from_card(card)
                if profile and profile.id not in seen_ids:
                    seen_ids.add(profile.id)
                    collected.append(profile)

            if expected_count is not None and len(collected) >= expected_count:
                break

            if cards:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'end', inline: 'nearest'});",
                    cards[-1],
                )
            time.sleep(self.settings.scroll_pause_seconds)

        return collected

    def _profile_from_card(self, card: WebElement) -> Optional[Profile]:
        try:
            link = card.find_element(By.CSS_SELECTOR, "a[href*='/user/']")
        except Exception:  # noqa: BLE001
            return None

        href = link.get_attribute("href") or ""
        match = PROFILE_LINK_REGEX.search(href)
        if not match:
            return None
        profile_id = match.group(1)

        display_name = link.text.strip() or self._extract_text_from_card(card)
        profile_url = href.split("?")[0]

        avatar_url = None
        try:
            img = card.find_element(By.TAG_NAME, "img")
            avatar_url = img.get_attribute("src") or None
        except Exception:  # noqa: BLE001
            avatar_url = None

        return Profile(
            id=profile_id,
            display_name=display_name or profile_id,
            profile_url=profile_url,
            avatar_url=avatar_url,
            is_private=False,
        )

    def _extract_text_from_card(self, card: WebElement) -> Optional[str]:
        try:
            text = card.text.strip()
            return text if text else None
        except Exception:  # noqa: BLE001
            return None

    def _dismiss_cookie_banner(self) -> None:
        candidates = [
            (By.ID, "onetrust-accept-btn-handler"),
            (By.CSS_SELECTOR, "button[data-testid='cookie-banner-accept']"),
            (By.CSS_SELECTOR, "button[data-testid='close-button']"),
        ]

        for by, value in candidates:
            try:
                button = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((by, value)))
                button.click()
                LOGGER.debug("Dismissed cookie banner via %s", value)
                time.sleep(1)
                return
            except Exception:  # noqa: BLE001
                continue


__all__ = ["ProfilePageScraper"]
