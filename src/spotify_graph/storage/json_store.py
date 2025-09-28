from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from spotify_graph.config import PROJECT_ROOT
from spotify_graph.logging import get_logger
from spotify_graph.models.profile import Profile, Relationship

LOGGER = get_logger(__name__)


@dataclass
class JsonGraphStore:
    base_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data")

    def __post_init__(self) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        LOGGER.debug("Initialized JsonGraphStore at %s", self.base_path)

    @property
    def profiles_path(self) -> Path:
        return self.base_path / "profiles.json"

    @property
    def edges_path(self) -> Path:
        return self.base_path / "edges.json"

    def load_profiles(self) -> Dict[str, Profile]:
        if not self.profiles_path.exists():
            return {}
        with self.profiles_path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return {pid: Profile(**data) for pid, data in payload.items()}

    def load_edges(self) -> List[Relationship]:
        if not self.edges_path.exists():
            return []
        with self.edges_path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return [Relationship(**entry) for entry in payload]

    def save_profiles(self, profiles: Dict[str, Profile]) -> None:
        serialized = {pid: json.loads(profile.model_dump_json()) for pid, profile in profiles.items()}
        with self.profiles_path.open("w", encoding="utf-8") as fp:
            json.dump(serialized, fp, indent=2, ensure_ascii=False)
        LOGGER.debug("Persisted %d profiles", len(serialized))

    def save_edges(self, edges: List[Relationship]) -> None:
        serialized = [json.loads(edge.model_dump_json()) for edge in edges]
        with self.edges_path.open("w", encoding="utf-8") as fp:
            json.dump(serialized, fp, indent=2, ensure_ascii=False)
        LOGGER.debug("Persisted %d edges", len(serialized))


__all__ = ["JsonGraphStore"]
