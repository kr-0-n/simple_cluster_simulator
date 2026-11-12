"""
Data model of the simulation.

Topology and deployment are immutable descriptions (loaded from the scenario files).
The changing state of a simulation lives in simulator.cluster.Cluster.

Node ids and pod ids are independent id spaces.
"""
from dataclasses import dataclass
from typing import Optional

NodeId = int
PodId = int
Placement = dict[PodId, Optional[NodeId]]  # pod -> node it runs on, None if it is not running


@dataclass(frozen=True)
class Node:
    id: NodeId
    cpu: float
    mem: float
    stability: float  # probability to survive one time step
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class Link:
    """A directed network link between two nodes."""
    source: NodeId
    target: NodeId
    throughput: float
    latency: float
    stability: float


@dataclass(frozen=True)
class Connection:
    """A network connection a pod wants to another pod."""
    to: PodId
    latency: float
    throughput: float


@dataclass(frozen=True)
class Pod:
    id: PodId
    cpu: float
    mem: float
    stability: float
    network: tuple[Connection, ...] = ()
    label_selector: tuple[str, ...] = ()


@dataclass(frozen=True)
class Topology:
    name: str
    nodes: tuple[Node, ...]
    links: tuple[Link, ...]


@dataclass(frozen=True)
class Deployment:
    name: str
    pods: tuple[Pod, ...]
