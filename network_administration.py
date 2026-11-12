"""
Builds the network graph from a topology and repairs it after the chaos monkey broke parts of it.
"""
import networkx as nx

import Time as time
from utils import link_service

node_failures = {} # syntax: {node: [time_steps_of_failure]}  (read by the evaluator)
shared_graph_dict = None  # the topology the network is repaired to


def reset():
    """
    Forget the recorded node failures and the topology (call before every simulation run).
    """
    global shared_graph_dict
    node_failures.clear()
    shared_graph_dict = None


def setup_network(graph_dict: dict) -> nx.DiGraph:
    """
    Create the directed network graph for a topology (see scenarios.py).
    """
    global shared_graph_dict
    shared_graph_dict = graph_dict
    G = nx.DiGraph()
    G.add_nodes_from(graph_dict['nodes'])
    G.add_edges_from(graph_dict['edges'], type="connection")
    for edge in G.edges:
        G.edges[edge]["service"] = link_service(G.edges[edge]["throughput"], G.edges[edge]["latency"])
    return G


def repair_network(graph: nx.DiGraph):
    """
    Bring back every node and link of the topology that is missing in the graph.
    """
    # First check nodes
    for node_id, node_attributes in shared_graph_dict['nodes']:
        if node_id not in graph.nodes:
            print(f"{__name__}: Node {node_id} offline")
            node_failures.setdefault(node_id, []).append(time.current_time_step())
            graph.add_node(node_id, **node_attributes)
            print(f"{__name__}: Node {node_id} back online")
    # Then check edges
    for start, end, link_attributes in shared_graph_dict['edges']:
        if (start, end) not in graph.edges:
            print(f"{__name__}: Link ({start}, {end}) offline")
            graph.add_edge(start, end, type="connection", **link_attributes,
                           service=link_service(link_attributes["throughput"], link_attributes["latency"]))
            print(f"{__name__}: Link ({start}, {end}) back online")
