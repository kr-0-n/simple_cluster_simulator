# Simulator
The simulator will help to select an algorithm: it simulates a Kubernetes-like edge cluster
whose nodes, links and pods fail randomly, lets a scheduling algorithm place the pods, and
records how good the placements are.

## Setup
```sh
pip install -r requirements.txt     # or: pip install -e .[dev]
python -m pytest                    # tests
```

## Usage
```sh
python -m simulator run                                   # medium scenario, ant colony, seed 19, 1440 steps
python -m simulator run --topology small --deployment small --algorithm simulated_annealing_solve \
                        --param max_iterations=500 --steps 200 --metrics memory
python -m simulator experiment experiments/compare_algorithms.yaml           # all runs in parallel
python -m simulator experiment experiments/compare_algorithms.yaml --steps 60 --workers 4
python -m simulator validate --combinations               # check all scenario files
python -m simulator generate-topology --base-stations 6 --clients 20 --satellites 8 -o scenarios/topologies/large.yaml
python -m simulator draw --topology small --deployment small -o graph.dot && neato -Tpng graph.dot -o graph.png
python -m simulator --log-level DEBUG run --steps 5 --metrics none           # see every step
```
An experiment prints a summary table (mean ± std over the seeds per scenario and algorithm).

### Experiments
An experiment file (`experiments/*.yaml`) describes `scenarios × algorithms × seeds`:
```yaml
name: compare_algorithms
scenarios: [small + small, medium + medium]   # topology + deployment
algorithms:
  - simulated_annealing_solve
  - {name: ant_colony_solve, label: aco_4_ants, params: {ants: 4}}
seeds: [1, 2, 3]
steps: 1440
repair_interval: 5
penalties: {latency: 20, move_pod: 5}          # weight overrides, see simulator/config.py
metrics: {backend: sqlite, path: results/compare_algorithms.sqlite}
workers: 8                                     # default: number of CPUs
```

### Metrics
Backends: `sqlite` (default, `results/*.sqlite`), `mysql` (`docker compose -f deploy/compose.yml up -d`,
database `simulator`), `memory`, `none`. Every backend stores

* `runs(run_id, experiment, topology, deployment, algorithm, seed, config, started_at, finished_at, status, summary)` –
  `config` and `summary` are JSON
* `metrics(run_id, step, time, metric, value)`

```sql
-- e.g. as Grafana query (MySQL data source)
SELECT time, value FROM metrics WHERE run_id = '...' AND metric = 'evaluation' ORDER BY step;
```
Metrics per step: `evaluation` (the weighted score) and the unweighted terms `cpu_violation`, `memory_violation`,
`latency_violation`, `throughput_violation`, `unconnected_violation`, `label_violation`, `spread_violation`,
`move_violation`, `stability_violation`, plus `nodes_online`, `links_online`, `pods_online`,
`pod_binding_changed` (pods whose node changed); when pods were scheduled: `num_eval_func_calls`,
`unique_evaluations`, `schedule_time_ms`.

## How it works
Every step:
1. `Kubernetes.tick` – pods that are not running are scheduled by the algorithm, the new placement is evaluated.
2. every `repair_interval` steps the network is repaired (failed nodes and links come back).
3. the chaos monkey fails every node, link and running pod with probability `1 - stability`.

The **evaluation** (lower is better, `simulator/evaluator.py`) is a port of the evaluator of the reference
scheduler (`network_aware_k8s_scheduler/k8_scheduler/scheduler/evaluator/problem.go`), so the simulator
optimises the same objective. Every term is measured in "violations" (1 = one clear violation) and
weighted with `Penalties` (defaults = the reference `config.yaml`):

| Weight | Term (1 unit =) |
|---|---|
| `cpu`, `memory` | per node: `(load - capacity) / capacity`, 1 = one node at 200 % |
| `latency` | per requirement over its limit: `(path latency - allowed) / max(allowed, 1)` |
| `throughput` | per link: `max(0, demand - capacity) / capacity`; a flow that does not fit is reduced to the remaining capacity on the following links |
| `unconnected_pod` | requirements whose pods are not both placed or have no path |
| `label` | per pod: fraction of its label selector the node does not have |
| `spread` | minimum number of pods to move so every node runs floor(P/N)..ceil(P/N) pods |
| `move_pod` | pods moved away from their node |
| `stability` | per pod: crashes of its node in the last `floating_average_window` steps / window |

Paths are the fewest-hop paths over the online links (ties broken by node id), flows claim link capacity
in pod id order. `tests/test_reference_parity.py` compiles the reference evaluator
(`tools/reference_eval`, needs Go and the reference checkout) and checks that both compute the same
values on random scenarios. Deviation: the reference's stability term is placement independent and
currently always 0; here it counts the pods on recently crashed nodes.

Like the reference algorithm, the search algorithms place every pod on an online node (a step moves one
pod to another node, pods are never unassigned).

## Layout
| Path | Purpose |
|---|---|
| `simulator/__main__.py` | command line interface |
| `simulator/config.py` | `SimulationConfig`, `ExperimentConfig`, `Penalties`, `MetricsConfig` |
| `simulator/model.py` | `Node`, `Link`, `Pod`, `Topology`, `Deployment`, `Placement` (pod → node) |
| `simulator/scenarios.py` | loading, validating and generating scenarios |
| `simulator/simulation.py` | one run (`Simulation`) |
| `simulator/experiments.py` | parallel experiments and the summary table |
| `simulator/cluster.py` | online nodes/links, placement and failure log of a running simulation |
| `simulator/chaos.py` | the chaos monkey |
| `simulator/kubernetes.py` | the control loop that calls the scheduler |
| `simulator/evaluator.py` | the penalty function (cached, shortest paths precomputed) |
| `simulator/algorithms/` | scheduling algorithms, `ALGORITHMS` maps names to functions |
| `simulator/metrics.py` | metric backends |
| `simulator/visualizer.py` | dot export |
| `scenarios/` | topologies and deployments (YAML, format in `scenarios/README.md`) |
| `experiments/` | experiment files |
| `simmath/` | linear functions and min-plus / max-plus operations (network calculus, not used by the evaluator yet) |
| `tests/` | pytest tests |

### Adding an algorithm
Write a function `my_solve(problem: SchedulingProblem, **params) -> Placement` (see
`simulator/algorithms/common.py` for the problem and the neighbourhood helpers), add it to `ALGORITHMS`
in `simulator/algorithms/__init__.py` and use it by name. Use only `problem.rng` for randomness so runs stay
reproducible, and `problem.score(placement)` to evaluate.
