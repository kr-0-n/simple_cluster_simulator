"""
Schedules the small deployment once and writes the result to graph.dot
(render with e.g. `neato -Tpng graph.dot -o graph.png`).
"""
import network_administration
import scenarios
from k8.kubernetes_wrapper import Kubernetes
from visualizer import draw_graph

if __name__ == "__main__":
    k8 = Kubernetes(network_administration.setup_network(scenarios.small_graph), "simulated_annealing_solve")
    k8.deploy(scenarios.small_deployment)
    k8.tick()
    draw_graph(k8.graph, "Model Example")
