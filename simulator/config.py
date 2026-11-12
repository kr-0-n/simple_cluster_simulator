"""
Configuration of simulation runs and experiments.

An experiment file (YAML, see experiments/) describes a matrix of runs:
scenarios x algorithms x seeds, plus shared settings. Scenarios are given either as a list
of topology/deployment pairs or as `topologies` and `deployments` (all combinations).
"""
import dataclasses
import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass(frozen=True)
class Penalties:
    """
    Weights of the evaluation terms (see simulator.evaluator.Violations), the cost of one
    violation each. Defaults and names follow the reference scheduler's config.yaml
    (network_aware_k8s_scheduler/k8_scheduler/common/config.yaml).
    """
    cpu: float = 1_000_000          # one node at 200 % of its CPU (hard constraint)
    memory: float = 1_000_000       # one node at 200 % of its memory (hard constraint)
    label: float = 1_000_000        # one pod on a node matching none of its label selector (hard constraint)
    unconnected_pod: float = 1000   # one network requirement whose pods are not placed or have no path
    unscheduled_pod: float = 1_000_000  # one pod that is not running (simulator only, not in the reference)
    latency: float = 10             # one requirement at 2x its allowed latency
    throughput: float = 10          # one link at 200 % of its capacity
    move_pod: float = 5             # one pod moved to another node
    spread: float = 2               # one pod that would have to move to balance the nodes
    stability: float = 10           # one pod on a node that crashes once per step (averaged over the window)
    floating_average_window: int = 30  # steps (= minutes) over which crashes are averaged


@dataclass(frozen=True)
class MetricsConfig:
    backend: str = "sqlite"         # sqlite | mysql | memory | none
    path: str = "results/simulations.sqlite"   # sqlite only
    host: str = "127.0.0.1"         # mysql only
    user: str = "root"
    password: str = "root"
    database: str = "simulator"
    batch_size: int = 1000          # rows buffered before they are written


@dataclass(frozen=True)
class AlgorithmConfig:
    name: str                                   # key of simulator.algorithms.ALGORITHMS
    params: dict = field(default_factory=dict)  # keyword arguments for the algorithm
    label: Optional[str] = None                 # name in the results, defaults to name

    @property
    def display_name(self) -> str:
        return self.label or self.name

    @staticmethod
    def parse(value) -> "AlgorithmConfig":
        if isinstance(value, AlgorithmConfig):
            return value
        if isinstance(value, str):
            return AlgorithmConfig(value)
        return AlgorithmConfig(value["name"], dict(value.get("params", {})), value.get("label"))


@dataclass(frozen=True)
class SimulationConfig:
    topology: str = "medium"            # scenario name (scenarios/topologies/<name>.yaml) or path
    deployment: str = "medium"          # scenario name (scenarios/deployments/<name>.yaml) or path
    algorithm: AlgorithmConfig = AlgorithmConfig("ant_colony_solve")
    seed: int = 19                      # seeds the chaos monkey and the algorithm
    steps: int = 1440                   # one step == one simulated minute
    repair_interval: int = 5            # repair the network every n steps
    reoptimize_interval: int = 10       # also run the algorithm every n steps when no pod is pending (0 = never)
    evaluation_budget: int = 2000       # evaluations per scheduling decision for the search algorithms
    penalties: Penalties = Penalties()
    metrics: MetricsConfig = MetricsConfig()
    experiment: str = "default"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    scenarios: tuple[tuple[str, str], ...]   # (topology, deployment) pairs
    algorithms: tuple[AlgorithmConfig, ...]
    seeds: tuple[int, ...]
    steps: int = SimulationConfig.steps
    repair_interval: int = SimulationConfig.repair_interval
    reoptimize_interval: int = SimulationConfig.reoptimize_interval
    evaluation_budget: int = SimulationConfig.evaluation_budget
    penalties: Penalties = Penalties()
    metrics: MetricsConfig = MetricsConfig()
    workers: Optional[int] = None       # parallel processes, None = number of CPUs

    def runs(self) -> list[SimulationConfig]:
        return [
            SimulationConfig(topology=topology, deployment=deployment, algorithm=algorithm, seed=seed,
                             steps=self.steps, repair_interval=self.repair_interval,
                             reoptimize_interval=self.reoptimize_interval, evaluation_budget=self.evaluation_budget,
                             penalties=self.penalties, metrics=self.metrics, experiment=self.name)
            for (topology, deployment), algorithm, seed
            in itertools.product(self.scenarios, self.algorithms, self.seeds)
        ]


def _as_tuple(value) -> tuple:
    return tuple(value) if isinstance(value, (list, tuple)) else (value,)


def _parse_scenario(value) -> tuple[str, str]:
    if isinstance(value, dict):
        return value["topology"], value["deployment"]
    if isinstance(value, str) and "+" in value:
        topology, deployment = value.split("+")
        return topology.strip(), deployment.strip()
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return tuple(value)
    raise ValueError(f"invalid scenario {value!r}, use 'topology + deployment' or {{topology: .., deployment: ..}}")


def _build(cls, values: Optional[dict]):
    values = values or {}
    known = {f.name for f in dataclasses.fields(cls)}
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"unknown {cls.__name__} settings: {sorted(unknown)}")
    return cls(**values)


def experiment_from_dict(data: dict[str, Any]) -> ExperimentConfig:
    data = dict(data)
    try:
        if "scenarios" in data:
            scenarios = tuple(_parse_scenario(s) for s in data.pop("scenarios"))
        else:
            scenarios = tuple(itertools.product(_as_tuple(data.pop("topologies")), _as_tuple(data.pop("deployments"))))
        return ExperimentConfig(
            name=data.pop("name"),
            scenarios=scenarios,
            algorithms=tuple(AlgorithmConfig.parse(a) for a in _as_tuple(data.pop("algorithms"))),
            seeds=_as_tuple(data.pop("seeds")),
            penalties=_build(Penalties, data.pop("penalties", None)),
            metrics=_build(MetricsConfig, data.pop("metrics", None)),
            **data,
        )
    except KeyError as e:
        raise ValueError(f"experiment is missing the setting {e}") from None
    except TypeError as e:
        raise ValueError(f"invalid experiment: {e}") from None


def load_experiment(path) -> ExperimentConfig:
    with open(Path(path)) as f:
        return experiment_from_dict(yaml.safe_load(f))
