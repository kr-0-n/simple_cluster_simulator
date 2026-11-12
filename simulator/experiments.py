"""
Runs an experiment (a matrix of simulation runs) in parallel processes and summarises it.
"""
import logging
import math
import os
import statistics
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Optional

from simulator.config import ExperimentConfig, SimulationConfig
from simulator.log import configure_logging
from simulator.metrics import prepare_storage
from simulator.scenarios import load_scenario
from simulator.simulation import RunResult, Simulation

log = logging.getLogger(__name__)

# (column title, metric, statistic) shown in the summary table
SUMMARY_COLUMNS = [
    ("evaluation", "evaluation", "mean"),
    ("pods online", "pods_online", "mean"),
    ("binding changes", "pod_binding_changed", "total"),
    ("evaluations", "num_eval_func_calls", "total"),
    ("schedule ms", "schedule_time_ms", "mean"),
]


def _run(config: SimulationConfig) -> RunResult:
    return Simulation(config, create_schema=False).run()


def run_experiment(experiment: ExperimentConfig, workers: Optional[int] = None,
                   log_level: int = logging.INFO) -> list[RunResult]:
    runs = experiment.runs()
    # fail fast on invalid scenarios, before any process is started
    for topology, deployment in {(run.topology, run.deployment) for run in runs}:
        load_scenario(topology, deployment)

    prepare_storage(experiment.metrics)

    workers = workers or experiment.workers or os.cpu_count() or 1
    workers = min(workers, len(runs))
    log.info("experiment %s: %d runs on %d worker(s)", experiment.name, len(runs), workers)

    results, failures = [], []
    if workers == 1:
        for config in runs:
            try:
                results.append(_run(config))
            except Exception:
                log.exception("run %s/%s/%s seed %s failed", config.topology, config.deployment,
                              config.algorithm.display_name, config.seed)
                failures.append(config)
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=configure_logging, initargs=(log_level,)) as pool:
            futures = {pool.submit(_run, config): config for config in runs}
            for done, future in enumerate(as_completed(futures), 1):
                config = futures[future]
                try:
                    results.append(future.result())
                    log.info("%d/%d runs done", done, len(runs))
                except Exception:
                    log.exception("run %s/%s/%s seed %s failed", config.topology, config.deployment,
                                  config.algorithm.display_name, config.seed)
                    failures.append(config)
    if failures:
        log.error("%d of %d runs failed", len(failures), len(runs))
    return results


def summary_table(results: list[RunResult]) -> str:
    """Mean ± standard deviation over the seeds, per topology / deployment / algorithm."""
    groups = defaultdict(list)
    for result in results:
        c = result.config
        groups[(c.topology, c.deployment, c.algorithm.display_name)].append(result)

    header = ["topology", "deployment", "algorithm", "runs"] + [title for title, _, _ in SUMMARY_COLUMNS] + ["runtime s"]
    rows = []
    for key in sorted(groups):
        group = groups[key]
        row = [*key, str(len(group))]
        for _, metric, statistic in SUMMARY_COLUMNS:
            row.append(_mean_std([r.summary.get(metric, {}).get(statistic, math.nan) for r in group]))
        row.append(_mean_std([r.duration_s for r in group]))
        rows.append(row)

    widths = [max(len(str(cell)) for cell in column) for column in zip(header, *rows)]
    line = lambda cells: "  ".join(str(cell).ljust(width) for cell, width in zip(cells, widths))
    return "\n".join([line(header), line("-" * w for w in widths), *map(line, rows)])


def _mean_std(values: list[float]) -> str:
    values = [v for v in values if not math.isnan(v)]
    if not values:
        return "-"
    mean = statistics.fmean(values)
    if len(values) == 1:
        return f"{mean:.1f}"
    return f"{mean:.1f} ± {statistics.stdev(values):.1f}"
