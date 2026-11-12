"""
Helpers for querying the simulation graph.

The simulation uses a single nx.DiGraph that contains
  - vertices with type "node" (cluster nodes) and type "pod",
  - edges with type "connection" (network links between nodes) and
    type "assign" (pod -> node, the pod runs on that node).
"""
from typing import Optional

import networkx as nx

from simmath.LinearFunction import LinearFunction


def get_assigned_node_id(graph: nx.DiGraph, pod_id: int) -> Optional[int]:
    """
    Get the node that the pod is assigned to.

    Parameters
    ----------
    graph : nx.DiGraph
        The graph to search for the assignment
    pod_id : int
        The id of the pod to search for

    Returns
    -------
    int | None
        The node id that the pod is assigned to, or None if the pod is not assigned
    """
    pod = graph.nodes[pod_id]
    if pod["type"] != "pod": raise ValueError(f"{pod_id} is not a pod")
    assigned_nodes = [neighbor for neighbor in graph.neighbors(pod_id) if graph.nodes[neighbor]["type"] == "node"]

    if len(assigned_nodes) > 1: raise ValueError(f"Pod {pod_id} is assigned to more than one node")
    if len(assigned_nodes) == 1: return assigned_nodes[0]
    return None


def get_pod_ids(graph: nx.DiGraph) -> list:
    """
    Get a list of all pod ids in the graph.
    """
    return [node for node in graph.nodes if graph.nodes[node]["type"] == "pod"]


def get_node_ids(graph: nx.DiGraph) -> list:
    """
    Get a list of all node ids in the graph.
    """
    return [node for node in graph.nodes if graph.nodes[node]["type"] == "node"]


def get_assigned_pod_ids(graph: nx.DiGraph, node_id: int) -> list:
    """
    Get a list of pod ids assigned to a particular node.
    """
    return [pod for pod in graph.predecessors(node_id) if graph.nodes[pod]["type"] == "pod"]


def get_edges_of_type(graph: nx.DiGraph, edge_type: str) -> list:
    """
    Get all edges of the given type ("connection", "assign", "wanted_connection").
    """
    return [edge for edge in graph.edges if graph.edges[edge].get("type") == edge_type]


def get_scheduled_pod_ids(graph: nx.DiGraph) -> set:
    """
    Get the ids of all pods that are in the graph and assigned to a node.
    """
    return {edge[0] for edge in get_edges_of_type(graph, "assign") if graph.nodes[edge[0]]["type"] == "pod"}


def link_service(throughput: float, latency: float) -> LinearFunction:
    """
    The service curve of a network link (rate-latency curve).
    """
    return LinearFunction(throughput, 0, -latency)
