"""
Command line interface:

    python -m simulator run --topology medium --deployment medium --algorithm ant_colony_solve --seed 19
    python -m simulator experiment experiments/compare_algorithms.yaml --workers 8
    python -m simulator validate
    python -m simulator generate-topology --base-stations 6 --clients 20 -o scenarios/topologies/big.yaml
    python -m simulator draw --topology small --deployment small -o graph.dot
"""
import argparse
import dataclasses
import logging
import sys
from random import Random

import yaml

from simulator.algorithms import ALGORITHMS, SchedulingProblem, get_algorithm
from simulator.clock import Clock
from simulator.cluster import Cluster
from simulator.config import AlgorithmConfig, MetricsConfig, Penalties, SimulationConfig, load_experiment
from simulator.evaluator import Evaluator
from simulator.experiments import run_experiment, summary_table
from simulator.log import configure_logging
from simulator.scenarios import (
    SCENARIO_DIR,
    ScenarioError,
    deployment_from_dict,
    generate_edge_topology,
    load_scenario,
    read_scenario_file,
    topology_from_dict,
    validate_combination,
    validate_deployment,
    validate_topology,
)
from simulator.simulation import Simulation
from simulator.visualizer import write_dot

log = logging.getLogger("simulator")
DEFAULT = SimulationConfig()


def _params(values: list[str]) -> dict:
    params = {}
    for value in values or []:
        key, _, raw = value.partition("=")
        if not raw:
            raise SystemExit(f"--param expects key=value, got {value!r}")
        params[key] = yaml.safe_load(raw)
    return params


def _add_scenario_arguments(parser):
    parser.add_argument("--topology", default=DEFAULT.topology, help="name in scenarios/topologies or path")
    parser.add_argument("--deployment", default=DEFAULT.deployment, help="name in scenarios/deployments or path")
    parser.add_argument("--algorithm", default=DEFAULT.algorithm.name, choices=sorted(ALGORITHMS))
    parser.add_argument("--param", action="append", metavar="KEY=VALUE", help="algorithm parameter (repeatable)")
    parser.add_argument("--seed", type=int, default=DEFAULT.seed)


def cmd_run(args):
    metrics = dataclasses.replace(MetricsConfig(), backend=args.metrics, path=args.metrics_path)
    config = SimulationConfig(topology=args.topology, deployment=args.deployment,
                              algorithm=AlgorithmConfig(args.algorithm, _params(args.param)), seed=args.seed,
                              steps=args.steps, repair_interval=args.repair_interval, metrics=metrics,
                              experiment=args.experiment)
    result = Simulation(config).run()
    print(f"run {result.run_id} {result.status} in {result.duration_s:.1f}s")
    for metric in ("evaluation", "pods_online", "pod_binding_changed", "num_eval_func_calls"):
        if metric in result.summary:
            s = result.summary[metric]
            print(f"  {metric:22s} mean {s['mean']:10.2f}  min {s['min']:10.2f}  max {s['max']:10.2f}  total {s['total']:12.2f}")


def cmd_experiment(args):
    experiment = load_experiment(args.file)
    if args.steps is not None:
        experiment = dataclasses.replace(experiment, steps=args.steps)
    if args.metrics is not None:
        experiment = dataclasses.replace(experiment, metrics=dataclasses.replace(experiment.metrics, backend=args.metrics))
    results = run_experiment(experiment, workers=args.workers, log_level=args.log_level)
    print(summary_table(results))
    if experiment.metrics.backend == "sqlite":
        print(f"\nmetrics written to {experiment.metrics.path} (experiment {experiment.name!r})")


def cmd_validate(args):
    errors = 0

    def report(what, issues):
        nonlocal errors
        errors += sum(1 for i in issues if i.level == "error")
        status = "ok" if not issues else "\n    " + "\n    ".join(map(str, issues))
        print(f"{what}: {status}")

    topologies = args.topology or sorted(p.stem for p in (SCENARIO_DIR / "topologies").glob("*.yaml"))
    deployments = args.deployment or sorted(p.stem for p in (SCENARIO_DIR / "deployments").glob("*.yaml"))
    loaded_topologies, loaded_deployments = {}, {}
    for reference in topologies:
        try:
            loaded_topologies[reference] = topology_from_dict(*read_scenario_file(reference, "topologies"))
            report(f"topology {reference}", validate_topology(loaded_topologies[reference]))
        except ScenarioError as e:
            errors += 1
            print(f"topology {reference}: error: {e}")
    for reference in deployments:
        try:
            loaded_deployments[reference] = deployment_from_dict(*read_scenario_file(reference, "deployments"))
            report(f"deployment {reference}", validate_deployment(loaded_deployments[reference]))
        except ScenarioError as e:
            errors += 1
            print(f"deployment {reference}: error: {e}")
    if args.combinations:
        for t, topology in loaded_topologies.items():
            for d, deployment in loaded_deployments.items():
                report(f"scenario {t} + {d}", validate_combination(topology, deployment))
    return 1 if errors else 0


