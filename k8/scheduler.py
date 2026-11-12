import networkx as nx

from k8.algorithms import get_algorithm


class Scheduler:
    def __init__(self, algorithm):
        self.selected_algorithm = get_algorithm(algorithm)

    def schedule(self, pods: list[tuple], graph: nx.DiGraph) -> nx.DiGraph:
        """
        Schedule the given (unassigned) pods. Returns the new graph.
        """
        return self.selected_algorithm(graph, pods, debug=False, visualize=False)

    def optimize(self, graph: nx.DiGraph) -> nx.DiGraph:
        """
        Re-optimise the placement of the already scheduled pods.
        """
        return self.selected_algorithm(graph, debug=False, visualize=False)
