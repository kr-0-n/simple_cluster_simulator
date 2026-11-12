"""
Scheduling algorithms.

Every algorithm has the signature
    algorithm(problem: SchedulingProblem, **params) -> Placement
It may move existing pods and has to decide where the new pods (problem.new_pod_ids) run.
Its keyword parameters can be set per experiment (see AlgorithmConfig.params).
"""
from simulator.algorithms.ant_colony import ant_colony_solve
from simulator.algorithms.basic import kubernetes_default, perfect_solve, random_solve
from simulator.algorithms.common import SchedulingProblem
from simulator.algorithms.metaheuristics import evolutionary_solve, simulated_annealing_solve

ALGORITHMS = {
    algorithm.__name__: algorithm
    for algorithm in [random_solve, perfect_solve, kubernetes_default, evolutionary_solve,
                      simulated_annealing_solve, ant_colony_solve]
}


def get_algorithm(name: str):
    try:
        return ALGORITHMS[name]
    except KeyError:
        raise ValueError(f"unknown algorithm {name!r}, choose one of {sorted(ALGORITHMS)}") from None


__all__ = ["ALGORITHMS", "SchedulingProblem", "get_algorithm", *ALGORITHMS]
