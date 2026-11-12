import dataclasses
import sqlite3
from random import Random

from simulator.__main__ import main
from simulator.chaos import ChaosMonkey
from simulator.clock import Clock
from simulator.cluster import Cluster
from simulator.config import AlgorithmConfig, ExperimentConfig, MetricsConfig, SimulationConfig
from simulator.experiments import run_experiment, summary_table
from simulator.metrics import MemoryRecorder
from simulator.model import Deployment, Topology
from simulator.scenarios import load_topology
from simulator.simulation import Simulation
from tests.helpers import link, node, pod

SMALL = SimulationConfig(topology="small", deployment="small", algorithm=AlgorithmConfig("simulated_annealing_solve"),
                         steps=30, metrics=MetricsConfig(backend="memory"))


def rows(config):
    recorder = MemoryRecorder()
    Simulation(config, recorder=recorder, run_id="run").run()
    return [(step, metric, value) for _, step, _, metric, value in recorder.rows if metric != "schedule_time_ms"]


def test_runs_are_reproducible():
    assert rows(SMALL) == rows(SMALL)
    assert rows(SMALL) != rows(dataclasses.replace(SMALL, seed=SMALL.seed + 1))


def test_every_step_records_the_evaluation():
    recorded = rows(SMALL)
    assert [step for step, metric, _ in recorded if metric == "evaluation"] == list(range(SMALL.steps))


def test_failures_are_recorded_when_they_happen():
    topology = Topology("t", (node(1, stability=0.0), node(2)), (link(1, 2), link(2, 1)))
    cluster = Cluster(topology, Deployment("d", (pod(10), pod(11, stability=0.0))), Clock())
    cluster.place({10: 1, 11: 2})
    cluster.clock.step = 3
    ChaosMonkey(Random(0)).unleash(cluster)
    assert cluster.failures.nodes == {1: [3]}
    assert cluster.failures.pods == {11: [3]}
    assert cluster.placement == {10: None, 11: None}  # 10 lost its node, 11 crashed
    assert cluster.node_ids() == [2] and cluster.network.number_of_edges() == 0

    cluster.repair()
    assert sorted(cluster.node_ids()) == [1, 2] and cluster.network.number_of_edges() == 2
    assert cluster.crash_rates(window=20) == {2: 0.0, 1: 1 / 20}


def test_sqlite_storage(tmp_path):
    path = tmp_path / "results.sqlite"
    config = dataclasses.replace(SMALL, steps=5, metrics=MetricsConfig(backend="sqlite", path=str(path)))
    result = Simulation(config).run()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT status, algorithm FROM runs WHERE run_id = ?", (result.run_id,)).fetchone() == \
            ("finished", "simulated_annealing_solve")
        steps = db.execute("SELECT step FROM metrics WHERE run_id = ? AND metric = 'evaluation' ORDER BY step",
                           (result.run_id,)).fetchall()
        assert [s for (s,) in steps] == [0, 1, 2, 3, 4]


def test_parallel_experiment(tmp_path):
    path = tmp_path / "experiment.sqlite"
    experiment = ExperimentConfig(name="test", scenarios=(("small", "small"), ("mini", "mini")),
                                  algorithms=(AlgorithmConfig("random_solve"), AlgorithmConfig("kubernetes_default")),
                                  seeds=(1, 2), steps=10, metrics=MetricsConfig(backend="sqlite", path=str(path)))
    results = run_experiment(experiment, workers=4)
    assert len(results) == 8 and all(r.status == "finished" for r in results)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM runs WHERE status = 'finished'").fetchone() == (8,)
    table = summary_table(results)
    assert "kubernetes_default" in table and "mini" in table


def test_cli(tmp_path, capsys):
    assert main(["validate"]) == 0
    assert main(["run", "--topology", "small", "--deployment", "small", "--steps", "3", "--metrics", "none",
                 "--algorithm", "ant_colony_solve", "--param", "ants=3"]) == 0
    assert main(["run", "--topology", "small", "--deployment", "medium", "--metrics", "none"]) == 2
    topology_file = tmp_path / "generated.yaml"
    assert main(["generate-topology", "--base-stations", "3", "--clients", "4", "-o", str(topology_file)]) == 0
    assert len(load_topology(str(topology_file)).nodes) == 3 + 4 + 6
    assert main(["draw", "--topology", "small", "--deployment", "small", "-o", str(tmp_path / "g.dot")]) == 0
    assert "node1" in (tmp_path / "g.dot").read_text()


def test_reoptimisation_runs_on_the_interval():
    config = dataclasses.replace(SMALL, steps=40, reoptimize_interval=5)
    recorder = MemoryRecorder()
    Simulation(config, recorder=recorder, run_id="run").run()
    runs = dict(recorder.series("run", "reoptimization"))
    reoptimised = [step for step, value in runs.items() if value == 1]
    assert reoptimised and all(step % 5 == 0 and step > 0 for step in reoptimised)
    pending = dict(recorder.series("run", "unscheduled_violation"))
    assert all(pending[step] == 0 for step in reoptimised)  # only when nothing is pending

    recorder = MemoryRecorder()
    Simulation(dataclasses.replace(config, reoptimize_interval=0), recorder=recorder, run_id="run").run()
    assert all(value == 0 for _, value in recorder.series("run", "reoptimization"))
