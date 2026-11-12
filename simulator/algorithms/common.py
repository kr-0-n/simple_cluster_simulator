"""
The scheduling problem and helpers shared by the algorithms.

A solution is a Placement (dict pod -> node or None). The neighbourhood of a placement
consists of all placements where exactly one pod is (re)assigned to an online node:
#pods * #nodes neighbours (including the placement itself, when a pod is "moved" to its
own node). Like the mutation of the reference scheduler, pods are never unassigned.
"""
from dataclasses import dataclass, field
from random import Random

from simulator.evaluator import Evaluator
from simulator.model import NodeId, Placement, Pod, PodId

GOOD_ENOUGH = 0.1  # a placement scoring below this is accepted immediately (as in the reference)
DEFAULT_BUDGET = 2000


@dataclass
class SchedulingProblem:
    evaluator: Evaluator            # evaluates placements (cached)
    rng: Random                     # the only source of randomness for the algorithm
    current: Placement              # placement before this decision (new pods: None)
    new_pod_ids: list[PodId]        # the pods that have to be scheduled (empty: re-optimise the placement)
    budget: int = DEFAULT_BUDGET    # evaluations the search algorithms may use for this decision
    pods: dict[PodId, Pod] = field(init=False)
    pod_ids: list[PodId] = field(init=False)
    node_ids: list[NodeId] = field(init=False)

    def __post_init__(self):
        self.pods = self.evaluator.pods
        self.pod_ids = self.evaluator.pod_ids
        self.node_ids = self.evaluator.node_ids

    def score(self, placement: Placement) -> float:
        return self.evaluator.score(placement)

    @property
    def evaluations(self) -> int:
        return self.evaluator.calls

    def exhausted(self) -> bool:
        """True when the evaluation budget is used up."""
        return self.evaluator.calls >= self.budget

    def greedy_initial_placement(self) -> Placement:
        """
        The current placement with every new pod on its best node: pods with a label selector
        first (like the reference), each on the node that gives the lowest score given the pods
        placed before it (ties: first node). Costs #new pods * #nodes evaluations; it always
        completes, even if that exceeds the budget.
        """
        placement = dict(self.current)
        order = sorted(self.new_pod_ids, key=lambda pod_id: (not self.pods[pod_id].label_selector, pod_id))
        for pod_id in order:
            best_node, best_value = None, None
            for node_id in self.node_ids:
                placement[pod_id] = node_id
                value = self.score(placement)
                if best_value is None or value < best_value:
                    best_node, best_value = node_id, value
            placement[pod_id] = best_node
        return placement

    def random_initial_placement(self) -> Placement:
        """The current placement with every new pod assigned to a random node."""
        placement = dict(self.current)
        for pod_id in self.new_pod_ids:
            placement[pod_id] = self.rng.choice(self.node_ids)
        return placement


def number_of_neighbours(problem: SchedulingProblem) -> int:
    return len(problem.pod_ids) * len(problem.node_ids)


def neighbour_at_index(problem: SchedulingProblem, placement: Placement, index: int) -> Placement:
    """
    The neighbour with the given index, without generating all neighbours:
    pod number index // #nodes is assigned to node number index % #nodes.
    """
    if not 0 <= index < number_of_neighbours(problem):
        raise IndexError(f"neighbour index {index} out of range")
    num_nodes = len(problem.node_ids)
    neighbour = dict(placement)
    neighbour[problem.pod_ids[index // num_nodes]] = problem.node_ids[index % num_nodes]
    return neighbour


def random_neighbour(problem: SchedulingProblem, placement: Placement) -> Placement:
    return neighbour_at_index(problem, placement, problem.rng.randint(0, number_of_neighbours(problem) - 1))


def neighbours(problem: SchedulingProblem, placement: Placement) -> list[Placement]:
    """All neighbours, in index order."""
    result = []
    for pod_id in problem.pod_ids:
        for node_id in problem.node_ids:
            neighbour = dict(placement)
            neighbour[pod_id] = node_id
            result.append(neighbour)
    return result
