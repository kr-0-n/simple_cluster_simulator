"""
Simulation configuration.

Scenario data (topologies and deployments) lives in scenarios.py.
The scheduling algorithm is referenced by name (see k8.algorithms.ALGORITHMS)
so this module does not import the algorithm code (avoids a circular import).
"""
import scenarios

enable_metrics = True

graph = scenarios.small_graph
deployment = scenarios.medium_deployment

algorithm = "ant_colony_solve"  # name from k8.algorithms.ALGORITHMS, or a callable

metrics_name_postfix = "ant_colony_solve_250"
random_seed = 19       # seeds the chaos monkey (and the run id)
algorithm_seed = 10    # seeds the randomness inside the scheduling algorithms

# Simulation loop
simulation_steps = 1440     # one step == one simulated minute
repair_interval = 5         # repair the network every n steps

# Penalties
move_pod_penalty = 400
unconnected_pod_penalty = 500
label_penalty = 1000
latency_penalty = 100
throughput_penalty = 10 # calculated like this: penalty = throughput_penalty * (wanted_throughput - actual_throughput)
spread_penalty = 10 # added for every pod to many or to little from the average

# Stability is calculated like this: penalty = stability_penalty * floating_average_of_crashes
stability_penalty = 20
floating_average_window = 20

# Database connection
database_host = "127.0.0.1"
database_user = "root"
database_password = "root"
