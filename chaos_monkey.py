"""
The chaos monkey creates chaos by deleting nodes, pods, and links. Beware, they are randomly chosen.

Every node, pod and link survives a step with probability equal to its "stability" attribute.
"""
from random import Random

import networkx as nx

from utils import get_node_ids, get_pod_ids, get_edges_of_type

DEFAULT_STABILITY = 0.5  # used when an element has no stability attribute

rnd: Random = None  # set by the simulation


def _survives(stability) -> bool:
    return not rnd.random() > stability


_warned = set()  # elements without stability we already warned about


def _stability(attributes: dict, description: str) -> float:
    stability = attributes.get("stability")
    if stability is None:
        if description not in _warned:
            _warned.add(description)
            print(f"{__name__}: {description} has no stability, using {DEFAULT_STABILITY}")
        return DEFAULT_STABILITY
    return stability


def delete_nodes(graph: nx.DiGraph) -> nx.DiGraph:
    for node in get_node_ids(graph):
        if not _survives(_stability(graph.nodes[node], f"Node {node}")):
            graph.remove_node(node)
    return graph


def delete_pods(graph: nx.DiGraph) -> nx.DiGraph:
    for pod in get_pod_ids(graph):
        if not _survives(_stability(graph.nodes[pod], f"Pod {pod}")):
            graph.remove_node(pod)
    return graph


def delete_links(graph: nx.DiGraph) -> nx.DiGraph:
    for link in get_edges_of_type(graph, "connection"):
        if not _survives(_stability(graph.edges[link], f"Link {link}")):
            graph.remove_edge(link[0], link[1])
    return graph


def unleash(graph: nx.DiGraph) -> nx.DiGraph:
    """
    Run all chaos operations once (nodes, then links, then pods).
    """
    delete_nodes(graph)
    delete_links(graph)
    delete_pods(graph)
    return graph
