"""
Writes the simulation graph as a Graphviz dot file (render with e.g. `neato -Tpng graph.dot -o graph.png`).
"""
import networkx as nx

graph_styles = {
    "node": {
        "shape": "rect",
        "colorscheme": "blues3",
        "style": "filled",
        "color": "2",
        "fillcolor": "1"
    },
    "pod": {
        "shape": "ellipse",
        "colorscheme": "greens3",
        "style": "filled",
        "color": "2",
        "fillcolor": "1"
    }
}

MAX_LINE_WIDTH = 3
MIN_LINE_WIDTH = 0.5
MAX_LINK_THROUGHPUT = 500
MAX_NODE_SIZE = 1.5


def _link_label(link: dict) -> str:
    return f"{link['latency']}ms {link['throughput']}mbps"


def edge_styles(kind: str, link: dict) -> dict:
    if kind == "wanted_connection":
        return {"label": _link_label(link), "weight": 1, "colorscheme": "greens3", "style": "filled", "color": "2", "fillcolor": "1"}
    if kind == "connection":
        width = (link["throughput"] / MAX_LINK_THROUGHPUT) * (MAX_LINE_WIDTH - MIN_LINE_WIDTH) + MIN_LINE_WIDTH

        # red component shows how much the link is overloaded (wanted_service is set by the evaluator)
        overload = 0
        for wanted_connection in link.get("wanted_service", {}).values():
            if wanted_connection.m > link["service"].m:
                overload += (wanted_connection.m - link["service"].m) / link["service"].m
        overload = min(overload, 100) / 100
        weight = 100 * (1 / link["latency"]) if link["latency"] else 100
        return {"label": _link_label(link), "weight": weight, "penwidth": width, "color": "#{:02x}0000".format(int(overload * 255))}
    if kind == "assign":
        return {"len": 0.2}
    return {}


def draw_graph(graph: nx.DiGraph, title: str = "", file_name: str = "graph.dot"):
    """
    Write a styled copy of the graph to a dot file. The given graph is not modified.
    """
    graph = graph.copy()
    graph.graph["label"] = title

    # show the connections the pods want to have
    for pod in [node for node in graph.nodes if graph.nodes[node]["type"] == "pod"]:
        for pod_to, latency, throughput in graph.nodes[pod]["network"]:
            if graph.has_node(pod_to):
                graph.add_edge(pod, pod_to, latency=latency, throughput=throughput, type="wanted_connection")

    node_ids = [node for node in graph.nodes if graph.nodes[node]["type"] == "node"]
    node_size = lambda node: graph.nodes[node]["cpu"] + graph.nodes[node]["mem"]
    biggest_node_size = max(node_size(node) for node in node_ids) if node_ids else 1

    for node in graph.nodes:
        node_type = graph.nodes[node]["type"]
        graph.nodes[node].update(graph_styles[node_type])
        if node_type == "node":
            graph.nodes[node]["width"] = MAX_NODE_SIZE * node_size(node) / biggest_node_size
            graph.nodes[node]["height"] = graph.nodes[node]["width"] / 2

    for edge in graph.edges:
        edge_type = graph.edges[edge].get("type")
        if edge_type is not None:
            graph.edges[edge].update(edge_styles(edge_type, graph.edges[edge]))

    nx.drawing.nx_pydot.write_dot(graph, file_name)
