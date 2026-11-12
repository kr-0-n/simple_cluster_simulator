import itertools

from k8.evaluator import evaluate, evaluate_step
from metrics import update_metric
from utils import get_node_ids, get_pod_ids, get_edges_of_type
from visualizer import draw_graph


def perfect_solve(graph, pods=None, debug=False, visualize=False):
    """
    Brute force: try every assignment of pods to nodes (#nodes ^ #pods combinations)
    and return the best graph. Stops early if a solution with evaluation 0 is found.
    """
    if pods is not None:
        for pod in pods:
            graph.add_node(pod[0], **pod[1])
    node_ids = get_node_ids(graph)
    pod_ids = get_pod_ids(graph)

    solutions_checked = 0
    current_best = (evaluate(graph), graph)
    print(f"now checking {len(node_ids)} ^ {len(pod_ids)} assignments")
    for nodes_for_pods in itertools.product(node_ids, repeat=len(pod_ids)):
        combination = list(zip(pod_ids, nodes_for_pods))
        solutions_checked += 1
        new_graph = graph.copy()
        new_graph.remove_edges_from(get_edges_of_type(new_graph, "assign"))
        if debug:
            print("#"*50)
            print(f"combination: {combination}")
        for pod_id, node_id in combination:
            new_graph.add_edge(pod_id, node_id, type="assign")

        evaluation = evaluate_step(graph, new_graph, debug=False)
        if evaluation < current_best[0]:
            current_best = (evaluation, new_graph)
            if visualize:
                draw_graph(new_graph, "Evaluation: " + str(evaluation))
            if debug:
                print(f"new best: {current_best[0]}")
            if evaluation == 0:
                break
        elif debug:
            print(f"evaluation: {evaluation}")

    print(f"checked {solutions_checked} combinations")
    update_metric("num_eval_func_calls", solutions_checked)
    return current_best[1]
