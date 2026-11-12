"""
The chaos monkey creates chaos by failing nodes, links and pods. Beware, they are randomly chosen.

Every node, link and running pod survives a step with the probability given by its stability.
"""
from random import Random

from simulator.cluster import Cluster


class ChaosMonkey:
    def __init__(self, rng: Random):
        self.rng = rng

    def _fails(self, stability: float) -> bool:
        return self.rng.random() > stability

    def unleash(self, cluster: Cluster):
        for node_id in cluster.node_ids():
            if self._fails(cluster.node(node_id).stability):
                cluster.fail_node(node_id)
        for source, target, data in list(cluster.network.edges(data=True)):
            if self._fails(data["spec"].stability):
                cluster.fail_link(source, target)
        for pod_id in cluster.running_pod_ids():
            if self._fails(cluster.pods[pod_id].stability):
                cluster.fail_pod(pod_id)
