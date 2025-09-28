from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"


def load_environment() -> None:
    """Load environment variables from the project .env file if it exists."""
    load_dotenv(dotenv_path=ENV_PATH, override=False)


class Settings(BaseSettings):
    spotify_username: str = Field(..., env="SPOTIFY_USERNAME")
    spotify_password: str = Field(..., env="SPOTIFY_PASSWORD")
    spotify_base_url: str = Field("https://open.spotify.com", env="SPOTIFY_BASE_URL")
    spotify_login_url: str = Field(
        "https://accounts.spotify.com/en/login?&allow_password=1",
        env="SPOTIFY_LOGIN_URL",
    )
    crawl_max_depth: int = Field(1, ge=1, env="CRAWL_MAX_DEPTH")
    follower_threshold: int = Field(1000, ge=0, env="FOLLOWER_THRESHOLD")
    chrome_driver_path: Optional[str] = Field(None, env="CHROME_DRIVER_PATH")
    scroll_pause_seconds: float = Field(0.3, ge=0.0, env="SCROLL_PAUSE_SECONDS")
    max_scroll_iterations: int = Field(30, ge=1, env="MAX_SCROLL_ITERATIONS")
    manual_login_timeout_seconds: int = Field(300, ge=30, env="MANUAL_LOGIN_TIMEOUT_SECONDS")
    followers_download_limit: int = Field(250, ge=0, env="FOLLOWERS_DOWNLOAD_LIMIT")

    @field_validator("spotify_base_url")
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_environment()
    return Settings()  # type: ignore[call-arg]


__all__ = ["Settings", "get_settings", "load_environment", "PROJECT_ROOT"]
