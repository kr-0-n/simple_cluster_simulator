"""
Writes a cluster (nodes, links, pods and their placement) as a Graphviz dot file.
Render it with e.g. `neato -Tpng graph.dot -o graph.png`.
"""
from typing import Optional

import networkx as nx

from simulator.evaluator import Evaluator
from simulator.model import Placement, Pod, PodId

NODE_STYLE = {"shape": "rect", "colorscheme": "blues3", "style": "filled", "color": "2", "fillcolor": "1"}
POD_STYLE = {"shape": "ellipse", "colorscheme": "greens3", "style": "filled", "color": "2", "fillcolor": "1"}
MAX_LINE_WIDTH = 3
MIN_LINE_WIDTH = 0.5
MAX_LINK_THROUGHPUT = 500
MAX_NODE_SIZE = 1.5


def node_name(node_id) -> str:
    return f"node{node_id}"


def pod_name(pod_id) -> str:
    return f"pod{pod_id}"


def to_dot_graph(network: nx.DiGraph, pods: dict[PodId, Pod], placement: Placement,
                 evaluator: Optional[Evaluator] = None, title: str = "") -> nx.DiGraph:
    """
    Links are drawn thicker the more throughput they have and red the more they are
    overloaded (if an evaluator is given).
    """
    load = evaluator.link_loads(placement) if evaluator is not None else {}
    graph = nx.DiGraph(label=title)

    sizes = {n: data["spec"].cpu + data["spec"].mem for n, data in network.nodes(data=True)}
    biggest = max(sizes.values(), default=1)
    for node_id, data in network.nodes(data=True):
        node = data["spec"]
        width = MAX_NODE_SIZE * sizes[node_id] / biggest
        labels = f"\\n{','.join(node.labels)}" if node.labels else ""
        graph.add_node(node_name(node_id), label=f"{node_id}{labels}", width=width, height=width / 2, **NODE_STYLE)

    for source, target, data in network.edges(data=True):
        link = data["spec"]
        width = (link.throughput / MAX_LINK_THROUGHPUT) * (MAX_LINE_WIDTH - MIN_LINE_WIDTH) + MIN_LINE_WIDTH
        wanted = load.get((source, target), 0)
        overload = min(max(0.0, (wanted - link.throughput) / link.throughput), 1.0)
        graph.add_edge(node_name(source), node_name(target), label=f"{link.latency}ms {link.throughput}mbps",
                       weight=100 / link.latency if link.latency else 100, penwidth=width,
                       color="#{:02x}0000".format(int(overload * 255)))

    for pod_id in pods:
        graph.add_node(pod_name(pod_id), label=str(pod_id), **POD_STYLE)
        if placement.get(pod_id) is not None:
            graph.add_edge(pod_name(pod_id), node_name(placement[pod_id]), len=0.2)
    for pod_id, pod in pods.items():
        for connection in pod.network:
            if connection.to in pods:
                graph.add_edge(pod_name(pod_id), pod_name(connection.to), style="dashed", color="darkgreen",
                               label=f"{connection.latency}ms {connection.throughput}mbps", weight=1)
    return graph


def write_dot(path: str, network: nx.DiGraph, pods: dict[PodId, Pod], placement: Placement,
              evaluator: Optional[Evaluator] = None, title: str = ""):
    nx.drawing.nx_pydot.write_dot(to_dot_graph(network, pods, placement, evaluator, title), path)
