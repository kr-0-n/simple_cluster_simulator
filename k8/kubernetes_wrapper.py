import networkx as nx

from k8.evaluator import evaluate_step
from k8.scheduler import Scheduler
from metrics import create_metric, update_metric
from utils import get_edges_of_type, get_node_ids, get_scheduled_pod_ids

METRICS = [
    'evaluation',
    'nodes_online',
    'pods_online',
    'links_online',
    'num_eval_func_calls',
    'network_penalty',
    'labels_penalty',
    'node_stability_penalty',
    'spread_penalty',
    'resources_penalty',
    'move_pod_penalty',
    'pod_binding_changed',
]


class Kubernetes:
    def __init__(self, network: nx.DiGraph, algorithm):
        self.scheduler = Scheduler(algorithm)
        self.graph = network
        self.current_deployment = None
        print(f"{__name__}: Kubernetes initialized, using {self.scheduler.selected_algorithm.__name__} algorithm")

        for metric in METRICS:
            create_metric(metric)

    def deploy(self, deployment: dict):
        self.current_deployment = deployment

    def pods_to_schedule(self) -> list:
        """
        The pods of the current deployment that are not running (missing or not assigned to a node).
        """
        running_pods = get_scheduled_pod_ids(self.graph)
        return [pod for pod in self.current_deployment['pods'] if pod[0] not in running_pods]

    def tick(self):
        if self.current_deployment is None:
            return

        update_metric('nodes_online', len(get_node_ids(self.graph)))
        update_metric('pods_online', len(get_scheduled_pod_ids(self.graph)))
        update_metric('links_online', len(get_edges_of_type(self.graph, "connection")))

        pods_to_schedule = self.pods_to_schedule()
        new_graph = self.graph
        if pods_to_schedule:
            print(f"{__name__}: Pod(s) {pods_to_schedule} are not running")
            if get_node_ids(self.graph):
                new_graph = self.scheduler.schedule(pods_to_schedule, self.graph)
            else:
                print(f"{__name__}: No nodes available")

        evaluation = evaluate_step(self.graph, new_graph, debug=False, record_metrics=True)
        print(f"{__name__}: Evaluation: {evaluation}")
        update_metric('evaluation', evaluation)

        # count removed and added assignments (a moved pod counts twice)
        old_assignments = set(get_edges_of_type(self.graph, "assign"))
        new_assignments = set(get_edges_of_type(new_graph, "assign"))
        update_metric('pod_binding_changed', len(old_assignments ^ new_assignments))

        self.graph = new_graph