def cmd_generate_topology(args):
    data = generate_edge_topology(args.name, args.base_stations, args.clients, args.satellites, args.seed)
    topology = topology_from_dict(args.name, data)
    issues = [i for i in validate_topology(topology) if i.level == "error"]
    if issues:
        raise SystemExit(f"generated topology is invalid: {issues}")
    text = yaml.safe_dump(data, sort_keys=False, default_flow_style=None, width=120)
    if args.output:
        with open(args.output, "w") as f:
            f.write(text)
        print(f"written {len(topology.nodes)} nodes and {len(topology.links)} links to {args.output}")
    else:
        print(text)


def cmd_draw(args):
    topology, deployment = load_scenario(args.topology, args.deployment)
    cluster = Cluster(topology, deployment, Clock())
    evaluator = Evaluator(cluster.network, cluster.pods, Penalties(), previous=cluster.placement)
    algorithm = get_algorithm(args.algorithm)
    problem = SchedulingProblem(evaluator, Random(f"algorithm-{args.seed}"), dict(cluster.placement), cluster.pending_pod_ids())
    placement = algorithm(problem, **_params(args.param))
    evaluation = evaluator.evaluate(placement)
    write_dot(args.output, cluster.network, cluster.pods, placement, evaluator,
              title=f"{args.algorithm}: evaluation {evaluation.total}")
    print(f"{evaluation}\nwritten to {args.output} (render with: neato -Tpng {args.output} -o graph.png)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m simulator", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log-level", default="INFO", type=str.upper,
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run one simulation")
    _add_scenario_arguments(run)
    run.add_argument("--steps", type=int, default=DEFAULT.steps)
    run.add_argument("--repair-interval", type=int, default=DEFAULT.repair_interval)
    run.add_argument("--metrics", default=DEFAULT.metrics.backend, choices=["sqlite", "mysql", "memory", "none"])
    run.add_argument("--metrics-path", default=DEFAULT.metrics.path)
    run.add_argument("--experiment", default=DEFAULT.experiment, help="experiment name stored with the run")
    run.set_defaults(func=cmd_run)

    experiment = commands.add_parser("experiment", help="run an experiment file (runs in parallel)")
    experiment.add_argument("file")
    experiment.add_argument("--workers", type=int, help="parallel processes (default: experiment setting or #CPUs)")
    experiment.add_argument("--steps", type=int, help="override the number of steps")
    experiment.add_argument("--metrics", choices=["sqlite", "mysql", "memory", "none"], help="override the backend")
    experiment.set_defaults(func=cmd_experiment)

    validate = commands.add_parser("validate", help="validate scenario files (default: all)")
    validate.add_argument("--topology", action="append")
    validate.add_argument("--deployment", action="append")
    validate.add_argument("--combinations", action="store_true", help="also check every topology/deployment pair")
    validate.set_defaults(func=cmd_validate)

    generate = commands.add_parser("generate-topology", help="generate an edge network topology")
    generate.add_argument("--name", default="generated")
    generate.add_argument("--base-stations", type=int, default=4)
    generate.add_argument("--clients", type=int, default=10)
    generate.add_argument("--satellites", type=int, default=6)
    generate.add_argument("--seed", type=int, default=0)
    generate.add_argument("-o", "--output", help="YAML file (default: print)")
    generate.set_defaults(func=cmd_generate_topology)

    draw = commands.add_parser("draw", help="schedule a deployment once and write it as a dot file")
    _add_scenario_arguments(draw)
    draw.add_argument("-o", "--output", default="graph.dot")
    draw.set_defaults(func=cmd_draw)

    args = parser.parse_args(argv)
    args.log_level = getattr(logging, args.log_level)
    configure_logging(args.log_level)
    try:
        return args.func(args) or 0
    except (ScenarioError, ValueError) as e:
        log.error("%s", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
