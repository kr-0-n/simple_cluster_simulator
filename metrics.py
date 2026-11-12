"""
Records time series metrics into a MySQL database (one database per run, one table per metric).
Recording is a no-op unless initialize() was called with enabled=True.
"""
import re

import Time as time

database_connection = None
database_cursor = None
name = None

record_metrics = False

_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def _check_identifier(identifier: str) -> str:
    # Table/database names cannot be passed as query parameters, so validate them instead.
    if not _IDENTIFIER.match(identifier):
        raise ValueError(f"invalid metric/database name: {identifier!r}")
    return identifier


def update_metric(metric: str, value: float):
    """
    Append a value for the current simulated time to the given metric.
    """
    if not record_metrics: return
    table = _check_identifier(metric)
    database_cursor.execute(
        f"INSERT INTO `{table}` (time, `{table}`) VALUES (%s, %s);",
        (time.sql_time(time.current_time()), value),
    )
    database_connection.commit()


def create_metric(metric: str):
    """
    Create the table for a new metric.
    """
    if not record_metrics: return
    table = _check_identifier(metric)
    database_cursor.execute(f"CREATE TABLE `{table}` (time DATETIME NOT NULL, `{table}` FLOAT);")
    database_connection.commit()


def initialize(algorithm_name: str, run: int, enabled: bool, host: str, user: str, password: str):
    """
    Create the database for this run and connect to it.
    """
    global record_metrics, name, database_connection, database_cursor
    record_metrics = enabled
    if not record_metrics: return

    import mysql.connector  # only needed when metrics are recorded

    name = _check_identifier(f"k8_simulation_{run}_{algorithm_name}")
    print(name)
    admin_connection = mysql.connector.connect(host=host, user=user, password=password)
    try:
        admin_connection.cursor().execute(f"CREATE DATABASE `{name}`")
    finally:
        admin_connection.close()

    database_connection = mysql.connector.connect(host=host, user=user, password=password, database=name)
    database_cursor = database_connection.cursor()


def close():
    """
    Close the database connection (if any) and stop recording.
    """
    global record_metrics, database_connection, database_cursor
    record_metrics = False
    if database_connection is not None:
        database_connection.close()
    database_connection = None
    database_cursor = None
