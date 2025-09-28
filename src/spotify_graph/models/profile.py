from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class Profile(BaseModel):
    id: str
    display_name: Optional[str] = None
    followers: Optional[int] = None
    following: Optional[int] = None
    profile_url: Optional[HttpUrl] = None
    avatar_url: Optional[HttpUrl] = None
    is_private: bool = False
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    followers_fetch_attempted: bool = False
    followers_fetched: bool = False
    followers_oversized: bool = False


class Relationship(BaseModel):
    source_id: str
    target_id: str
    relation_type: str = "following"
    discovered_at: datetime = Field(default_factory=datetime.utcnow)


__all__ = ["Profile", "Relationship"]
