"""
One simulation run.

Every step: the pods that are not running are scheduled, every `repair_interval` steps the
network is repaired, then the chaos monkey fails nodes, links and pods.
"""
import dataclasses
import logging
import time
import uuid
from dataclasses import dataclass
from random import Random
from typing import Optional

from simulator.chaos import ChaosMonkey
from simulator.clock import Clock
from simulator.cluster import Cluster
from simulator.config import SimulationConfig
from simulator.kubernetes import Kubernetes
from simulator.metrics import MetricsSink, Recorder, make_recorder
from simulator.scenarios import load_scenario

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunResult:
    run_id: str
    config: SimulationConfig
    status: str
    duration_s: float
    summary: dict


def make_run_id(config: SimulationConfig) -> str:
    parts = [config.experiment, config.topology, config.deployment, config.algorithm.display_name, f"s{config.seed}"]
    return "_".join(str(part).replace("/", "-") for part in parts) + "_" + uuid.uuid4().hex[:6]


class Simulation:
    def __init__(self, config: SimulationConfig, recorder: Optional[Recorder] = None, run_id: Optional[str] = None,
                 create_schema: bool = True):
        """
        recorder:      where metrics go, default: a new recorder for config.metrics (closed after the run)
        create_schema: create the metrics tables (set False if prepare_storage was already called)
        """
        self.config = config
        self.run_id = run_id or make_run_id(config)
        self.recorder = recorder if recorder is not None else make_recorder(config.metrics, create_schema)
        self._owns_recorder = recorder is None
        self.topology, self.deployment = load_scenario(config.topology, config.deployment)
        self.clock = Clock()
        self.cluster = Cluster(self.topology, self.deployment, self.clock)
        # independent, reproducible random streams (string seeds do not depend on PYTHONHASHSEED)
        self.chaos_monkey = ChaosMonkey(Random(f"chaos-{config.seed}"))
        self.metrics = MetricsSink(self.recorder, self.run_id, self.clock)
        self.kubernetes = Kubernetes(self.cluster, config.algorithm, config.penalties,
                                     Random(f"algorithm-{config.seed}"), self.metrics,
                                     evaluation_budget=config.evaluation_budget,
                                     reoptimize_interval=config.reoptimize_interval)

    def step(self):
        self.kubernetes.tick()
        if self.clock.step % self.config.repair_interval == 0:
            self.cluster.repair()
        self.chaos_monkey.unleash(self.cluster)
        self.clock.tick()

    def run(self) -> RunResult:
        config = self.config
        self.recorder.start_run(self.run_id, {
            "experiment": config.experiment, "topology": config.topology, "deployment": config.deployment,
            "algorithm": config.algorithm.display_name, "seed": config.seed, "config": config.to_dict()})
        log.info("run %s started", self.run_id)
        start = time.perf_counter()
        status = "failed"
        try:
            while self.clock.step < config.steps:
                self.step()
                if self.clock.step % 100 == 0:
                    log.debug("run %s: step %d/%d", self.run_id, self.clock.step, config.steps)
            status = "finished"
        finally:
            duration = time.perf_counter() - start
            summary = self.metrics.summary()
            self.recorder.finish_run(self.run_id, status, summary)
            if self._owns_recorder:
                self.recorder.close()
        log.info("run %s finished in %.1fs, mean evaluation %.1f", self.run_id, duration,
                 summary.get("evaluation", {}).get("mean", float("nan")))
        return RunResult(self.run_id, config, status, duration, summary)


def run_simulation(config: Optional[SimulationConfig] = None, **overrides) -> RunResult:
    """Run one simulation; keyword arguments override fields of the config."""
    return Simulation(dataclasses.replace(config or SimulationConfig(), **overrides)).run()
