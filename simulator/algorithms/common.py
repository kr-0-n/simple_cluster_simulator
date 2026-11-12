"""
The scheduling problem and helpers shared by the algorithms.

A solution is a Placement (dict pod -> node or None). The neighbourhood of a placement
consists of all placements where exactly one pod is moved to a node or unassigned:
#pods * (#nodes + 1) neighbours.
"""
from dataclasses import dataclass, field
from random import Random

from simulator.evaluator import Evaluator
from simulator.model import NodeId, Placement, Pod, PodId


@dataclass
class SchedulingProblem:
    evaluator: Evaluator            # evaluates placements (cached)
    rng: Random                     # the only source of randomness for the algorithm
    current: Placement              # placement before this decision (new pods: None)
    new_pod_ids: list[PodId]        # the pods that have to be scheduled
    pods: dict[PodId, Pod] = field(init=False)
    pod_ids: list[PodId] = field(init=False)
    node_ids: list[NodeId] = field(init=False)

    def __post_init__(self):
        self.pods = self.evaluator.pods
        self.pod_ids = self.evaluator.pod_ids
        self.node_ids = self.evaluator.node_ids

    def score(self, placement: Placement) -> float:
        return self.evaluator.score(placement)

    def random_initial_placement(self) -> Placement:
        """The current placement with every new pod assigned to a random node."""
        placement = dict(self.current)
        for pod_id in self.new_pod_ids:
            placement[pod_id] = self.rng.choice(self.node_ids)
        return placement


def number_of_neighbours(problem: SchedulingProblem) -> int:
    return len(problem.pod_ids) * (len(problem.node_ids) + 1)


def neighbour_at_index(problem: SchedulingProblem, placement: Placement, index: int) -> Placement:
    """
    The neighbour with the given index, without generating all neighbours.
    For each pod there are (#nodes + 1) neighbours; the first one unassigns the pod.
    """
    if not 0 <= index < number_of_neighbours(problem):
        raise IndexError(f"neighbour index {index} out of range")
    slots = len(problem.node_ids) + 1
    pod_id = problem.pod_ids[index // slots]
    node_index = index % slots - 1
    neighbour = dict(placement)
    neighbour[pod_id] = None if node_index == -1 else problem.node_ids[node_index]
    return neighbour


def random_neighbour(problem: SchedulingProblem, placement: Placement) -> Placement:
    return neighbour_at_index(problem, placement, problem.rng.randint(0, number_of_neighbours(problem) - 1))


def neighbours(problem: SchedulingProblem, placement: Placement) -> list[Placement]:
    """All neighbours, in index order."""
    result = []
    for pod_id in problem.pod_ids:
        for node_id in [None] + problem.node_ids:
            neighbour = dict(placement)
            neighbour[pod_id] = node_id
            result.append(neighbour)
    return result
