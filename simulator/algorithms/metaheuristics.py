"""
Search based algorithms: evolutionary search and simulated annealing.

Both start from the current placement with every new pod on its best node
(SchedulingProblem.greedy_initial_placement) and search until the evaluation budget
of the decision is used up, or a placement scores below GOOD_ENOUGH.
"""
import math

from simulator.algorithms.common import GOOD_ENOUGH, SchedulingProblem, number_of_neighbours, random_neighbour
from simulator.model import Placement


def evolutionary_solve(problem: SchedulingProblem, children_per_parent: int = 35,
                       survivors_per_generation: int = 22) -> Placement:
    """
    Every generation each survivor produces children (random neighbours);
    the best children survive. Returns the best placement found.
    """
    first = problem.greedy_initial_placement()
    best = (problem.score(first), first)
    if number_of_neighbours(problem) == 0:
        return first
    survivors = [best] * survivors_per_generation
    while not problem.exhausted() and best[0] >= GOOD_ENOUGH:
        children = []
        for _, parent in survivors:
            for _ in range(children_per_parent):
                if problem.exhausted():
                    break
                child = random_neighbour(problem, parent)
                children.append((problem.score(child), child))
        if not children:
            break
        children.sort(key=lambda child: child[0])
        survivors = children[:survivors_per_generation]
        if survivors[0][0] < best[0]:
            best = survivors[0]
    return best[1]


def simulated_annealing_solve(problem: SchedulingProblem, initial_temperature: float = 1000,
                              final_temperature: float = 0.1) -> Placement:
    """
    Random neighbours are accepted if they are better, worse ones with probability e^(-delta/T).
    The temperature falls geometrically from initial_temperature to final_temperature over the
    evaluations left in the budget.
    """
    current = problem.greedy_initial_placement()
    current_value = problem.score(current)
    best, best_value = current, current_value
    if number_of_neighbours(problem) == 0:
        return current
    iterations = max(1, problem.budget - problem.evaluations)
    cooling_rate = (final_temperature / initial_temperature) ** (1 / iterations)
    temperature = initial_temperature

    while not problem.exhausted() and best_value >= GOOD_ENOUGH:
        candidate = random_neighbour(problem, current)
        candidate_value = problem.score(candidate)
        delta = candidate_value - current_value
        if delta < 0:  # better
            current, current_value = candidate, candidate_value
            if current_value < best_value:
                best, best_value = current, current_value
        elif temperature > 0 and problem.rng.random() < math.exp(-delta / temperature):  # worse, accepted with a probability
            current, current_value = candidate, candidate_value
        temperature *= cooling_rate
    return best
