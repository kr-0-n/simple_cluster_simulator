"""
Simple baselines: random placement, brute force and an imitation of the default kube-scheduler.
"""
import itertools
import logging
import math
from collections import defaultdict

from simulator.algorithms.common import SchedulingProblem
from simulator.model import Placement

log = logging.getLogger(__name__)


def random_solve(problem: SchedulingProblem) -> Placement:
    """Assign every new pod to a random node."""
    return problem.random_initial_placement()


def perfect_solve(problem: SchedulingProblem, max_combinations: int = 10_000_000) -> Placement:
    """
    Brute force: try every assignment of all pods to nodes (#nodes ^ #pods combinations).
    Stops early when a placement with evaluation 0 is found. Like the other algorithms (and
    the reference scheduler) it only considers placements that assign every pod: the
    evaluator does not penalise unassigned pods without network requirements.
    """
    combinations = len(problem.node_ids) ** len(problem.pod_ids)
    if combinations > max_combinations:
        raise ValueError(f"perfect_solve would have to check {combinations} combinations (max_combinations={max_combinations})")
    log.debug("checking %d ^ %d assignments", len(problem.node_ids), len(problem.pod_ids))
    best, best_value = dict(problem.current), math.inf
    for nodes in itertools.product(problem.node_ids, repeat=len(problem.pod_ids)):
        placement = dict(zip(problem.pod_ids, nodes))
        value = problem.score(placement)
        if value < best_value:
            best, best_value = placement, value
            if value == 0:
                break
    return best


def kubernetes_default(problem: SchedulingProblem) -> Placement:
    """
    Imitation of the default kube-scheduler for the new pods (existing pods are not moved):
    filter nodes (labelSelector, NodeResourceFit), score them (even spread of pods) and
    pick the node with the highest score.
    """
    placement = dict(problem.current)
    nodes = problem.evaluator.nodes
    cpu_load, mem_load, pod_count = defaultdict(float), defaultdict(float), defaultdict(int)
    for pod_id, node_id in placement.items():
        if node_id is not None:
            cpu_load[node_id] += problem.pods[pod_id].cpu
            mem_load[node_id] += problem.pods[pod_id].mem
            pod_count[node_id] += 1

    for pod_id in problem.new_pod_ids:
        pod = problem.pods[pod_id]
        ## Stage 1: Filtering
        feasible = [node_id for node_id in problem.node_ids
                    if set(pod.label_selector) <= set(nodes[node_id].labels)
                    and cpu_load[node_id] + pod.cpu <= nodes[node_id].cpu
                    and mem_load[node_id] + pod.mem <= nodes[node_id].mem]
        if not feasible:
            log.debug("no feasible node for pod %s", pod_id)
            continue
        ## Stage 2: Scoring - aim for an even distribution (counting the new pod)
        avg_pods_per_node = (sum(pod_count.values()) + 1) / len(problem.node_ids)
        scores = [max(0, avg_pods_per_node - pod_count[node_id]) for node_id in feasible]
        ## Stage 3: Selection (the first node with the highest score)
        selected = feasible[scores.index(max(scores))]
        placement[pod_id] = selected
        cpu_load[selected] += pod.cpu
        mem_load[selected] += pod.mem
        pod_count[selected] += 1
    return placement
