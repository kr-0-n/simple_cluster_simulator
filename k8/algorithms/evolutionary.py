from k8.algorithms import common
from k8.algorithms.common import assign_randomly, get_neighbour_at_index, number_neighbour_states
from k8.evaluator import evaluate_step
from metrics import update_metric

GENERATIONS = 100
CHILDREN_PER_PARENT = 35
SURVIVORS_PER_GENERATION = 22


def evolutionary_solve(graph, pods=None, debug=False, visualize=False):
    """
    Evolutionary search: every generation each survivor produces children (random
    neighbour states); the best children survive. Returns the best graph found.
    New pods are first assigned to random nodes.
    """
    first_solution = graph.copy()
    if pods is not None:
        for pod in pods:
            assign_randomly(first_solution, pod)
    if number_neighbour_states(first_solution) == 0:
        return first_solution  # nothing to optimise

    current_best = (evaluate_step(graph, first_solution, debug=False), first_solution)

    survivors = [current_best] * SURVIVORS_PER_GENERATION
    for generation in range(GENERATIONS):
        if debug:
            print(f"Generation {generation}: {survivors}")
        children = []
        for parent in range(SURVIVORS_PER_GENERATION):
            parent_graph = survivors[parent][1]
            for _ in range(CHILDREN_PER_PARENT):
                rand_index = common.rnd.randint(0, number_neighbour_states(parent_graph) - 1)
                new_graph = get_neighbour_at_index(parent_graph, rand_index)
                children.append((evaluate_step(graph, new_graph, debug=False), new_graph))
        children.sort(key=lambda x: x[0])
        survivors = children[:SURVIVORS_PER_GENERATION]
        if survivors[0][0] < current_best[0]:
            current_best = survivors[0]

    update_metric("num_eval_func_calls", GENERATIONS * CHILDREN_PER_PARENT * SURVIVORS_PER_GENERATION)
    return current_best[1]
