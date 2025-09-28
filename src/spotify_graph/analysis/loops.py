from __future__ import annotations

from typing import List, Sequence, Tuple

import networkx as nx

from spotify_graph.analysis.graph_builder import build_display_graph
from spotify_graph.logging import get_logger

LOGGER = get_logger(__name__)


def find_triangles(include_private: bool = True) -> List[Tuple[str, str, str]]:
    """Return triangles (friend-of-friend loops) as display-name tuples."""
    digraph = build_display_graph(include_private=include_private)
    graph = nx.Graph()
    graph.add_nodes_from(digraph.nodes(data=True))
    graph.add_edges_from(digraph.to_undirected().edges())

    triangles = set()
    for node in graph:
        neighbors = list(graph.neighbors(node))
        for i, v in enumerate(neighbors):
            for w in neighbors[i + 1 :]:
                if graph.has_edge(v, w):
                    trio = tuple(sorted({node, v, w}))
                    triangles.add(trio)

    results: List[Tuple[str, str, str]] = []
    for trio in triangles:
        labels = tuple(graph.nodes[n].get("label", n) for n in trio)
        results.append(labels)

    LOGGER.info("Detected %d triangles", len(results))
    return sorted(results)


__all__ = ["find_triangles"]
