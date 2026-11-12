"""
Penalty function for a placement of pods on nodes (lower is better, 0 is perfect).

This is a port of the evaluator of the network aware scheduler
(network_aware_k8s_scheduler/k8_scheduler/scheduler/evaluator/problem.go), so the
simulator optimises the same objective as the real scheduler.

Every term is measured in a common unit, 1 = one clear violation of that kind
(see Violations). The score is the sum of the terms, each multiplied by its weight
from Penalties, so a weight is simply the cost of one violation.

One Evaluator is created per scheduling decision. Everything that does not depend on
the placement (label violations, requirements, paths) is computed once; evaluations
are cached.

Conventions taken over from the reference (they matter for ties and shared links):
  - pods and nodes are ordered by id (the reference orders by name),
  - network paths are the fewest-hop paths over the online links; ties are broken by
    visiting neighbours in node order (breadth first search),
  - flows claim link capacity in pod order, requirements in the order they are listed.

Deviation from the reference: the stability term depends on the placement (pods on
nodes that crashed recently). In the reference it is the same for every placement
and currently always 0 (README "Known limitations").
"""
from collections import deque
from dataclasses import dataclass, fields
from typing import Optional

import networkx as nx

from simulator.config import Penalties
from simulator.model import NodeId, Placement, Pod, PodId


@dataclass(frozen=True)
class Violations:
    """The unweighted penalty terms; 1 = one clear violation."""
    cpu: float = 0          # sum over nodes of CPU overload / capacity: 1 = one node at 200 %
    memory: float = 0       # same for memory
    latency: float = 0      # sum over requirements of (latency - allowed) / allowed: 1 = one requirement at 2x
    throughput: float = 0   # sum over links of overload / capacity: 1 = one link at 200 %
    unconnected: float = 0  # requirements whose pods are not placed or have no path between them
    label: float = 0        # sum over pods of the fraction of unmatched label selector entries
    spread: float = 0       # minimum number of pods that would have to move to balance the nodes
    move: float = 0         # pods moved away from their current node
    stability: float = 0    # sum over pods of the recent crash rate of their node (crashes per step)

    def score(self, penalties: Penalties) -> float:
        p = penalties
        return (p.cpu * self.cpu + p.memory * self.memory + p.latency * self.latency
                + p.throughput * self.throughput + p.unconnected_pod * self.unconnected + p.label * self.label
                + p.spread * self.spread + p.move_pod * self.move + p.stability * self.stability)

    def as_dict(self) -> dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class Evaluation:
    total: float            # the weighted score
    violations: Violations


@dataclass(frozen=True)
class _Requirement:
    destination: PodId      # the pod the connection goes to
    latency: float          # maximum latency
    throughput: float       # required throughput


