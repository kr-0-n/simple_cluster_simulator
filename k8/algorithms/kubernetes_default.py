import networkx as nx

from k8.evaluator import evaluate
from utils import get_assigned_pod_ids, get_node_ids, get_pod_ids
from visualizer import draw_graph


def _matches_label_selector(node: dict, pod: dict) -> bool:
    node_labels = node.get("labels", [])
    return all(label in node_labels for label in pod.get("labelSelector", []))


def _fits_resources(graph: nx.DiGraph, node_id, pod: dict) -> bool:
    assigned = get_assigned_pod_ids(graph, node_id)
    cpu_load = sum(graph.nodes[pod_id]["cpu"] for pod_id in assigned)
    mem_load = sum(graph.nodes[pod_id]["mem"] for pod_id in assigned)
    return (cpu_load + pod["cpu"] <= graph.nodes[node_id]["cpu"]
            and mem_load + pod["mem"] <= graph.nodes[node_id]["mem"])


def kubernetes_default(graph: nx.DiGraph, pods=None, debug=False, visualize=False):
    """
    Imitation of the default kube-scheduler: filter nodes (labelSelector, NodeResourceFit),
    score them (even spread of pods) and pick the node with the highest score.
    """
    graph = graph.copy()
    for pod_id, pod in pods:
        ## Stage 1: Filtering (LabelSelector, NodeResourceFit)
        feasible_nodes = [node_id for node_id in get_node_ids(graph)
                          if _matches_label_selector(graph.nodes[node_id], pod)
                          and _fits_resources(graph, node_id, pod)]

        ## Stage 2: Scoring - aim for an even distribution
        num_pods = len(get_pod_ids(graph)) + 1
        num_nodes = len(get_node_ids(graph))
        avg_pods_per_node = num_pods / num_nodes if num_nodes else 0
        scored_nodes = []
        for node_id in feasible_nodes:
            num_scheduled_pods = len(get_assigned_pod_ids(graph, node_id))
            score = 0 if num_scheduled_pods > avg_pods_per_node else avg_pods_per_node - num_scheduled_pods
            scored_nodes.append((node_id, score))

        ## Stage 3: Selection
        graph.add_node(pod_id, **pod)
        if not scored_nodes:
            print(f"no feasible nodes for pod {pod_id}")
            continue
        selected_node = max(scored_nodes, key=lambda item: item[1])[0]
        graph.add_edge(pod_id, selected_node, type="assign")
        if visualize:
            draw_graph(graph, "Kubernetes Default " + str(evaluate(graph)))
    return graph
