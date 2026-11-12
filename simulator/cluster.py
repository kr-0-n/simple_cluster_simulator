"""
The changing state of a simulated cluster: which nodes and links are online, where the
pods run, and when things failed.
"""
import logging
from collections import defaultdict

import networkx as nx

from simulator.clock import Clock
from simulator.model import Deployment, Link, Node, NodeId, Placement, Pod, PodId, Topology

log = logging.getLogger(__name__)


def build_network(nodes, links) -> nx.DiGraph:
    """
    Directed graph of the nodes (attribute "spec": Node) and links (attributes "spec": Link,
    "latency" and "throughput").
    """
    network = nx.DiGraph()
    for node in nodes:
        network.add_node(node.id, spec=node)
    for link in links:
        network.add_edge(link.source, link.target, spec=link, latency=link.latency, throughput=link.throughput)
    return network


class FailureLog:
    """The time steps at which nodes, links and pods failed."""

    def __init__(self):
        self.nodes: dict[NodeId, list[int]] = defaultdict(list)
        self.links: dict[tuple[NodeId, NodeId], list[int]] = defaultdict(list)
        self.pods: dict[PodId, list[int]] = defaultdict(list)

    def crash_rate(self, node_id: NodeId, step: int, window: int) -> float:
        """Crashes of the node during the last `window` steps, divided by the window."""
        if window <= 0:
            return 0.0
        crashes = sum(1 for crash in self.nodes.get(node_id, ()) if step - crash < window)
        return crashes / window


class Cluster:
    def __init__(self, topology: Topology, deployment: Deployment, clock: Clock):
        self.topology = topology
        self.clock = clock
        self.network = build_network(topology.nodes, topology.links)
        self.pods: dict[PodId, Pod] = {pod.id: pod for pod in deployment.pods}
        self.placement: Placement = {pod_id: None for pod_id in self.pods}
        self.failures = FailureLog()

    # --- queries -------------------------------------------------------------------------

    def node(self, node_id: NodeId) -> Node:
        return self.network.nodes[node_id]["spec"]

    def node_ids(self) -> list[NodeId]:
        return list(self.network.nodes)

    def running_pod_ids(self) -> list[PodId]:
        return [pod_id for pod_id, node_id in self.placement.items() if node_id is not None]

    def pending_pod_ids(self) -> list[PodId]:
        return [pod_id for pod_id, node_id in self.placement.items() if node_id is None]

    def crash_rates(self, window: int) -> dict[NodeId, float]:
        return {node_id: self.failures.crash_rate(node_id, self.clock.step, window) for node_id in self.network.nodes}

    # --- changes -------------------------------------------------------------------------

    def place(self, placement: Placement):
        unknown = {node_id for node_id in placement.values() if node_id is not None and node_id not in self.network}
        if unknown:
            raise ValueError(f"placement uses nodes that are not online: {sorted(unknown)}")
        self.placement = {pod_id: placement.get(pod_id) for pod_id in self.pods}

    def fail_node(self, node_id: NodeId):
        log.debug("node %s failed", node_id)
        self.network.remove_node(node_id)
        self.failures.nodes[node_id].append(self.clock.step)
        for pod_id, assigned in self.placement.items():
            if assigned == node_id:
                self.placement[pod_id] = None

    def fail_link(self, source: NodeId, target: NodeId):
        log.debug("link %s->%s failed", source, target)
        self.network.remove_edge(source, target)
        self.failures.links[(source, target)].append(self.clock.step)

    def fail_pod(self, pod_id: PodId):
        log.debug("pod %s failed", pod_id)
        self.placement[pod_id] = None
        self.failures.pods[pod_id].append(self.clock.step)

    def repair(self):
        """Bring back every node and link of the topology that is offline."""
        for node in self.topology.nodes:
            if node.id not in self.network:
                self.network.add_node(node.id, spec=node)
                log.debug("node %s back online", node.id)
        for link in self.topology.links:
            if not self.network.has_edge(link.source, link.target):
                self._add_link(link)
                log.debug("link %s->%s back online", link.source, link.target)

    def _add_link(self, link: Link):
        self.network.add_edge(link.source, link.target, spec=link, latency=link.latency, throughput=link.throughput)
