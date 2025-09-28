from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set, Tuple

from spotify_graph.models.profile import Profile
from spotify_graph.models.profile import Relationship


@dataclass
class RunRecorder:
    profile_ids: Set[str] = field(default_factory=set)
    _edge_keys: Set[Tuple[str, str, str]] = field(default_factory=set)
    edges: List[Relationship] = field(default_factory=list)

    def record_profile(self, profile: Profile) -> None:
        self.profile_ids.add(profile.id)

    def record_edge(self, edge: Relationship) -> None:
        key = (edge.source_id, edge.target_id, edge.relation_type)
        if key not in self._edge_keys:
            self._edge_keys.add(key)
            self.edges.append(edge)


__all__ = ["RunRecorder"]
