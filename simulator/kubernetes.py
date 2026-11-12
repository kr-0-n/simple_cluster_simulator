"""
The control loop of the simulated cluster: every tick the pods that are not running are
scheduled with the selected algorithm, and the resulting placement is evaluated.
"""
import logging
import time
from random import Random

from simulator.algorithms import SchedulingProblem, get_algorithm
from simulator.cluster import Cluster
from simulator.config import AlgorithmConfig, Penalties
from simulator.evaluator import Evaluator
from simulator.metrics import MetricsSink

log = logging.getLogger(__name__)


class Kubernetes:
    def __init__(self, cluster: Cluster, algorithm: AlgorithmConfig, penalties: Penalties, rng: Random,
                 metrics: MetricsSink):
        self.cluster = cluster
        self.algorithm = get_algorithm(algorithm.name)
        self.algorithm_params = algorithm.params
        self.penalties = penalties
        self.rng = rng
        self.metrics = metrics

    def evaluator(self) -> Evaluator:
        cluster = self.cluster
        return Evaluator(cluster.network, cluster.pods, self.penalties,
                         crash_rates=cluster.crash_rates(self.penalties.stability_window),
                         previous=dict(cluster.placement))

    def tick(self):
        cluster, metrics = self.cluster, self.metrics
        metrics.record("nodes_online", cluster.network.number_of_nodes())
        metrics.record("links_online", cluster.network.number_of_edges())
        metrics.record("pods_online", len(cluster.running_pod_ids()))

        evaluator = self.evaluator()
        placement = cluster.placement
        pending = cluster.pending_pod_ids()
        if pending and cluster.network.number_of_nodes() > 0:
            log.debug("step %d: scheduling pods %s", cluster.clock.step, pending)
            problem = SchedulingProblem(evaluator, self.rng, dict(cluster.placement), pending)
            start = time.perf_counter()
            placement = self.algorithm(problem, **self.algorithm_params)
            metrics.record("schedule_time_ms", (time.perf_counter() - start) * 1000)
            metrics.record("num_eval_func_calls", evaluator.calls)
            metrics.record("unique_evaluations", evaluator.unique_evaluations)
        elif pending:
            log.debug("step %d: no nodes available for pods %s", cluster.clock.step, pending)

        evaluation = evaluator.evaluate(placement)
        metrics.record("evaluation", evaluation.total)
        for name, value in evaluation.components().items():
            metrics.record(f"{name}_penalty", value)
        metrics.record("pod_binding_changed", sum(1 for pod_id in cluster.pods
                                                  if cluster.placement.get(pod_id) != placement.get(pod_id)))
        log.debug("step %d: evaluation %s", cluster.clock.step, evaluation)
        cluster.place(placement)
