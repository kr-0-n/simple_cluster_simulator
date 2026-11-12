"""
Loading, validating and generating scenarios (topologies and deployments).

Scenario files are YAML, see scenarios/README.md for the format. A topology or
deployment is referenced either by name (scenarios/topologies/<name>.yaml,
scenarios/deployments/<name>.yaml) or by a path to a YAML file.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any, Union

import networkx as nx
import yaml

from simulator.model import Connection, Deployment, Link, Node, Pod, Topology

log = logging.getLogger(__name__)

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios"


class ScenarioError(ValueError):
    pass


@dataclass(frozen=True)
class Issue:
    level: str  # "error" or "warning"
    message: str

    def __str__(self):
        return f"{self.level}: {self.message}"


# ---------------------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------------------

def _resolve(reference: Union[str, Path], kind: str) -> Path:
    path = Path(reference)
    if path.suffix in (".yaml", ".yml") or path.exists():
        return path
    path = SCENARIO_DIR / kind / f"{reference}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in (SCENARIO_DIR / kind).glob("*.yaml"))
        raise ScenarioError(f"unknown {kind[:-1]} {reference!r}, available: {available}")
    return path


def read_scenario_file(reference, kind: str) -> tuple[str, dict]:
    path = _resolve(reference, kind)
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("name", path.stem), data


def _with_defaults(entry: dict, defaults: dict, what: str, required: tuple[str, ...]) -> dict:
    values = {**defaults, **entry}
    missing = [key for key in required if key not in values]
    if missing:
        raise ScenarioError(f"{what} is missing {missing}")
    return values


def topology_from_dict(name: str, data: dict[str, Any]) -> Topology:
    defaults = data.get("defaults", {})
    nodes = []
    for entry in data.get("nodes", []):
        v = _with_defaults(entry, defaults.get("node", {}), f"node {entry.get('id')}", ("id", "cpu", "mem", "stability"))
        nodes.append(Node(id=v["id"], cpu=v["cpu"], mem=v["mem"], stability=v["stability"],
                          labels=tuple(v.get("labels", ()))))
    links = []
    for entry in data.get("links", []):
        what = f"link {entry.get('from')}->{entry.get('to')}"
        v = _with_defaults(entry, defaults.get("link", {}), what, ("from", "to", "throughput", "latency", "stability"))
        links.append(Link(v["from"], v["to"], v["throughput"], v["latency"], v["stability"]))
        if v.get("bidirectional", False):
            links.append(Link(v["to"], v["from"], v["throughput"], v["latency"], v["stability"]))
    return Topology(name, tuple(nodes), tuple(links))


def deployment_from_dict(name: str, data: dict[str, Any]) -> Deployment:
    defaults = data.get("defaults", {}).get("pod", {})
    pods = []
    for entry in data.get("pods", []):
        v = _with_defaults(entry, defaults, f"pod {entry.get('id')}", ("id", "cpu", "mem", "stability"))
        network = []
        for c in v.get("network", []):
            if not {"to", "latency", "throughput"} <= set(c):
                raise ScenarioError(f"pod {v['id']}: connection {c} needs to, latency and throughput")
            network.append(Connection(c["to"], c["latency"], c["throughput"]))
        pods.append(Pod(id=v["id"], cpu=v["cpu"], mem=v["mem"], stability=v["stability"],
                        network=tuple(network), label_selector=tuple(v.get("labelSelector", ()))))
    return Deployment(name, tuple(pods))


def load_topology(reference) -> Topology:
    name, data = read_scenario_file(reference, "topologies")
    topology = topology_from_dict(name, data)
    _raise_or_log(validate_topology(topology), f"topology {name}")
    return topology


def load_deployment(reference) -> Deployment:
    name, data = read_scenario_file(reference, "deployments")
    deployment = deployment_from_dict(name, data)
    _raise_or_log(validate_deployment(deployment), f"deployment {name}")
    return deployment


def load_scenario(topology_reference, deployment_reference) -> tuple[Topology, Deployment]:
    topology = load_topology(topology_reference)
    deployment = load_deployment(deployment_reference)
    _raise_or_log(validate_combination(topology, deployment), f"scenario {topology.name}/{deployment.name}")
    return topology, deployment


def _raise_or_log(issues: list[Issue], what: str):
    errors = [i for i in issues if i.level == "error"]
    for issue in issues:
        if issue.level == "warning":
            log.warning("%s: %s", what, issue.message)
    if errors:
        raise ScenarioError(f"{what} is invalid:\n  " + "\n  ".join(i.message for i in errors))


# ---------------------------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------------------------

def _duplicates(values) -> list:
    seen, duplicates = set(), []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _check_stability(issues: list, what: str, stability):
    if not 0 <= stability <= 1:
        issues.append(Issue("error", f"{what}: stability {stability} is not in [0, 1]"))


def validate_topology(topology: Topology) -> list[Issue]:
    issues = []
    if not topology.nodes:
        issues.append(Issue("error", "no nodes"))
    for duplicate in _duplicates(n.id for n in topology.nodes):
        issues.append(Issue("error", f"duplicate node id {duplicate}"))
    for node in topology.nodes:
        if node.cpu <= 0 or node.mem <= 0:
            issues.append(Issue("error", f"node {node.id}: cpu and mem must be positive"))
        _check_stability(issues, f"node {node.id}", node.stability)

    node_ids = {n.id for n in topology.nodes}
    for duplicate in _duplicates((link.source, link.target) for link in topology.links):
        issues.append(Issue("error", f"duplicate link {duplicate[0]}->{duplicate[1]}"))
    for link in topology.links:
        what = f"link {link.source}->{link.target}"
        for end in (link.source, link.target):
            if end not in node_ids:
                issues.append(Issue("error", f"{what}: unknown node {end}"))
        if link.source == link.target:
            issues.append(Issue("error", f"{what}: links a node to itself"))
        if link.throughput <= 0:
            issues.append(Issue("error", f"{what}: throughput must be positive"))
        if link.latency < 0:
            issues.append(Issue("error", f"{what}: latency must not be negative"))
        _check_stability(issues, what, link.stability)

    graph = nx.DiGraph()
    graph.add_nodes_from(node_ids)
    graph.add_edges_from((link.source, link.target) for link in topology.links
                         if link.source in node_ids and link.target in node_ids)
    if graph.number_of_nodes() > 1 and not nx.is_strongly_connected(graph):
        issues.append(Issue("warning", "the network is not strongly connected, some nodes cannot reach each other"))
    return issues


def validate_deployment(deployment: Deployment) -> list[Issue]:
    issues = []
    for duplicate in _duplicates(p.id for p in deployment.pods):
        issues.append(Issue("error", f"duplicate pod id {duplicate}"))
    pod_ids = {p.id for p in deployment.pods}
    for pod in deployment.pods:
        if pod.cpu < 0 or pod.mem < 0:
            issues.append(Issue("error", f"pod {pod.id}: cpu and mem must not be negative"))
        _check_stability(issues, f"pod {pod.id}", pod.stability)
        for connection in pod.network:
            if connection.to == pod.id:
                issues.append(Issue("error", f"pod {pod.id}: connection to itself"))
            elif connection.to not in pod_ids:
                issues.append(Issue("error", f"pod {pod.id}: connection to unknown pod {connection.to}"))
            if connection.throughput < 0 or connection.latency < 0:
                issues.append(Issue("error", f"pod {pod.id}: connection to {connection.to} has negative values"))
    return issues


def validate_combination(topology: Topology, deployment: Deployment) -> list[Issue]:
    issues = []
    for pod in deployment.pods:
        candidates = [n for n in topology.nodes if set(pod.label_selector) <= set(n.labels)]
        if not candidates:
            issues.append(Issue("error", f"pod {pod.id}: no node has the labels {list(pod.label_selector)}"))
        elif not any(pod.cpu <= n.cpu and pod.mem <= n.mem for n in candidates):
            issues.append(Issue("warning", f"pod {pod.id}: does not fit on any node with matching labels"))
    for resource in ("cpu", "mem"):
        demand = sum(getattr(p, resource) for p in deployment.pods)
        capacity = sum(getattr(n, resource) for n in topology.nodes)
        if demand > capacity:
            issues.append(Issue("warning", f"the pods need more {resource} ({demand}) than all nodes have ({capacity})"))
    return issues


# ---------------------------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------------------------

def generate_edge_topology(name: str = "generated", base_stations: int = 4, clients: int = 10,
                           satellites: int = 6, seed: int = 0) -> dict:
    """
    Generate a topology in the style of the "medium" scenario and return it in the file format:
    fully meshed base stations, clients (label camera) attached to one base station each and
    satellite clients (labels camera, sensor) with low throughput and high latency.
    Base station stabilities are drawn randomly.
    """
    rnd = Random(seed)
    nodes, links = [], []
    for i in range(1, base_stations + 1):
        nodes.append({"id": i, "cpu": 100, "mem": 64, "stability": round(rnd.uniform(0.5, 0.99), 2)})
    for a in range(1, base_stations + 1):
        for b in range(a + 1, base_stations + 1):
            links.append({"from": a, "to": b, "throughput": 500, "latency": rnd.choice([7, 7, 10]), "bidirectional": True})

    next_id = base_stations + 1
    for count, cpu, mem, labels, throughput, latency in [
        (clients, 50, 32, ["camera"], 100, 15),                  # clients
        (satellites, 20, 16, ["camera", "sensor"], 10, 100),     # satellite clients
    ]:
        for i in range(count):
            station = i % base_stations + 1
            nodes.append({"id": next_id, "cpu": cpu, "mem": mem, "labels": labels})
            links.append({"from": next_id, "to": station, "throughput": throughput, "latency": latency, "bidirectional": True})
            next_id += 1

    return {
        "name": name,
        "description": f"generated: {base_stations} base stations, {clients} clients, {satellites} satellites, seed {seed}",
        "defaults": {"node": {"stability": 0.99}, "link": {"stability": 0.99}},
        "nodes": nodes,
        "links": links,
    }
