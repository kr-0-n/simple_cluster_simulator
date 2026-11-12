"""
The control loop of the simulated cluster: every tick the pods that are not running are
scheduled with the selected algorithm, and the resulting placement is evaluated. Every
`reoptimize_interval` ticks the algorithm also runs when no pod is pending, to improve the
placement of the running pods (like the Optimize round of the reference scheduler).
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
                 metrics: MetricsSink, evaluation_budget: int = 2000, reoptimize_interval: int = 0):
        self.cluster = cluster
        self.algorithm = get_algorithm(algorithm.name)
        self.algorithm_params = algorithm.params
        self.penalties = penalties
        self.rng = rng
        self.metrics = metrics
        self.evaluation_budget = evaluation_budget
        self.reoptimize_interval = reoptimize_interval

    def evaluator(self) -> Evaluator:
        cluster = self.cluster
        return Evaluator(cluster.network, cluster.pods, self.penalties,
                         crash_rates=cluster.crash_rates(self.penalties.floating_average_window),
                         previous=dict(cluster.placement))

    def tick(self):
        cluster, metrics = self.cluster, self.metrics
        metrics.record("nodes_online", cluster.network.number_of_nodes())
        metrics.record("links_online", cluster.network.number_of_edges())
        metrics.record("pods_online", len(cluster.running_pod_ids()))

        evaluator = self.evaluator()
        placement = cluster.placement
        step = cluster.clock.step
        pending = cluster.pending_pod_ids()
        reoptimize = (not pending and self.reoptimize_interval > 0 and step > 0
                      and step % self.reoptimize_interval == 0 and cluster.running_pod_ids())
        if cluster.network.number_of_nodes() == 0:
            if pending:
                log.debug("step %d: no nodes available for pods %s", step, pending)
        elif pending or reoptimize:
            log.debug("step %d: %s", step, f"scheduling pods {pending}" if pending else "re-optimising")
            problem = SchedulingProblem(evaluator, self.rng, dict(cluster.placement), pending, self.evaluation_budget)
            start = time.perf_counter()
            placement = self.algorithm(problem, **self.algorithm_params)
            metrics.record("schedule_time_ms", (time.perf_counter() - start) * 1000)
            metrics.record("num_eval_func_calls", evaluator.calls)
            metrics.record("unique_evaluations", evaluator.unique_evaluations)
            metrics.record("reoptimization", 0 if pending else 1)

        evaluation = evaluator.evaluate(placement)
        metrics.record("evaluation", evaluation.total)
        for name, value in evaluation.violations.as_dict().items():
            metrics.record(f"{name}_violation", value)
        metrics.record("pod_binding_changed", sum(1 for pod_id in cluster.pods
                                                  if cluster.placement.get(pod_id) != placement.get(pod_id)))
        log.debug("step %d: evaluation %s", cluster.clock.step, evaluation)
        cluster.place(placement)
