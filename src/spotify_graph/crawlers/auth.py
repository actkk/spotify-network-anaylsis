from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webdriver import WebDriver

from spotify_graph.config import Settings, get_settings
from spotify_graph.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class AuthResult:
    success: bool
    error: Optional[str] = None


class SpotifyWebAuthenticator:
    """Handles browser automation for Spotify web login."""

    def __init__(self, driver: WebDriver, *, settings: Optional[Settings] = None) -> None:
        self.driver = driver
        self.settings = settings or get_settings()
        self.wait = WebDriverWait(driver, 20)

    def login(self, *, manual: bool = False) -> AuthResult:
        LOGGER.info("Opening Spotify login page")
        login_url = self.settings.spotify_login_url
        self.driver.get(login_url)
        self._dismiss_cookie_banner()

        if manual:
            LOGGER.info("Manual login requested. Waiting for user to complete authentication.")
            return self._await_manual_login()

        try:
            username = self.wait.until(EC.presence_of_element_located((By.ID, "login-username")))
            password = self.wait.until(EC.presence_of_element_located((By.ID, "login-password")))
            submit = self.wait.until(EC.element_to_be_clickable((By.ID, "login-button")))
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Failed to locate login form elements: %s", exc)
            return AuthResult(success=False, error="LOGIN_FORM_NOT_FOUND")

        username.clear()
        username.send_keys(self.settings.spotify_username)
        password.clear()
        password.send_keys(self.settings.spotify_password)
        submit.click()

        LOGGER.info("Submitted credentials; waiting for post-login redirect")
        return self.confirm_login()

    def logout(self) -> None:
        LOGGER.info("Attempting to log out")
        account_url = f"{self.settings.spotify_base_url}/logout"
        self.driver.get(account_url)
        time.sleep(2)

    def _dismiss_cookie_banner(self) -> None:
        """Attempt to close Spotify's cookie consent banner if present."""
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

    def _await_manual_login(self) -> AuthResult:
        timeout = self.settings.manual_login_timeout_seconds
        LOGGER.info("Waiting up to %s seconds for manual login to finish", timeout)
        end_time = time.time() + timeout
        while time.time() < end_time:
            if "login" not in (self.driver.current_url or "").lower():
                LOGGER.info("Manual login detected based on URL change.")
                return self.confirm_login()
            try:
                error_elem = self.driver.find_element(By.CSS_SELECTOR, "div.Message-sc-15vkh7g-0")
                if error_elem and error_elem.is_displayed():
                    error_text = error_elem.text.strip() or "UNKNOWN_ERROR"
                    LOGGER.error("Manual login failed: %s", error_text)
                    return AuthResult(success=False, error=error_text)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)

        LOGGER.error("Manual login timed out after %s seconds", timeout)
        return AuthResult(success=False, error="MANUAL_LOGIN_TIMEOUT")

    def confirm_login(self) -> AuthResult:
        time.sleep(2)
        current_url = (self.driver.current_url or "").lower()
        LOGGER.debug("Post-login URL: %s", current_url)

        if "login" in current_url:
            try:
                error_elem = self.driver.find_element(By.CSS_SELECTOR, "div.Message-sc-15vkh7g-0")
                error_text = error_elem.text.strip()
            except Exception:  # noqa: BLE001
                error_text = "UNKNOWN_ERROR"
            LOGGER.error("Login failed: %s", error_text)
            return AuthResult(success=False, error=error_text)

        try:
            self.driver.find_element(By.ID, "login-username")
            LOGGER.error("Login form still visible; assuming login failed")
            return AuthResult(success=False, error="LOGIN_FORM_STILL_VISIBLE")
        except Exception:  # noqa: BLE001
            pass

        try:
            self.driver.find_element(By.CSS_SELECTOR, "[data-testid='user-widget-name']")
            LOGGER.info("Login appears successful via user widget.")
        except Exception:  # noqa: BLE001
            LOGGER.info("Login appears successful (no login indicators present).")
        return AuthResult(success=True)


__all__ = ["SpotifyWebAuthenticator", "AuthResult"]
