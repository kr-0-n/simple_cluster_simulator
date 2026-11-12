# Simulator
The simulator will help to select an algorithm

## Run
```sh
pip install -r requirements.txt
docker compose -f deploy/compose.yml up -d   # MySQL + Grafana, only needed with conf.enable_metrics = True
python simulation.py      # one run with the settings from conf.py
python experiments.py     # one run per entry in experiments.experiments
python draw_example.py    # schedule the small scenario once and write graph.dot
```

## Layout
| File | Purpose |
|---|---|
| `conf.py` | settings: scenario, algorithm (by name), seeds, steps, penalties, database |
| `scenarios.py` | network topologies and deployments |
| `simulation.py` | the simulation loop (schedule → repair → chaos monkey → next step) |
| `network_administration.py` | builds the network graph, repairs it, records node failures |
| `chaos_monkey.py` | randomly deletes nodes, links and pods according to their stability |
| `k8/kubernetes_wrapper.py` | the cluster: finds pods that are not running and lets the scheduler place them |
| `k8/scheduler.py` | wraps the selected algorithm |
| `k8/algorithms/` | scheduling algorithms, one module each; `ALGORITHMS` maps names to functions |
| `k8/evaluator.py` | penalty function for a placement |
| `metrics.py` | writes time series to MySQL (one database per run) |
| `Time.py` | simulated time (1 step = 1 minute) |
| `utils.py` | graph queries |
| `visualizer.py` | dot export |
| `simmath/` | linear functions and min-plus / max-plus operations (network calculus) |
