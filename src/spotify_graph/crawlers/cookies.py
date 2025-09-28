from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, List

from selenium.webdriver.remote.webdriver import WebDriver

from spotify_graph.logging import get_logger

LOGGER = get_logger(__name__)

SAFE_COOKIE_KEYS = {
    "domain",
    "expiry",
    "httpOnly",
    "name",
    "path",
    "secure",
    "value",
    "sameSite",
}


def _sanitize_cookie(cookie: dict) -> dict:
    sanitized = {key: cookie[key] for key in SAFE_COOKIE_KEYS if key in cookie}
    # Selenium expects expiry as int
    if "expiry" in sanitized and sanitized["expiry"] is not None:
        try:
            sanitized["expiry"] = int(sanitized["expiry"])
        except (ValueError, TypeError):
            sanitized.pop("expiry", None)
    return sanitized


def save_cookies(driver: WebDriver, path: Path, *, domains: Iterable[str]) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        original_url = driver.current_url
    except Exception:  # noqa: BLE001
        original_url = None

    all_cookies: List[dict] = []
    for domain in domains:
        try:
            LOGGER.debug("Collecting cookies for %s", domain)
            driver.get(domain)
            time.sleep(1)
            cookies = driver.get_cookies()
            all_cookies.extend(_sanitize_cookie(cookie) for cookie in cookies)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Failed to collect cookies for %s: %s", domain, exc)

    if original_url:
        try:
            driver.get(original_url)
        except Exception:  # noqa: BLE001
            LOGGER.debug("Unable to restore original URL after saving cookies")

    with path.open("w", encoding="utf-8") as fp:
        json.dump(all_cookies, fp, indent=2)
    LOGGER.info("Saved %d cookies to %s", len(all_cookies), path)


def load_cookies(driver: WebDriver, path: Path, *, base_domain: str) -> bool:
    cookie_path = path.expanduser()
    if not cookie_path.exists():
        LOGGER.info("Cookie file %s not found", cookie_path)
        return False

    LOGGER.info("Loading cookies from %s", cookie_path)
    with cookie_path.open("r", encoding="utf-8") as fp:
        cookies = json.load(fp)

    try:
        driver.get(base_domain)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Failed to open base domain %s before loading cookies: %s", base_domain, exc)
        return False

    applied = 0
    for cookie in cookies:
        sanitized = _sanitize_cookie(cookie)
        try:
            driver.add_cookie(sanitized)
            applied += 1
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Failed to add cookie %s: %s", sanitized.get("name"), exc)
            continue

    LOGGER.info("Loaded %d cookies", applied)
    driver.refresh()
    time.sleep(1)
    return applied > 0


__all__ = ["save_cookies", "load_cookies"]
