from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Tuple

import networkx as nx

from spotify_graph.logging import get_logger
from spotify_graph.models import Profile, Relationship
from spotify_graph.storage.json_store import JsonGraphStore

LOGGER = get_logger(__name__)


def _display_name(profile: Profile) -> str:
    return profile.display_name or profile.id


def load_state(store: JsonGraphStore | None = None) -> Tuple[Dict[str, Profile], Iterable[Relationship]]:
    repo_store = store or JsonGraphStore()
    profiles = repo_store.load_profiles()
    edges = repo_store.load_edges()
    LOGGER.info("Loaded %d profiles and %d edges", len(profiles), len(edges))
    return profiles, edges


def build_display_graph(
    *,
    store: JsonGraphStore | None = None,
    include_private: bool = True,
) -> nx.DiGraph:
    profiles, edges = load_state(store)
    graph = nx.DiGraph()

    for profile in profiles.values():
        if not include_private and profile.is_private:
            continue
        data = {
            key: value
            for key, value in profile.model_dump(mode="json").items()
            if value is not None
        }
        data["label"] = _display_name(profile)
        graph.add_node(profile.id, **data)

    for edge in edges:
        source = profiles.get(edge.source_id)
        target = profiles.get(edge.target_id)
        if not source or not target:
            continue
        if not include_private and (source.is_private or target.is_private):
            continue
        edge_data = {
            key: value
            for key, value in edge.model_dump(mode="json").items()
            if value is not None
        }
        graph.add_edge(edge.source_id, edge.target_id, **edge_data)

    LOGGER.info(
        "Graph contains %d nodes and %d edges (include_private=%s)",
        graph.number_of_nodes(),
        graph.number_of_edges(),
        include_private,
    )
    return graph


def export_graphml(graph: nx.DiGraph, path: Path) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, path)
    LOGGER.info("Graph written to %s", path)


__all__ = ["build_display_graph", "export_graphml"]
