"""
Checks that simulator/evaluator.py computes the same violations and scores as the evaluator
of the reference scheduler, on random scenarios. The reference evaluator is compiled from
network_aware_k8s_scheduler (tools/reference_eval); the test is skipped without Go or the checkout.
"""
import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from random import Random

import pytest

from simulator.cluster import build_network
from simulator.config import Penalties
from simulator.evaluator import Evaluator
from simulator.model import Connection, Link, Node, Pod

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tools" / "reference_eval"
REFERENCE = ROOT / "network_aware_k8s_scheduler" / "k8_scheduler"
MIB = 1024 * 1024
LABELS = ["a", "b", "ssd"]
TERMS = {"cpu": "CPU", "memory": "Memory", "latency": "Latency", "throughput": "Throughput",
         "unconnected": "Unconnected", "label": "Label", "spread": "Spread", "move": "Move"}


@pytest.fixture(scope="module")
def reference_eval(tmp_path_factory):
    if shutil.which("go") is None or not REFERENCE.exists():
        pytest.skip("needs Go and the network_aware_k8s_scheduler checkout")
    binary = tmp_path_factory.mktemp("reference") / "reference_eval"
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOWORK": "off"}
    build = subprocess.run(["go", "build", "-o", str(binary), "."], cwd=HARNESS, env=env, capture_output=True, text=True)
    if build.returncode != 0:
        pytest.skip(f"cannot build the reference evaluator: {build.stderr[-500:]}")
    return binary


def node_name(i):
    return f"node-{i:03d}"


def pod_name(i):
    return f"pod-{i:03d}"


def random_scenario(r: Random):
    node_ids = r.sample(range(1, 60), r.randint(1, 7))
    nodes = [Node(i, r.randint(100, 2000), r.randint(64, 2048), 1.0, tuple(r.sample(LABELS, r.randint(0, 3))))
             for i in node_ids]
    links = [Link(a, b, round(r.uniform(0.5, 40), 2), r.randint(0, 15), 1.0)
             for a in node_ids for b in node_ids if a != b and r.random() < 0.55]
    pod_ids = r.sample(range(100, 400), r.randint(1, 10))
    pods = []
    for i in pod_ids:
        others = [p for p in pod_ids if p != i]
        network = tuple(Connection(r.choice(others), r.randint(0, 15), r.choice([r.randint(0, 60), round(r.uniform(0, 30), 2)]))
                        for _ in range(r.choice([0, 0, 1, 1, 2, 3])) if others)
        pods.append(Pod(i, r.randint(0, 1000), r.randint(0, 1024), 1.0, network, tuple(r.sample(LABELS, r.choice([0, 0, 1, 2])))))
    random_node = lambda: r.choice(node_ids) if r.random() > 0.15 else None
    base = {p.id: random_node() for p in pods}
    assignments = [{p.id: (base[p.id] if r.random() < 0.4 else random_node()) for p in pods} for _ in range(6)]
    return nodes, links, pods, base, assignments


def to_case(nodes, links, pods, base, assignments, penalties: Penalties) -> dict:
    name = lambda n: "" if n is None else node_name(n)
    return {
        "Penalties": {"CPU": penalties.cpu, "Memory": penalties.memory, "Label": penalties.label,
                      "UnconnectedPod": penalties.unconnected_pod, "Latency": penalties.latency,
                      "Throughput": penalties.throughput, "MovePod": penalties.move_pod,
                      "Spread": penalties.spread, "Stability": penalties.stability},
        # the reference reads memory in bytes and compares MiB
        "Nodes": [{"Name": node_name(n.id), "CPU": int(n.cpu), "Memory": int(n.mem) * MIB,
                   "Labels": {label: "true" for label in n.labels}} for n in nodes],
        "Links": [{"Source": node_name(x.source), "Target": node_name(x.target), "Latency": int(x.latency),
                   "Throughput": x.throughput} for x in links],
        "Pods": [{"Name": pod_name(p.id), "CPU": int(p.cpu), "Memory": int(p.mem) * MIB,
                  "Selector": {label: "true" for label in p.label_selector},
                  "Reqs": [{"Target": pod_name(c.to), "Latency": int(c.latency), "Throughput": c.throughput}
                           for c in p.network],
                  "Base": name(base[p.id])} for p in pods],
        "Assignments": [[name(a[p.id]) for p in pods] for a in assignments],
    }


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_evaluator_matches_reference(reference_eval, seed):
    r = Random(seed)
    penalties = Penalties()
    scenarios = [random_scenario(r) for _ in range(300)]
    out = subprocess.run([str(reference_eval)], input=json.dumps([to_case(*s, penalties) for s in scenarios]),
                         capture_output=True, text=True, check=True)
    for (nodes, links, pods, base, assignments), expected in zip(scenarios, json.loads(out.stdout)):
        evaluator = Evaluator(build_network(nodes, links), {p.id: p for p in pods}, penalties, previous=base)
        for assignment, reference in zip(assignments, expected):
            evaluation = evaluator.evaluate(assignment)
            for term, go_name in TERMS.items():
                got = getattr(evaluation.violations, term)
                assert math.isclose(got, reference[go_name], rel_tol=1e-9, abs_tol=1e-9), \
                    f"{term}: {got} != {reference[go_name]} for {to_case(nodes, links, pods, base, [assignment], penalties)}"
            assert math.isclose(evaluation.total, reference["Score"], rel_tol=1e-9, abs_tol=1e-9)
