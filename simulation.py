"""
Runs one simulation with the settings from conf.py.

Every step: the scheduler places pods that are not running, every `repair_interval`
steps the network is repaired, and then the chaos monkey breaks nodes, links and pods.
"""
from random import Random

import chaos_monkey
import conf
import metrics
import network_administration
import Time as time
from k8 import algorithms
from k8.kubernetes_wrapper import Kubernetes


def run_simulation():
    time.reset_time()
    network_administration.reset()
    algorithms.seed(conf.algorithm_seed)

    rnd = Random(conf.random_seed)
    chaos_monkey.rnd = rnd
    run_id = rnd.randint(1000, 9999)
    run_name = f"k8_simulation_{run_id}_{conf.metrics_name_postfix}"

    metrics.initialize(conf.metrics_name_postfix, run_id, enabled=conf.enable_metrics,
                       host=conf.database_host, user=conf.database_user, password=conf.database_password)
    print("metrics initialized")

    k8 = Kubernetes(network_administration.setup_network(conf.graph), conf.algorithm)
    k8.deploy(conf.deployment)

    try:
        while time.current_time_step() < conf.simulation_steps:
            k8.tick()
            if time.current_time_step() % conf.repair_interval == 0:
                print(f"network repaired at {time.current_time_step()}")
                network_administration.repair_network(k8.graph)

            chaos_monkey.unleash(k8.graph)

            time.increment_time()
            print(f"{__name__}: Time: {time.current_time_step()}")
    finally:
        metrics.close()
    print(f"Simulation {run_name} finished at {time.current_time_step()}")
    return k8


if __name__ == "__main__":
    run_simulation()
