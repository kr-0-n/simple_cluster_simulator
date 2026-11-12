"""
Search based algorithms: evolutionary search and simulated annealing.
Both start from the current placement with the new pods assigned to random nodes.
"""
import math

from simulator.algorithms.common import SchedulingProblem, number_of_neighbours, random_neighbour
from simulator.model import Placement


def evolutionary_solve(problem: SchedulingProblem, generations: int = 100, children_per_parent: int = 35,
                       survivors_per_generation: int = 22) -> Placement:
    """
    Every generation each survivor produces children (random neighbours);
    the best children survive. Returns the best placement found.
    """
    first = problem.random_initial_placement()
    if number_of_neighbours(problem) == 0:
        return first
    best = (problem.score(first), first)
    survivors = [best] * survivors_per_generation
    for _ in range(generations):
        children = []
        for _, parent in survivors:
            for _ in range(children_per_parent):
                child = random_neighbour(problem, parent)
                children.append((problem.score(child), child))
        children.sort(key=lambda child: child[0])
        survivors = children[:survivors_per_generation]
        if survivors[0][0] < best[0]:
            best = survivors[0]
    return best[1]


def simulated_annealing_solve(problem: SchedulingProblem, max_iterations: int = 250,
                              initial_temperature: float = 1000, cooling_rate: float = 0.92) -> Placement:
    current = problem.random_initial_placement()
    if number_of_neighbours(problem) == 0:
        return current
    current_value = problem.score(current)
    best, best_value = current, current_value
    temperature = initial_temperature

    for _ in range(max_iterations):
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
