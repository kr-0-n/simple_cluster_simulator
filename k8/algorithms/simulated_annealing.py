import math

from k8.algorithms import common
from k8.algorithms.common import assign_randomly, get_neighbour_at_index, number_neighbour_states
from k8.evaluator import evaluate_step
from metrics import update_metric

MAX_ITERATIONS = 250
INITIAL_TEMPERATURE = 1000
COOLING_RATE = 0.92


def simulated_annealing_solve(graph, pods=None, debug=False, visualize=False):
    """
    Simulated annealing over the neighbour states. New pods are first assigned to random nodes.
    """
    first_solution = graph.copy()
    if pods is not None:
        for pod in pods:
            assign_randomly(first_solution, pod)
    if number_neighbour_states(first_solution) == 0:
        return first_solution  # nothing to optimise
    current_solution = first_solution
    current_value = evaluate_step(graph, current_solution)
    best_solution = current_solution
    best_value = current_value
    temperature = INITIAL_TEMPERATURE

    for _ in range(MAX_ITERATIONS):
        rnd_solution_index = common.rnd.randint(0, number_neighbour_states(current_solution) - 1)
        new_solution = get_neighbour_at_index(current_solution, rnd_solution_index)
        new_value = evaluate_step(graph, new_solution)

        delta_value = new_value - current_value
        if delta_value < 0: # new solution is better
            current_solution = new_solution
            current_value = new_value

            if current_value < best_value:
                best_solution = current_solution
                best_value = current_value
        else: # new solution is worse
            acceptance_probability = math.exp(-delta_value / temperature)
            if common.rnd.random() < acceptance_probability:
                current_solution = new_solution
                current_value = new_value

        temperature *= COOLING_RATE
    update_metric("num_eval_func_calls", MAX_ITERATIONS)
    return best_solution
