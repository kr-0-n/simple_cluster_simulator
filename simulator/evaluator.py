"""
Penalty function for a placement of pods on nodes (lower is better, 0 is perfect).

One Evaluator is created per scheduling decision. It knows the current network, the pods,
the crash rates of the nodes and the previous placement, and evaluates candidate placements.
Shortest paths are computed once per source node and evaluations are cached, so algorithms
can evaluate many (also repeated) candidates cheaply.
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

import networkx as nx

from simulator.config import Penalties
from simulator.model import NodeId, Placement, Pod, PodId


@dataclass(frozen=True)
class Evaluation:
    total: float
    resources: float = 0
    network: float = 0
    labels: float = 0
    stability: float = 0
    spread: float = 0
    move: float = 0

    COMPONENTS = ("resources", "network", "labels", "stability", "spread", "move")

    def components(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in self.COMPONENTS}


class Evaluator:
    def __init__(self, network: nx.DiGraph, pods: dict[PodId, Pod], penalties: Penalties,
                 crash_rates: Optional[dict[NodeId, float]] = None, previous: Optional[Placement] = None):
        """
        network:     nodes ("spec": Node) and links ("latency", "throughput") that are online
        pods:        all pods of the problem, in a fixed order (the order matters for the network
                     penalty: earlier pods get the link capacity first)
        crash_rates: recent crash rate per node (see FailureLog.crash_rate)
        previous:    the placement before this decision, moving a pod away from its node is penalised
        """
        self.network = network
        self.penalties = penalties
        self.pods = pods
        self.pod_ids = list(pods)
        self.node_ids = list(network.nodes)
        self.nodes = {node_id: network.nodes[node_id]["spec"] for node_id in self.node_ids}
        self.crash_rates = crash_rates or {}
        self.previous = previous or {}
        self._links = {(u, v): (data["latency"], data["throughput"]) for u, v, data in network.edges(data=True)}
        self._paths: dict[NodeId, dict[NodeId, list]] = {}
        self._routes: dict[tuple, Optional[tuple]] = {}
        self._cache: dict[tuple, Evaluation] = {}
        self.calls = 0  # number of evaluate() calls, including cache hits

    @property
    def unique_evaluations(self) -> int:
        return len(self._cache)

    def key(self, placement: Placement) -> tuple:
        return tuple(placement.get(pod_id) for pod_id in self.pod_ids)

    def score(self, placement: Placement) -> float:
        return self.evaluate(placement).total

    def evaluate(self, placement: Placement) -> Evaluation:
        self.calls += 1
        key = self.key(placement)
        evaluation = self._cache.get(key)
        if evaluation is None:
            evaluation = self._evaluate(dict(zip(self.pod_ids, key)))
            self._cache[key] = evaluation
        return evaluation

    def _evaluate(self, placement: Placement) -> Evaluation:
        parts = dict(
            resources=self.resources_penalty(placement),
            network=self.network_penalty(placement)[0],
            labels=self.labels_penalty(placement),
            stability=self.stability_penalty(placement),
            spread=self.spread_penalty(placement),
            move=self.move_penalty(placement),
        )
        return Evaluation(total=round(sum(parts.values()), 2), **parts)

    # --- penalties -----------------------------------------------------------------------

    def resources_penalty(self, placement: Placement) -> float:
        """Sum of the cpu and mem overload of all nodes."""
        cpu, mem = defaultdict(float), defaultdict(float)
        for pod_id, node_id in placement.items():
            if node_id is not None:
                cpu[node_id] += self.pods[pod_id].cpu
                mem[node_id] += self.pods[pod_id].mem
        return sum(max(0, cpu[n] - self.nodes[n].cpu) + max(0, mem[n] - self.nodes[n].mem) for n in cpu)

    def network_penalty(self, placement: Placement) -> tuple[float, dict]:
        """
        Unscheduled pods, latency of the wanted connections and links that cannot serve the
        wanted throughput. Connections are routed on the lowest latency path; every link
        forwards at most its capacity, so links behind an overloaded link see less traffic.
        Returns the penalty and the wanted throughput per link.
        """
        penalties = self.penalties
        value = 0
        load: dict[tuple, float] = {}
        for pod_id in self.pod_ids:
            start = placement.get(pod_id)
            if start is None:
                value += penalties.unconnected_pod
                continue
            for connection in self.pods[pod_id].network:
                end = placement.get(connection.to)
                if end is None:
                    continue  # the other pod is not running
                route = self._route(start, end)
                if route is None:
                    continue  # no route (network partition)
                latency, links = route
                rate = connection.throughput
                for link, capacity in links:
                    previous_load = load.get(link, 0.0)
                    new_load = previous_load + rate
                    load[link] = new_load
                    if previous_load > capacity:
                        rate = 0
                    elif new_load > capacity:
                        rate = capacity - previous_load
                    if new_load > capacity:
                        value += penalties.throughput * (new_load - capacity)
                value += penalties.latency * latency
        return value, load

    def labels_penalty(self, placement: Placement) -> float:
        """Every label of a pod's labelSelector that its node does not have."""
        value = 0
        for pod_id, node_id in placement.items():
            if node_id is None:
                continue
            labels = self.nodes[node_id].labels
            value += self.penalties.label * sum(1 for label in self.pods[pod_id].label_selector if label not in labels)
        return value

    def stability_penalty(self, placement: Placement) -> float:
        """Every pod on a node that crashed recently, weighted by the node's crash rate."""
        return sum(self.penalties.stability * self.crash_rates.get(node_id, 0)
                   for node_id in placement.values() if node_id is not None)

    def spread_penalty(self, placement: Placement) -> float:
        """
        Pods more or less on a node than in the most even distribution of the running pods.
        A distribution where every node has floor(avg) or ceil(avg) pods gets no penalty.
        """
        num_nodes = len(self.node_ids)
        if num_nodes == 0:
            return 0
        pods_per_node = dict.fromkeys(self.node_ids, 0)
        for node_id in placement.values():
            if node_id is not None:
                pods_per_node[node_id] += 1
        num_pods = sum(pods_per_node.values())
        avg = num_pods / num_nodes
        deviation = sum(abs(count - avg) for count in pods_per_node.values())
        remainder = num_pods % num_nodes
        minimal_deviation = 2 * remainder * (num_nodes - remainder) / num_nodes
        return max(0.0, round(deviation - minimal_deviation, 9)) * self.penalties.spread

    def move_penalty(self, placement: Placement) -> float:
        """Every pod that ran on a node before and now runs elsewhere (or not at all)."""
        moved = sum(1 for pod_id, node_id in self.previous.items()
                    if node_id is not None and placement.get(pod_id) != node_id)
        return moved * self.penalties.move_pod

    # --- helpers -------------------------------------------------------------------------

    def _route(self, start: NodeId, end: NodeId) -> Optional[tuple]:
        """(latency, [(link, capacity), ...]) of the lowest latency path, None if there is none."""
        key = (start, end)
        if key not in self._routes:
            path = self._shortest_path(start, end)
            if path is None:
                self._routes[key] = None
            else:
                links = list(zip(path, path[1:]))
                latency = 0
                for link in links:
                    latency += self._links[link][0]
                self._routes[key] = (latency, [(link, self._links[link][1]) for link in links])
        return self._routes[key]

    def _shortest_path(self, start: NodeId, end: NodeId) -> Optional[list]:
        paths = self._paths.get(start)
        if paths is None:
            paths = nx.single_source_dijkstra_path(self.network, start, weight="latency")
            self._paths[start] = paths
        return paths.get(end)
