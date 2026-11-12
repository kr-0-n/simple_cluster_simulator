# Simple Network Simulator

A simulator for choosing a scheduling algorithm for compute clusters in dynamic environments

It simulates an edge cluster in which nodes, network links and pods fail at random. Every simulated
minute a scheduling algorithm places the pods that are not running. Each placement is scored with the
**same evaluation function as the real scheduler**. Runs are reproducible, run in parallel, and store
their time series in SQLite or MySQL, so algorithms and parameters can be compared over many seeds.

```
$ python -m simulator experiment experiments/compare_algorithms.yaml --steps 120
topology  deployment  algorithm                  runs  evaluation              pods online  binding changes  evaluations         schedule ms    runtime s
--------  ----------  -------------------------  ----  ----------------------  -----------  ---------------  ------------------  -------------  ----------
medium    medium      ant_colony_solve           5     77756.9 ± 28092.0       24.1 ± 0.1   185.0 ± 24.0     113039.6 ± 5765.2   444.3 ± 109.4  25.9 ± 6.6
medium    medium      evolutionary_solve         5     53877.2 ± 50601.0       24.2 ± 0.1   160.8 ± 24.3     112000.0 ± 20396.1  173.4 ± 32.8   9.7 ± 1.1
medium    medium      kubernetes_default         5     102865.8 ± 57431.8      24.1 ± 0.1   102.8 ± 9.7      0.0 ± 0.0           0.3 ± 0.1      0.5 ± 0.2
medium    medium      random_solve               5     13431692.7 ± 1642641.3  24.2 ± 0.1   91.0 ± 7.7       0.0 ± 0.0           0.0 ± 0.0      0.3 ± 0.2
medium    medium      simulated_annealing_solve  5     49799.9 ± 47119.6       24.1 ± 0.0   393.2 ± 39.1     119200.0 ± 8555.7   499.7 ± 12.8   30.1 ± 1.8
...
```

**Contents**

