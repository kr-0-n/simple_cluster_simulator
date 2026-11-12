"""
Scheduling algorithms.

Every algorithm has the signature
    algorithm(graph, pods=None, debug=False, visualize=False) -> nx.DiGraph
where `pods` is a list of (pod_id, attributes) tuples that have to be scheduled.
It returns the graph with the new assignment ("assign" edges pod -> node).
"""
from k8.algorithms.common import assign_randomly, seed
from k8.algorithms.ant_colony import ant_colony_solve
from k8.algorithms.evolutionary import evolutionary_solve
from k8.algorithms.kubernetes_default import kubernetes_default
from k8.algorithms.perfect import perfect_solve
from k8.algorithms.simulated_annealing import simulated_annealing_solve


def random_solve(graph, pods=None, debug=False, visualize=False):
    """
    Assign every new pod to a random node (modifies the given graph).
    Without pods, one random pod is moved to a random node.
    """
    if pods is None:
        return assign_randomly(graph)
    for pod in pods:
        assign_randomly(graph, pod)
    return graph


ALGORITHMS = {
    algorithm.__name__: algorithm
    for algorithm in [random_solve, perfect_solve, evolutionary_solve, ant_colony_solve,
                      simulated_annealing_solve, kubernetes_default]
}


def get_algorithm(algorithm):
    """
    Resolve an algorithm given by name (see ALGORITHMS) or return the callable itself.
    """
    if callable(algorithm):
        return algorithm
    try:
        return ALGORITHMS[algorithm]
    except KeyError:
        raise ValueError(f"unknown algorithm {algorithm!r}, choose one of {sorted(ALGORITHMS)}") from None


__all__ = ["ALGORITHMS", "get_algorithm", "seed", "random_solve", "perfect_solve", "evolutionary_solve",
           "ant_colony_solve", "simulated_annealing_solve", "kubernetes_default"]