class Evaluator:
    def __init__(self, network: nx.DiGraph, pods: dict[PodId, Pod], penalties: Penalties,
                 crash_rates: Optional[dict[NodeId, float]] = None, previous: Optional[Placement] = None):
        """
        network:     the online nodes ("spec": Node) and links ("latency", "throughput")
        pods:        all pods of the problem
        crash_rates: recent crash rate per node (see FailureLog.crash_rate)
        previous:    the placement before this decision, moving a pod away from its node is penalised
        """
        self.network = network
        self.penalties = penalties
        self.pods = pods
        self.pod_ids = sorted(pods)
        self.node_ids = sorted(network.nodes)
        self.nodes = {node_id: network.nodes[node_id]["spec"] for node_id in self.node_ids}
        self.crash_rates = crash_rates or {}
        self.previous = previous or {}

        self._requirements = {pod_id: [_Requirement(c.to, c.latency, c.throughput) for c in pods[pod_id].network]
                              for pod_id in self.pod_ids}
        self._label_violation = {(pod_id, node_id): self._label_fraction(pods[pod_id], self.nodes[node_id])
                                 for pod_id in self.pod_ids if pods[pod_id].label_selector for node_id in self.node_ids}
        # links in node order, so the breadth first search breaks ties like the reference
        self._adjacency = {node_id: sorted(network.successors(node_id)) for node_id in self.node_ids}
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
            violations = self.violations(dict(zip(self.pod_ids, key)))
            evaluation = Evaluation(violations.score(self.penalties), violations)
            self._cache[key] = evaluation
        return evaluation

    def violations(self, placement: Placement) -> Violations:
        cpu, memory = self._resource_violations(placement)
        latency, throughput, unconnected, _ = self._network_violations(placement)
        return Violations(cpu=cpu, memory=memory, latency=latency, throughput=throughput, unconnected=unconnected,
                          label=self._label_violations(placement), spread=self._spread_violation(placement),
                          move=self._moves(placement), stability=self._stability_violation(placement))

    def link_loads(self, placement: Placement) -> dict[tuple, float]:
        """The throughput routed over every link (for visualisation)."""
        return self._network_violations(placement)[3]

    # --- terms ---------------------------------------------------------------------------

    def _resource_violations(self, placement: Placement) -> tuple[float, float]:
        cpu_load = dict.fromkeys(self.node_ids, 0.0)
        mem_load = dict.fromkeys(self.node_ids, 0.0)
        for pod_id, node_id in placement.items():
            if node_id is not None:
                cpu_load[node_id] += self.pods[pod_id].cpu
                mem_load[node_id] += self.pods[pod_id].mem
        cpu = memory = 0.0
        for node_id, node in self.nodes.items():
            if cpu_load[node_id] > node.cpu > 0:
                cpu += (cpu_load[node_id] - node.cpu) / node.cpu
            if mem_load[node_id] > node.mem > 0:
                memory += (mem_load[node_id] - node.mem) / node.mem
        return cpu, memory

    def _network_violations(self, placement: Placement) -> tuple[float, float, float, dict]:
        """
        Every requirement is routed between the nodes of its two pods. Every link accumulates
        the throughput routed over it; a flow that does not fit through a link is reduced to the
        link's remaining capacity for the following links.
        """
        latency = throughput = unconnected = 0.0
        wanted: dict[tuple, float] = {}
        for pod_id in self.pod_ids:
            for requirement in self._requirements[pod_id]:
                source = placement.get(pod_id)
                target = placement.get(requirement.destination)
                if source == target:
                    route = (0, [])  # same node (as in the reference also: both pods unassigned)
                elif source is None or target is None:
                    unconnected += 1
                    continue
                else:
                    route = self._route(source, target)
                    if route is None:
                        unconnected += 1
                        continue

                path_latency, links = route
                if path_latency > requirement.latency:
                    latency += (path_latency - requirement.latency) / max(requirement.latency, 1)

                carried = requirement.throughput
                for link, capacity in links:
                    old = wanted.get(link, 0.0)
                    new = old + carried
                    wanted[link] = new
                    if capacity <= 0:
                        continue
                    if new > capacity:
                        throughput += (max(0.0, new - capacity) - max(0.0, old - capacity)) / capacity
                        carried = max(0.0, capacity - old)  # only the remaining capacity reaches the next link
        return latency, throughput, unconnected, wanted

    def _label_violations(self, placement: Placement) -> float:
        return sum(self._label_violation.get((pod_id, node_id), 0.0)
                   for pod_id, node_id in placement.items() if node_id is not None)

    def _spread_violation(self, placement: Placement) -> float:
        """
        The minimum number of pods that would have to move so that every node runs between
        floor(P/N) and ceil(P/N) of the P placed pods.
        """
        if not self.node_ids:
            return 0
        count = dict.fromkeys(self.node_ids, 0)
        for node_id in placement.values():
            if node_id is not None:
                count[node_id] += 1
        placed, num_nodes = sum(count.values()), len(self.node_ids)
        low, high = placed // num_nodes, -(-placed // num_nodes)
        excess = sum(max(0, c - high) for c in count.values())
        deficit = sum(max(0, low - c) for c in count.values())
        return float(max(excess, deficit))

    def _moves(self, placement: Placement) -> float:
        return float(sum(1 for pod_id, node_id in self.previous.items()
                         if node_id is not None and placement.get(pod_id) != node_id))

    def _stability_violation(self, placement: Placement) -> float:
        return sum(self.crash_rates.get(node_id, 0.0) for node_id in placement.values() if node_id is not None)

    # --- helpers -------------------------------------------------------------------------

    @staticmethod
    def _label_fraction(pod: Pod, node) -> float:
        """Fraction of the pod's label selector entries the node does not have."""
        missing = sum(1 for label in pod.label_selector if label not in node.labels)
        return missing / len(pod.label_selector)

    def _route(self, source: NodeId, target: NodeId) -> Optional[tuple]:
        """(latency, [(link, capacity), ...]) of the fewest-hop path, None if there is none."""
        key = (source, target)
        if key not in self._routes:
            path = self._fewest_hop_paths(source).get(target)
            if path is None:
                self._routes[key] = None
            else:
                links = list(zip(path, path[1:]))
                self._routes[key] = (sum(self._links[link][0] for link in links),
                                     [(link, self._links[link][1]) for link in links])
        return self._routes[key]

    def _fewest_hop_paths(self, source: NodeId) -> dict[NodeId, list]:
        paths = self._paths.get(source)
        if paths is None:
            parent = {source: None}
            queue = deque([source])
            while queue:
                current = queue.popleft()
                for neighbour in self._adjacency[current]:
                    if neighbour not in parent:
                        parent[neighbour] = current
                        queue.append(neighbour)
            paths = {}
            for target in parent:
                path, node = [], target
                while node is not None:
                    path.append(node)
                    node = parent[node]
                paths[target] = path[::-1]
            self._paths[source] = paths
        return paths
