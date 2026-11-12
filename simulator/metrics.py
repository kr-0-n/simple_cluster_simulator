"""
Recording of time series metrics.

All backends use the same long format:
    runs(run_id, experiment, topology, deployment, algorithm, seed, config, started_at, finished_at, status, summary)
    metrics(run_id, step, time, metric, value)
config and summary are JSON. Rows are written in batches.

Example query (Grafana / SQL):
    SELECT time, value FROM metrics WHERE run_id = '...' AND metric = 'evaluation' ORDER BY step
"""
import json
import logging
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from simulator.clock import Clock
from simulator.config import MetricsConfig

log = logging.getLogger(__name__)


class Recorder:
    """Discards everything. Base class of the backends."""

    def start_run(self, run_id: str, info: dict):
        pass

    def record(self, run_id: str, step: int, time: datetime, metric: str, value: float):
        pass

    def finish_run(self, run_id: str, status: str, summary: dict):
        pass

    def close(self):
        pass


class MemoryRecorder(Recorder):
    """Keeps everything in memory (for tests and interactive use)."""

    def __init__(self):
        self.runs: dict[str, dict] = {}
        self.rows: list[tuple] = []

    def start_run(self, run_id, info):
        self.runs[run_id] = {"info": info, "status": "running"}

    def record(self, run_id, step, time, metric, value):
        self.rows.append((run_id, step, time, metric, value))

    def finish_run(self, run_id, status, summary):
        self.runs[run_id].update(status=status, summary=summary)

    def series(self, run_id: str, metric: str) -> list[tuple[int, float]]:
        return [(step, value) for r, step, _, m, value in self.rows if r == run_id and m == metric]


class _SqlRecorder(Recorder):
    placeholder = "?"
    schema: list[str] = []

    def __init__(self, connection, batch_size: int, create_schema: bool = True):
        self.connection = connection
        self.batch_size = batch_size
        self.buffer: list[tuple] = []
        if create_schema:
            cursor = self.connection.cursor()
            for statement in self.schema:
                cursor.execute(statement)
            self.connection.commit()

    def _execute(self, query: str, params: tuple):
        query = query.replace("?", self.placeholder)
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        self.connection.commit()

    def start_run(self, run_id, info):
        self._execute(
            "INSERT INTO runs (run_id, experiment, topology, deployment, algorithm, seed, config, started_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, info["experiment"], info["topology"], info["deployment"], info["algorithm"], info["seed"],
             json.dumps(info["config"]), datetime.now().isoformat(timespec="seconds"), "running"))

    def record(self, run_id, step, time, metric, value):
        self.buffer.append((run_id, step, time.strftime("%Y-%m-%d %H:%M:%S"), metric, value))
        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        if not self.buffer:
            return
        query = "INSERT INTO metrics (run_id, step, time, metric, value) VALUES (?, ?, ?, ?, ?)".replace("?", self.placeholder)
        cursor = self.connection.cursor()
        cursor.executemany(query, self.buffer)
        self.connection.commit()
        self.buffer = []

    def finish_run(self, run_id, status, summary):
        self.flush()
        self._execute("UPDATE runs SET finished_at = ?, status = ?, summary = ? WHERE run_id = ?",
                      (datetime.now().isoformat(timespec="seconds"), status, json.dumps(summary), run_id))

    def close(self):
        self.flush()
        self.connection.close()


class SqliteRecorder(_SqlRecorder):
    schema = [
        "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, experiment TEXT, topology TEXT, deployment TEXT, "
        "algorithm TEXT, seed INTEGER, config TEXT, started_at TEXT, finished_at TEXT, status TEXT, summary TEXT)",
        "CREATE TABLE IF NOT EXISTS metrics (run_id TEXT, step INTEGER, time TEXT, metric TEXT, value REAL)",
        "CREATE INDEX IF NOT EXISTS metrics_run ON metrics (run_id, metric, step)",
    ]

    def __init__(self, path: str, batch_size: int = 1000, create_schema: bool = True):
        """
        Parallel runs write to the same file: prepare the database once (create_schema=True,
        see prepare_storage) and open it in the workers with create_schema=False.
        """
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=120)
        if create_schema:
            connection.execute("PRAGMA journal_mode=WAL")  # readers and one writer at the same time
        super().__init__(connection, batch_size, create_schema)


class MySqlRecorder(_SqlRecorder):
    placeholder = "%s"
    schema = [
        "CREATE TABLE IF NOT EXISTS runs (run_id VARCHAR(191) PRIMARY KEY, experiment VARCHAR(191), "
        "topology VARCHAR(191), deployment VARCHAR(191), algorithm VARCHAR(191), seed INT, config TEXT, "
        "started_at VARCHAR(32), finished_at VARCHAR(32), status VARCHAR(16), summary TEXT)",
        "CREATE TABLE IF NOT EXISTS metrics (run_id VARCHAR(191), step INT, time DATETIME, metric VARCHAR(64), "
        "value DOUBLE, INDEX metrics_run (run_id, metric, step))",
    ]

    def __init__(self, host: str, user: str, password: str, database: str, batch_size: int = 1000,
                 create_schema: bool = True):
        import mysql.connector  # only needed for this backend

        if not database.replace("_", "").isalnum():
            raise ValueError(f"invalid database name {database!r}")
        if create_schema:
            admin = mysql.connector.connect(host=host, user=user, password=password)
            try:
                admin.cursor().execute(f"CREATE DATABASE IF NOT EXISTS `{database}`")
            finally:
                admin.close()
        connection = mysql.connector.connect(host=host, user=user, password=password, database=database)
        super().__init__(connection, batch_size, create_schema)


def make_recorder(config: MetricsConfig, create_schema: bool = True) -> Recorder:
    if config.backend == "sqlite":
        return SqliteRecorder(config.path, config.batch_size, create_schema)
    if config.backend == "mysql":
        return MySqlRecorder(config.host, config.user, config.password, config.database, config.batch_size, create_schema)
    if config.backend == "memory":
        return MemoryRecorder()
    if config.backend == "none":
        return Recorder()
    raise ValueError(f"unknown metrics backend {config.backend!r} (sqlite, mysql, memory, none)")


def prepare_storage(config: MetricsConfig):
    """Create the database and tables (once, before parallel runs open the storage)."""
    make_recorder(config, create_schema=True).close()


@dataclass
class Statistic:
    count: int = 0
    total: float = 0
    minimum: float = math.inf
    maximum: float = -math.inf
    last: float = math.nan

    def add(self, value: float):
        self.count += 1
        self.total += value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        self.last = value

    @property
    def mean(self) -> float:
        return self.total / self.count if self.count else math.nan


@dataclass
class MetricsSink:
    """The metrics of one run: forwards to a recorder and keeps summary statistics."""
    recorder: Recorder
    run_id: str
    clock: Clock
    statistics: dict[str, Statistic] = field(default_factory=dict)

    def record(self, metric: str, value: float):
        self.statistics.setdefault(metric, Statistic()).add(value)
        self.recorder.record(self.run_id, self.clock.step, self.clock.time, metric, value)

    def summary(self) -> dict[str, dict[str, float]]:
        return {name: {"mean": s.mean, "min": s.minimum, "max": s.maximum, "total": s.total, "count": s.count}
                for name, s in self.statistics.items()}
