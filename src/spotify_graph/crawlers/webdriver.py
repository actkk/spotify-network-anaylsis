from __future__ import annotations

from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService

from spotify_graph.config import Settings, get_settings


def build_chrome_driver(
    *,
    headless: bool = True,
    settings: Optional[Settings] = None,
) -> webdriver.Chrome:
    """Instantiate a Chrome driver with sensible defaults."""
    conf = settings or get_settings()

    options = ChromeOptions()
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    if headless:
        options.add_argument("--headless=new")

    driver_path: Optional[str] = conf.chrome_driver_path
    if driver_path:
        service = ChromeService(executable_path=str(Path(driver_path).expanduser()))
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    driver.set_page_load_timeout(30)
    driver.implicitly_wait(5)
    return driver


__all__ = ["build_chrome_driver"]
