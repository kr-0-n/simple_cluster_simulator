"""
Shared state and helpers for the scheduling algorithms.

A "solution" is a copy of the simulation graph with "assign" edges (pod -> node).
The neighbourhood of a solution consists of all graphs where exactly one pod is
moved to another node or unassigned.
"""
import hashlib
from random import Random

import networkx as nx

from utils import get_assigned_node_id, get_node_ids, get_pod_ids

# One random generator shared by all algorithms. Access it as `common.rnd`
# (not `from common import rnd`) so that seed() affects every algorithm.
rnd: Random = Random()
rnd.seed(10)


def seed(value):
    """
    Re-seed the random generator used by all algorithms.
    """
    rnd.seed(value)


def assign_randomly(graph: nx.DiGraph, pod: tuple = None) -> nx.DiGraph:
    """
    Add the pod to the graph (in place) and assign it to a random node.
    If no pod is given, a random pod of the graph is removed and re-assigned randomly.
    """
    if pod is None:
        pod_id = rnd.choice(get_pod_ids(graph))
        pod = (pod_id, graph.nodes[pod_id])
        graph.remove_node(pod_id)
    graph.add_node(pod[0], **pod[1])
    graph.add_edge(pod[0], rnd.choice(get_node_ids(graph)), type="assign")
    return graph


def graph_hash(graph: nx.DiGraph) -> int:
    hash_string = str(sorted(graph.nodes)) + str(sorted(graph.edges))
    return int(hashlib.md5(hash_string.encode()).hexdigest(), 16)


def number_neighbour_states(graph: nx.DiGraph) -> int:
    # every pod can be moved to every node or be unassigned
    return len(get_pod_ids(graph)) * (len(get_node_ids(graph)) + 1)


def get_neighbour_at_index(graph: nx.DiGraph, index: int) -> nx.DiGraph:
    """
    Get a single neighbour state without generating all of them.
    For each pod there are (#nodes + 1) neighbours; the first one unassigns the pod.
    """
    if graph is None: raise ValueError("Graph is None")
    if index < 0 or index >= number_neighbour_states(graph): raise IndexError("Index out of range")

    pod_ids = get_pod_ids(graph)
    node_ids = get_node_ids(graph)

    pod_id = pod_ids[index // (len(node_ids) + 1)]
    node_to_pick = (index % (len(node_ids) + 1)) - 1  # -1 means: unassign the pod

    new_graph = graph.copy()
    new_graph.remove_edges_from(list(graph.out_edges(pod_id)) + list(graph.in_edges(pod_id)))
    if node_to_pick != -1:
        new_graph.add_edge(pod_id, node_ids[node_to_pick], type="assign")
    return new_graph


def _without_assignment(graph: nx.DiGraph, pod_id) -> nx.DiGraph:
    new_graph = graph.copy()
    assigned_node_id = get_assigned_node_id(new_graph, pod_id)
    if assigned_node_id is not None:
        new_graph.remove_edge(pod_id, assigned_node_id)
    return new_graph


def generate_neighbour_states(graph: nx.DiGraph) -> list[nx.DiGraph]:
    """
    Generate all neighbour states of the graph: for every pod, one graph where the
    pod is unassigned and one graph per node where the pod is assigned to that node.
    """
    solutions = []
    node_ids = get_node_ids(graph)
    for pod_id in get_pod_ids(graph):
        solutions.append(_without_assignment(graph, pod_id))
        for node_id in node_ids:
            new_graph = _without_assignment(graph, pod_id)
            new_graph.add_edge(pod_id, node_id, type="assign")
            solutions.append(new_graph)
    return solutions
