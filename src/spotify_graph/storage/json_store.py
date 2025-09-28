from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from spotify_graph.config import PROJECT_ROOT
from spotify_graph.logging import get_logger
from spotify_graph.models.profile import Profile, Relationship

LOGGER = get_logger(__name__)


@dataclass
class JsonGraphStore:
    base_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data")
    timestamp: datetime = field(default_factory=datetime.utcnow)
    current_subdir: str = "current"
    archive_subdir: str = "archive"

    def __post_init__(self) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.current_path = self.base_path / self.current_subdir
        self.archive_path = self.base_path / self.archive_subdir
        self.current_path.mkdir(parents=True, exist_ok=True)
        self.archive_path.mkdir(parents=True, exist_ok=True)
        self._archived = False

        # Backward compatibility for flat data layout
        legacy_profiles = self.base_path / "profiles.json"
        legacy_edges = self.base_path / "edges.json"
        if legacy_profiles.exists() and not self.profiles_path.exists():
            shutil.move(str(legacy_profiles), self.profiles_path)
        if legacy_edges.exists() and not self.edges_path.exists():
            shutil.move(str(legacy_edges), self.edges_path)

        LOGGER.debug(
            "Initialized JsonGraphStore at %s (archive root %s)",
            self.current_path,
            self.archive_path,
        )

    @property
    def profiles_path(self) -> Path:
        return self.current_path / "profiles.json"

    @property
    def edges_path(self) -> Path:
        return self.current_path / "edges.json"

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
        LOGGER.debug("Persisted %d profiles to %s", len(serialized), self.profiles_path)

    def save_edges(self, edges: List[Relationship]) -> None:
        serialized = [json.loads(edge.model_dump_json()) for edge in edges]
        with self.edges_path.open("w", encoding="utf-8") as fp:
            json.dump(serialized, fp, indent=2, ensure_ascii=False)
        LOGGER.debug("Persisted %d edges to %s", len(serialized), self.edges_path)

    def archive_snapshot(self) -> None:
        if self._archived:
            return

        dest = self.archive_path / self.timestamp.strftime("%Y%m%d-%H%M%S")
        dest.mkdir(parents=True, exist_ok=True)
        if self.profiles_path.exists():
            shutil.copy2(self.profiles_path, dest / "profiles.json")
        if self.edges_path.exists():
            shutil.copy2(self.edges_path, dest / "edges.json")
        LOGGER.info("Archived data snapshot to %s", dest)
        self._archived = True
