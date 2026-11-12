"""
Runs the simulation once per experiment. Each experiment is (metrics_name_postfix, algorithm name).
"""
import conf
import simulation

experiments = [
    ("ant_colony_demo", "ant_colony_solve"),
]

if __name__ == "__main__":
    for postfix, algorithm in experiments:
        conf.algorithm = algorithm
        conf.metrics_name_postfix = postfix
        simulation.run_simulation()
