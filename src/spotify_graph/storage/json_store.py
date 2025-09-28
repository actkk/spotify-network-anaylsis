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
    master_subdir: str = "master"

    def __post_init__(self) -> None:
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.current_path = self.base_path / self.current_subdir
        self.archive_path = self.base_path / self.archive_subdir
        self.master_path = self.base_path / self.master_subdir
        self.current_path.mkdir(parents=True, exist_ok=True)
        self.archive_path.mkdir(parents=True, exist_ok=True)
        self.master_path.mkdir(parents=True, exist_ok=True)
        self._archived = False

        self._migrate_flat_files()

        LOGGER.debug(
            "Initialized JsonGraphStore (current=%s, archive=%s, master=%s)",
            self.current_path,
            self.archive_path,
            self.master_path,
        )

    def _migrate_flat_files(self) -> None:
        legacy_profiles = self.base_path / "profiles.json"
        legacy_edges = self.base_path / "edges.json"
        if legacy_profiles.exists() and not self.master_profiles_path.exists():
            shutil.move(str(legacy_profiles), self.master_profiles_path)
        if legacy_edges.exists() and not self.master_edges_path.exists():
            shutil.move(str(legacy_edges), self.master_edges_path)

    @property
    def profiles_path(self) -> Path:
        return self.current_path / "profiles.json"

    @property
    def edges_path(self) -> Path:
        return self.current_path / "edges.json"

    @property
    def master_profiles_path(self) -> Path:
        return self.master_path / "profiles.json"

    @property
    def master_edges_path(self) -> Path:
        return self.master_path / "edges.json"

    def load_profiles(self) -> Dict[str, Profile]:
        path = self.master_profiles_path if self.master_profiles_path.exists() else self.profiles_path
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return {pid: Profile(**data) for pid, data in payload.items()}

    def load_edges(self) -> List[Relationship]:
        path = self.master_edges_path if self.master_edges_path.exists() else self.edges_path
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return [Relationship(**entry) for entry in payload]

    def save_profiles(self, profiles: Dict[str, Profile]) -> None:
        serialized = {pid: json.loads(profile.model_dump_json()) for pid, profile in profiles.items()}
        self._write_json(self.profiles_path, serialized)

        master = self._read_json(self.master_profiles_path, default={})
        master.update(serialized)
        self._write_json(self.master_profiles_path, master)
        LOGGER.debug("Persisted %d profiles (current=%s, master=%s)", len(serialized), self.profiles_path, self.master_profiles_path)

    def save_edges(self, edges: List[Relationship]) -> None:
        serialized = [json.loads(edge.model_dump_json()) for edge in edges]
        self._write_json(self.edges_path, serialized)

        master = self._read_json(self.master_edges_path, default=[])
        existing = {(e["source_id"], e["target_id"], e.get("relation_type", "")) for e in master}
        for entry in serialized:
            key = (entry["source_id"], entry["target_id"], entry.get("relation_type", ""))
            if key not in existing:
                master.append(entry)
                existing.add(key)
        self._write_json(self.master_edges_path, master)
        LOGGER.debug("Persisted %d edges (current=%s, master=%s)", len(serialized), self.edges_path, self.master_edges_path)

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

    def _write_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, ensure_ascii=False)

    def _read_json(self, path: Path, default):
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)