1. [Setup](#1-setup)
2. [Usage](#2-usage)
3. [Architecture](#3-architecture)
4. [Extending the simulator](#4-extending-the-simulator)
5. [Known limitations and modelling notes](#5-known-limitations-and-modelling-notes)
6. [Development](#6-development)

---

## 1. Setup

### Requirements

| What                      | Needed for                                      | Version                      |
| ------------------------- | ----------------------------------------------- | ---------------------------- |
| Python                    | everything                                      | ≥ 3.10 (developed with 3.14) |
| Graphviz (`dot`, `neato`) | rendering the `.dot` files of `draw`            | any                          |
| Docker + Compose          | the MySQL metrics backend and Grafana           | any                          |
| Go                        | the parity test against the reference evaluator | ≥ 1.23                       |

Only Python is required. Everything else is optional.

### Install

```sh
git clone <this repository> simple_network_simulator
cd simple_network_simulator
python -m venv .venv && source .venv/bin/activate

pip install -r requirements.txt     # all dependencies, including pytest, ruff and the MySQL driver
pip install -e .                    # optional: adds the `simulator` command (same as `python -m simulator`)
```

Use an editable install (`-e`), or run from the repository root. The scenario files in `scenarios/` are
found relative to the source tree.

### Check the installation

```sh
python -m pytest                    # ~70 tests, a few seconds
python -m simulator validate        # all scenario files must report "ok"
python -m simulator run --topology small --deployment small --steps 50 --metrics memory
```

### Optional: MySQL and Grafana

The default metrics backend is SQLite and needs no setup. To use MySQL (for example to watch runs in
Grafana):

```sh
docker compose -f deploy/compose.yml up -d    # MySQL :3306 (root/root), Adminer :8000, Grafana :3000
python -m simulator run --metrics mysql        # creates the database "simulator" and its tables
```

In Grafana (<http://localhost:3000>, admin/admin), add a **MySQL data source** with host `db:3306`,
user `root`, password `root`, database `simulator`. Example panel query:

```sql
SELECT time, value AS evaluation FROM metrics
WHERE run_id = '<run id>' AND metric = 'evaluation' ORDER BY step
```

Simulated time starts at **2020-01-01 00:00**, one step = one minute. Set the dashboard time range
to that day. The connection settings are in `MetricsConfig` (`simulator/config.py`) and the
`metrics:` block of experiment files.

---

## 2. Usage

Everything is available through one command line interface:

```
python -m simulator [--log-level DEBUG|INFO|WARNING|ERROR] <command> ...
```

| Command             | Purpose                                                             |
| ------------------- | ------------------------------------------------------------------- |
| `run`               | run one simulation                                                  |
| `experiment FILE`   | run an experiment (many runs in parallel) and print a summary table |
| `validate`          | check scenario files                                                |
| `generate-topology` | generate an edge network topology                                   |
| `draw`              | schedule a deployment once and write the result as a Graphviz file  |

### 2.1 Single runs

```sh
python -m simulator run                                   # medium scenario, ant colony, seed 19, 1440 steps
python -m simulator run --topology small --deployment small \
       --algorithm simulated_annealing_solve --param initial_temperature=500 --budget 5000 \
       --seed 3 --steps 200 --metrics memory
```

| Option                       | Default                      | Meaning                                                                         |
| ---------------------------- | ---------------------------- | ------------------------------------------------------------------------------- |
| `--topology`, `--deployment` | `medium`, `medium`           | scenario name (`scenarios/<kind>/<name>.yaml`) or path to a YAML file           |
| `--algorithm`                | `ant_colony_solve`           | see [algorithms](#35-algorithms)                                                |
| `--param KEY=VALUE`          | –                            | algorithm parameter, repeatable; values are parsed as YAML (`3`, `0.5`, `true`) |
| `--seed`                     | `19`                         | seeds the chaos monkey and the algorithm                                        |
| `--steps`                    | `1440`                       | simulated minutes (1440 = one day)                                              |
| `--repair-interval`          | `5`                          | failed nodes and links come back every n steps                                  |
| `--reoptimize-interval`      | `10`                         | also run the algorithm every n steps when no pod is pending (0 = never)         |
| `--budget`                   | `2000`                       | evaluations per scheduling decision for the search algorithms                   |
| `--metrics`                  | `sqlite`                     | `sqlite`, `mysql`, `memory` (discarded after the run) or `none`                 |
| `--metrics-path`             | `results/simulations.sqlite` | SQLite file                                                                     |
| `--experiment`               | `default`                    | experiment name stored with the run                                             |

The run prints its summary:

```
run default_small_small_simulated_annealing_solve_s19_d30d2e finished in 0.0s
  evaluation             mean 1368121.46  min      18.67  max 3200008.00  total 136812146.33
  pods_online            mean       6.75  min       0.00  max       7.00  total       675.00
  ...
```

### 2.2 Experiments

An experiment runs every combination of **scenarios × algorithms × seeds** in parallel processes.
Example files are in `experiments/`:

| File                      | Content                                                                  |
| ------------------------- | ------------------------------------------------------------------------ |
| `default.yaml`            | one run with the default setup (ant colony on the medium scenario)       |
| `compare_algorithms.yaml` | five algorithms on the small and medium scenario, 5 seeds each (50 runs) |
| `ant_colony_tuning.yaml`  | three parameter variants of the ant colony, with weight overrides        |

```yaml
name: compare_algorithms # stored with every run
scenarios: # topology + deployment pairs ...
  - small + small
  - medium + medium
# ... or all combinations of:
# topologies: [small, medium]
# deployments: [small]
algorithms:
  - random_solve # by name ...
  - { name: ant_colony_solve, label: aco_4_ants, params: { ants: 4 } } # ... or with parameters and a label
seeds: [1, 2, 3, 4, 5]
steps: 1440 # optional, default 1440
repair_interval: 5 # optional, default 5
reoptimize_interval: 10 # optional, default 10 (0 = only schedule pending pods)
evaluation_budget: 2000 # optional, evaluations per decision for the search algorithms
penalties: { latency: 20 } # optional, overrides of the evaluation weights
metrics: { backend: sqlite, path: results/compare_algorithms.sqlite } # optional
workers: 8 # optional, default: number of CPUs
```

```sh
python -m simulator experiment experiments/compare_algorithms.yaml
python -m simulator experiment experiments/compare_algorithms.yaml --steps 60 --workers 4 --metrics none
```

`--steps`, `--workers` and `--metrics` override the file. The table shows the mean ± standard
deviation over the seeds of:

| Column          | Metric                | Statistic per run                       |
| --------------- | --------------------- | --------------------------------------- |
| evaluation      | `evaluation`          | mean over the steps                     |
| pods online     | `pods_online`         | mean over the steps                     |
| binding changes | `pod_binding_changed` | total                                   |
| evaluations     | `num_eval_func_calls` | total (how much work the algorithm did) |
| schedule ms     | `schedule_time_ms`    | mean wall time per scheduling decision  |
| runtime s       | –                     | wall time of the run                    |

A failing run is logged and does not stop the other runs.

### 2.3 Results

Every backend stores two tables:

```
runs(run_id, experiment, topology, deployment, algorithm, seed, config, started_at, finished_at, status, summary)
metrics(run_id, step, time, metric, value)
```

- `config` (JSON) is the complete `SimulationConfig` of the run, including weights and parameters.
- `summary` (JSON) holds mean / min / max / total / count of every metric.
- `status` is `running`, `finished` or `failed`.
- The run id is `<experiment>_<topology>_<deployment>_<algorithm label>_s<seed>_<random suffix>`.

Metrics recorded every step:

| Metric                                                                                                                                                                                    | Meaning                                                                                |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `evaluation`                                                                                                                                                                              | weighted score of the placement after the step's scheduling decision (lower is better) |
| `cpu_violation`, `memory_violation`, `latency_violation`, `throughput_violation`, `unconnected_violation`, `label_violation`, `spread_violation`, `move_violation`, `stability_violation`, `unscheduled_violation` | the unweighted terms of the evaluation, see [3.4](#34-evaluation)                      |
| `nodes_online`, `links_online`, `pods_online`                                                                                                                                             | state of the cluster at the start of the step                                          |
| `pod_binding_changed`                                                                                                                                                                     | pods whose node changed in this step                                                   |

Only recorded in steps where the algorithm ran: `num_eval_func_calls` (evaluations requested),
`unique_evaluations` (evaluations actually computed; the rest came from the cache), `schedule_time_ms`,
`reoptimization` (1 = the algorithm ran because of the re-optimisation interval, 0 = because pods were pending).

Example queries (SQLite: `sqlite3 results/compare_algorithms.sqlite`):

```sql
-- mean evaluation per algorithm
SELECT r.algorithm, AVG(m.value) FROM metrics m JOIN runs r USING (run_id)
WHERE r.experiment = 'compare_algorithms' AND m.metric = 'evaluation' GROUP BY r.algorithm;

-- which terms dominate for one algorithm
SELECT m.metric, AVG(m.value) FROM metrics m JOIN runs r USING (run_id)
WHERE r.algorithm = 'simulated_annealing_solve' AND m.metric LIKE '%_violation' GROUP BY m.metric;
```

### 2.4 Scenarios

A scenario is a **topology** (`scenarios/topologies/*.yaml`: nodes and directed links) combined with a
**deployment** (`scenarios/deployments/*.yaml`: pods, their resources, label selectors and network
requirements). The file format is documented in [`scenarios/README.md`](scenarios/README.md).

| Name     | Topology                                                              | Deployment                                                            |
| -------- | --------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `mini`   | 3 nodes, slow links                                                   | 2 pods talking to each other                                          |
| `small`  | 4 nodes, asymmetric links, one SSD node                               | 7 pods in a ring, one needs the SSD                                   |
| `medium` | edge network: 4 base stations, 10 camera clients, 6 satellite clients | 25 pods: data collection, P2P streaming, video streaming, web servers |

```sh
python -m simulator validate                         # every file on its own
python -m simulator validate --combinations          # also every topology/deployment pair
python -m simulator generate-topology --base-stations 6 --clients 20 --satellites 8 --seed 1 \
       --name large -o scenarios/topologies/large.yaml
```

Scenarios are validated whenever they are loaded. Errors stop the run; warnings are logged. Errors include
duplicate ids, unknown references, and label selectors no node can satisfy. Warnings include
unreachable nodes and more demand than capacity.

### 2.5 Visualisation

```sh
python -m simulator draw --topology small --deployment small --algorithm kubernetes_default -o graph.dot
neato -Tpng graph.dot -o graph.png
```

Nodes are blue boxes, sized by their resources. Pods are green ellipses connected to their node.
Network links are drawn thicker the more throughput they have and turn red when overloaded. A pod's
network requirements are dashed green edges. The ant colony can also dump its search graph:
`--param dot_file=aco.dot`.

### 2.6 Logging

`--log-level INFO` (default) logs the start and end of runs. `DEBUG` logs every scheduling decision,
evaluation and failure. `WARNING` only shows problems (for example scenario warnings).

```sh
python -m simulator --log-level DEBUG run --topology small --deployment small --steps 5 --metrics none
```

### 2.7 Python API

```python
from simulator import AlgorithmConfig, Penalties, Simulation, SimulationConfig
from simulator.metrics import MemoryRecorder

config = SimulationConfig(topology="small", deployment="small", steps=200, seed=3,
                          algorithm=AlgorithmConfig("simulated_annealing_solve", {"initial_temperature": 500}),
                          evaluation_budget=5000, reoptimize_interval=1, penalties=Penalties(latency=20))
recorder = MemoryRecorder()
result = Simulation(config, recorder=recorder).run()
print(result.summary["evaluation"]["mean"])
print(recorder.series(result.run_id, "pods_online")[:10])     # [(step, value), ...]
```

Experiments from Python: the worker processes re-import your script, so put the call in a script
file behind a main guard:

```python
from simulator.config import load_experiment
from simulator.experiments import run_experiment, summary_table

if __name__ == "__main__":
    results = run_experiment(load_experiment("experiments/compare_algorithms.yaml"), workers=4)
    print(summary_table(results))
```

---

## 3. Architecture

### 3.1 Overview

```
                 experiment.yaml ──▶ ExperimentConfig ──runs()──▶ [SimulationConfig, ...]
                                                                        │ ProcessPoolExecutor
                                                                        ▼ (one process per run)
 scenarios/*.yaml ──load_scenario()──▶ Topology, Deployment ──▶ ┌──────────────── Simulation ────────────────┐
                    (validated)                                 │  Clock          Cluster                     │
                                                                │                 ├ network (online nodes/links)
                                                                │                 ├ placement (pod → node)    │
                                                                │                 └ failure log               │
                                                                │  ChaosMonkey(rng "chaos-<seed>")            │
                                                                │  Kubernetes(algorithm, rng "algorithm-<seed>")
                                                                │     │  per step: Evaluator ─▶ SchedulingProblem
                                                                │     │            ─▶ algorithm ─▶ Placement     │
                                                                │  MetricsSink ──▶ Recorder (sqlite/mysql/...) │
                                                                └─────────────────────────────────────────────┘
                                                                        │ RunResult (summary)
                                                                        ▼
                                                                 summary_table()
```

There is no module-level state. Everything a run needs is owned by its `Simulation` object, so runs
are independent and can run in parallel.

### 3.2 Simulation loop

`Simulation.step()` runs the following, once per simulated minute:

1. **`Kubernetes.tick()`**
   1. Record `nodes_online`, `links_online` and `pods_online`.
   2. Create an `Evaluator` for the current network. It gets the crash rates of the nodes and the
      current placement (to detect moves).
   3. If at least one node is online and pods are **pending** (not running), or the step is a
      multiple of `reoptimize_interval`: build a `SchedulingProblem` with the evaluation budget and
      call the algorithm. It returns a new placement for all pods.
   4. Evaluate the new placement, record the score and every term, and apply it to the cluster.
2. **Repair** every `repair_interval` steps: failed nodes and links come back as in the topology.
3. **Chaos monkey**: every online node, online link and running pod fails with probability
   `1 − stability`. The failure is recorded with the current step.
   - A failed node takes its pods down (they become pending).
   - A failed pod becomes pending.
   - Pending pods are scheduled again in the next step.
4. **`Clock.tick()`**.

A pod is either _placed_ (runs on an online node) or _pending_ (`None` in the placement). The algorithm
runs when something is pending and every `reoptimize_interval` steps (like the Optimize round of the
reference scheduler). It may move running pods, which costs a move penalty.

### 3.3 Modules

| Module                                   | Responsibility                                                                                                                   |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `simulator/__main__.py`                  | command line interface                                                                                                           |
| `simulator/config.py`                    | `SimulationConfig`, `ExperimentConfig`, `AlgorithmConfig`, `Penalties`, `MetricsConfig`; loading experiment files                |
| `simulator/model.py`                     | immutable data model: `Node`, `Link`, `Pod`, `Connection`, `Topology`, `Deployment`, `Placement = dict[pod id, node id or None]` |
| `simulator/scenarios.py`                 | loading, validating and generating scenario files                                                                                |
| `simulator/simulation.py`                | `Simulation` (one run), run ids, `RunResult`                                                                                     |
| `simulator/cluster.py`                   | `Cluster`: network graph of the online nodes and links, placement, `FailureLog`, repair                                          |
| `simulator/chaos.py`                     | `ChaosMonkey`                                                                                                                    |
| `simulator/kubernetes.py`                | `Kubernetes`: the control loop that calls the algorithm and records the evaluation                                               |
| `simulator/evaluator.py`                 | `Evaluator`, `Violations`, `Evaluation`: the objective function                                                                  |
| `simulator/algorithms/`                  | `SchedulingProblem`, neighbourhood helpers (`common.py`), the algorithms, `ALGORITHMS` registry                                  |
| `simulator/metrics.py`                   | recorders (`SqliteRecorder`, `MySqlRecorder`, `MemoryRecorder`, `Recorder`) and `MetricsSink`                                    |
| `simulator/experiments.py`               | parallel execution of experiments, summary table                                                                                 |
| `simulator/visualizer.py`                | Graphviz export                                                                                                                  |
| `simulator/clock.py`, `simulator/log.py` | simulated time, logging setup                                                                                                    |
| `simmath/`                               | linear functions and min-plus/max-plus operations for network calculus (not used by the evaluator)                               |
| `tools/reference_eval/`                  | Go program that runs the reference evaluator, for the parity test                                                                |
| `scenarios/`, `experiments/`             | data                                                                                                                             |
| `tests/`                                 | pytest tests                                                                                                                     |

The network is a `networkx.DiGraph`. Its vertices are the online node ids (attribute `spec`: `Node`)
and its edges are the online links (attributes `spec`: `Link`, plus `latency` and `throughput`). Pods
are not in the graph. Their placement is a plain dict, which keeps candidate solutions cheap to create
and compare.

### 3.4 Evaluation

`simulator/evaluator.py` is a port of the reference scheduler's evaluator
(`network_aware_k8s_scheduler/k8_scheduler/scheduler/evaluator/problem.go`). The simulator therefore
optimises exactly the objective the real scheduler optimises. Every term is measured in
**violations** (1 = one clear violation of that kind). The score is the sum of the terms, each times
its weight from `Penalties`. The default weights are those of the reference `config.yaml`:

| Term                              | Weight         | 1 unit =                                                                               |
| --------------------------------- | -------------- | -------------------------------------------------------------------------------------- |
| `cpu`, `memory`                   | 1 000 000 each | per node: `(load − capacity) / capacity`, i.e. one node at 200 %                       |
| `label`                           | 1 000 000      | per pod: fraction of its label selector the node does not have                         |
| `unconnected` (`unconnected_pod`) | 1 000          | a network requirement whose pods are not both placed, or have no path                  |
| `latency`                         | 10             | per requirement over its limit: `(path latency − allowed) / max(allowed, 1)`           |
| `throughput`                      | 10             | per link: `max(0, demand − capacity) / capacity`                                       |
| `move` (`move_pod`)               | 5              | a pod moved away from its node                                                         |
| `spread`                          | 2              | pods that would have to move so every node runs ⌊P/N⌋..⌈P/N⌉ of the P placed pods      |
| `stability`                       | 10             | per pod: crashes of its node in the last `floating_average_window` (30) steps / window |
| `unscheduled` (`unscheduled_pod`) | 1 000 000      | a pod that is not running (simulator only)                                             |

Details taken over from the reference:

- Requirements are routed over the **fewest-hop path** of online links. Ties are broken by node id
  (breadth-first search, neighbours in id order).
- Flows claim link capacity in pod id order. A flow that does not fit through a link continues only
  with the link's remaining capacity.
- Two pods on the same node, or both unassigned, need no path.
- The **stability term deliberately differs**. Here it depends on the placement: it counts pods on
  recently crashed nodes. In the reference it is the same for every placement and currently always 0.
- The **`unscheduled` term only exists in the simulator**. The reference penalises a pod that does not
  run only through its network requirements, which made leaving a pod pending far cheaper than any
  hard-constraint violation. Now a pending pod costs as much as a pod on a completely wrong node, which
  cannot run in a real cluster either. The parity test compares the score without this term.

Performance: everything that does not depend on the placement is computed once per evaluator:
label fractions, requirements, and paths (lazily per source node). Evaluations are cached by
placement, so algorithms that revisit placements pay nothing.

`tests/test_reference_parity.py` compiles the Go evaluator and compares all terms and the score on
1800 random placements. `tests/test_evaluator.py` contains ports of the reference's unit tests.

### 3.5 Algorithms

An algorithm is a function `algorithm(problem: SchedulingProblem, **params) -> Placement`. The problem
gives:

- `pod_ids`, `node_ids` and `pods`;
- `current`, the placement before the decision (pending pods are `None`);
- `new_pod_ids`, the pods to schedule;
- `score(placement)`;
- `rng`, the only allowed source of randomness;
- `budget` and `exhausted()`: the evaluation budget of the decision (`evaluation_budget`);
- `greedy_initial_placement()`, the current placement with every new pod on its best node (pods with
  a label selector first; each pod on the node with the lowest score given the pods placed before it).
  It costs #new pods × #nodes evaluations and always completes, even beyond the budget;
- `random_initial_placement()`, the current placement with the new pods on random nodes.

The search algorithms (simulated annealing, evolutionary, ant colony) start from the greedy placement
and search until the budget is used up, so they are compared at the same number of evaluations.
They stop early if a placement scores below 0.1. The baselines (`random_solve`, `kubernetes_default`,
`perfect_solve`) ignore the budget. When no pod is new (re-optimisation), the search starts from the
current placement.

The **neighbourhood** of a placement (`algorithms/common.py`) assigns one pod to one online node.
That gives #pods × #nodes neighbours. As in the reference scheduler's mutation, pods are never
unassigned.

| Algorithm                   | Idea                                                                                                                                                             | Parameters (default)                                                                                                                                                                                                              |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `random_solve`              | new pods on random nodes                                                                                                                                         | –                                                                                                                                                                                                                                 |
| `kubernetes_default`        | imitates kube-scheduler: filter nodes by labels and free resources, prefer nodes with fewer pods; never moves running pods; leaves a pod pending if no node fits | –                                                                                                                                                                                                                                 |
| `perfect_solve`             | brute force over all #nodes^#pods full placements; only for tiny scenarios                                                                                       | `max_combinations` (10 000 000)                                                                                                                                                                                                   |
| `simulated_annealing_solve` | random neighbour, accept worse ones with probability e^(−Δ/T); T falls geometrically over the budget                                                             | `initial_temperature` (1000), `final_temperature` (0.1)                                                                                                                                                                           |
| `evolutionary_solve`        | every survivor creates random neighbours as children, the best children survive; generations until the budget is used                                           | `children_per_parent` (35), `survivors_per_generation` (22)                                                                                                                                                                       |
| `ant_colony_solve`          | ants walk a graph of placements; edge choice ~ pheromone^α · improvement^β; pheromone ~ 1/score; rounds until the budget is used                                 | `ants` (2), `moves_per_ant` (3), `pheromone_evaporation` (0.5), `pheromone_constant` (50000), `initial_pheromone` (0.1), `alpha` (1), `beta` (1), `heuristic_multiplier_for_worse_solutions` (0), `dot_file` (none)              |

### 3.6 Reproducibility

- Each run uses two independent random generators: `Random("chaos-<seed>")` for failures and
  `Random("algorithm-<seed>")` for the algorithm. String seeds do not depend on `PYTHONHASHSEED`, so a
  run gives the same results in every process and on every machine.
- Only `schedule_time_ms` and the runtime vary between identical runs.
- The same seed means the same failures for every algorithm, as long as the algorithms do not change
  which pods are running (the chaos monkey draws one number per running pod).

### 3.7 Metrics pipeline

`Kubernetes` and `Simulation` call `MetricsSink.record(metric, value)`. The sink adds run id, step and
simulated time, keeps the summary statistics and forwards rows to a `Recorder`. SQL recorders buffer
rows and write them in batches (`batch_size`, default 1000). For experiments, the parent process
creates the schema once (`prepare_storage`). The worker processes then only open the database, and
SQLite runs in WAL mode so they can write to one file at the same time.

---

## 4. Extending the simulator

**A new algorithm**

1. Write `def my_solve(problem: SchedulingProblem, my_param: int = 10) -> Placement` in a module under
   `simulator/algorithms/`.
2. Use `problem.rng` for randomness and `problem.score()` to evaluate. The helpers in
   `algorithms/common.py` (`random_neighbour`, `neighbours`, ...) cover the neighbourhood.
3. Add the function to `ALGORITHMS` in `simulator/algorithms/__init__.py`.
4. Use it as `--algorithm my_solve --param my_param=5`, or in an experiment file. The parametrised tests
   in `tests/test_algorithms.py` pick it up automatically: valid placement, deterministic, not better
   than `perfect_solve`.

**A new scenario**: write YAML files (or use `generate-topology`), run `validate --combinations`, and
reference them by name or path.

**A new evaluation term**: add the field to `Violations` and its weight to `Penalties`, compute it in
`Evaluator.violations()` and add a test. Mention it as a deviation from the reference, or add it to the
Go scheduler too (then extend `tools/reference_eval`).

**A new metrics backend**: subclass `Recorder` (or `_SqlRecorder`), and add it to `make_recorder()`
and to the `--metrics` choices.

---

## 5. Known limitations and modelling notes

- **Pending pod or wrong node.** A pending pod and a pod on a completely wrong node both cost 10⁶.
  The search algorithms never leave a pod pending; `kubernetes_default` does. When no valid node exists,
  both pay the same. Compare `evaluation` together with `pods_online`.
- **A pod on a wrong node counts as running.** It is only moved at the next scheduling decision (pending
  pods or the re-optimisation interval), whereas a pending pod is scheduled as soon as a node fits. With
  frequent failures a short `reoptimize_interval` therefore matters: on `small`, simulated annealing
  scores about 1.33M with interval 10 and about 0.80M with interval 1 (`kubernetes_default`: 0.73M,
  with fewer pods running). Every re-optimisation costs a full budget of evaluations.
- **Two unassigned pods count as "same node"** (taken over from the reference): a requirement between
  them is not penalised.
- **Re-optimisation interval.** The reference scheduler optimises in every round in which nothing is
  pending; the simulator does it every `reoptimize_interval` steps (default 10) to keep runs fast.
- **Greedy start beyond the budget.** For very large problems the greedy initial placement alone
  (#new pods × #nodes evaluations) can exceed the budget; the search then stops right after it.
- **Stability** differs from the reference on purpose (see [3.4](#34-evaluation)).
- **Units.** Memory is in abstract units (MiB in the reference) and one step is one minute.
- **Ant colony** deposits pheromone on the shortest path from the root to an ant, not on the path the
  ant walked.
- **`perfect_solve`** refuses problems with more than `max_combinations` placements.
- **MySQL backend** has only been tested against a mocked connector.

---

## 6. Development

```sh
python -m pytest                     # all tests (the parity test is skipped without Go / the reference)
python -m pytest tests/test_evaluator.py -k spread
ruff check .                         # lint (configured in pyproject.toml)
```

| Test file                  | Covers                                                                          |
| -------------------------- | ------------------------------------------------------------------------------- |
| `test_evaluator.py`        | every evaluation term, ports of the reference's tests, caching                  |
| `test_reference_parity.py` | same values as the Go reference evaluator on random scenarios                   |
| `test_algorithms.py`       | all algorithms: valid, deterministic, never better than brute force, parameters |
| `test_scenarios.py`        | shipped scenarios, validation rules, defaults, generator                        |
| `test_simulation.py`       | reproducibility, failure timing, repair, SQLite, parallel experiments, CLI      |

`observations.md` contains notes from earlier experiments.
