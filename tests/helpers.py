from simulator.cluster import build_network
from simulator.config import Penalties
from simulator.evaluator import Evaluator
from simulator.model import Connection, Link, Node, Pod


def node(id, cpu=100, mem=100, labels=(), stability=1.0):
    return Node(id, cpu, mem, stability, tuple(labels))


def link(source, target, throughput=100, latency=1, stability=1.0):
    return Link(source, target, throughput, latency, stability)


def pod(id, cpu=1, mem=1, network=(), labels=(), stability=1.0):
    return Pod(id, cpu, mem, stability, tuple(Connection(*c) for c in network), tuple(labels))


def evaluator(nodes, links, pods, previous=None, crash_rates=None, **penalties):
    return Evaluator(build_network(nodes, links), {p.id: p for p in pods}, Penalties(**penalties),
                     crash_rates=crash_rates, previous=previous)
