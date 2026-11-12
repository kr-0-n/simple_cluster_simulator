"""
Ant colony optimisation over the space of placements.
"""
import logging
import math
from typing import Optional

import networkx as nx

from simulator.algorithms.common import GOOD_ENOUGH, SchedulingProblem, neighbours
from simulator.model import Placement

log = logging.getLogger(__name__)


def ant_colony_solve(problem: SchedulingProblem, ants: int = 2, moves_per_ant: int = 3,
                     pheromone_evaporation: float = 0.5, pheromone_constant: float = 50000,
                     initial_pheromone: float = 0.1, alpha: float = 1, beta: float = 1,
                     heuristic_multiplier_for_worse_solutions: float = 0,
                     dot_file: Optional[str] = None) -> Placement:
    """
    The solution graph contains placements (identified by their evaluator key); the out edges
    of a placement lead to its neighbours and carry pheromone. Ants start at the root (the
    current placement with every new pod on its best node) and move `moves_per_ant` times,
    choosing an edge with probability ~ pheromone^alpha * heuristic^beta. After each round the
    ants deposit pheromone on their path (pheromone_constant / evaluation of their placement),
    pheromone evaporates and the ants return to the root. Rounds are repeated until the
    evaluation budget is used up (every neighbour looked at counts, also known ones) or a round
    finds nothing new. Returns the best placement seen, or immediately one below GOOD_ENOUGH.
    If dot_file is given, the solution graph is written to it at the end.
    """
    placements: dict[tuple, Placement] = {}
    values: dict[tuple, float] = {}

    def add_solution(placement: Placement) -> tuple:
        key = problem.evaluator.key(placement)
        value = problem.score(placement)  # counts towards the budget, also if the placement is known
        if key not in values:
            placements[key] = placement
            values[key] = value
        return key

    graph = nx.DiGraph()
    root = add_solution(problem.greedy_initial_placement())
    graph.add_node(root)
    positions = [root] * ants

    def finish(key: tuple) -> Placement:
        if dot_file:
            _write_dot(graph, values, positions, dot_file)
        return placements[key]

    if values[root] < GOOD_ENOUGH:
        return finish(root)

    def heuristic(source: tuple, target: tuple) -> float:
        current_value, next_value = values[source], values[target]
        if next_value > current_value:
            return (next_value - current_value) / next_value * heuristic_multiplier_for_worse_solutions
        return (current_value - next_value) / current_value * 100

    def move(ant: int):
        node = positions[ant]
        out_edges = list(graph.out_edges(node))
        if not out_edges:
            return  # nowhere to go
        attractiveness = lambda e: math.pow(graph.edges[e]["pheromone"], alpha) * math.pow(heuristic(*e), beta)
        try:
            total = sum(attractiveness(e) for e in out_edges)
            probabilities = [attractiveness(e) / total for e in out_edges]
        except ZeroDivisionError:
            probabilities = [0.001] * len(out_edges)  # no information: uniform
        threshold = problem.rng.random() * sum(probabilities)
        cumulative = 0
        positions[ant] = out_edges[-1][1]  # fallback in case of float rounding
        for edge, p in zip(out_edges, probabilities):
            cumulative += p
            if cumulative > threshold:
                positions[ant] = edge[1]
                break

    while not problem.exhausted():
        known_solutions = len(values)
        for _ in range(moves_per_ant):
            # expand the placements the ants sit on (once)
            for node in dict.fromkeys(positions):
                if graph.out_degree(node) > 0:
                    continue
                for neighbour in neighbours(problem, placements[node]):
                    if problem.exhausted():
                        break
                    key = add_solution(neighbour)
                    if values[key] < GOOD_ENOUGH:
                        log.debug("perfect placement found")
                        return finish(key)
                    if key != node and not graph.has_edge(node, key):
                        graph.add_edge(node, key, pheromone=initial_pheromone)
            for ant in range(ants):
                move(ant)

        # deposit pheromone on the (shortest) path from the root to every ant
        for position in positions:
            path = nx.shortest_path(graph, root, position)
            for edge in zip(path, path[1:]):
                graph.edges[edge]["pheromone"] += pheromone_constant / values[position]
        for edge in graph.edges:
            graph.edges[edge]["pheromone"] *= pheromone_evaporation
        positions = [root] * ants
        if len(values) == known_solutions:
            break  # the round found nothing new (search space explored)

    return finish(min(values, key=values.get))


def _write_dot(graph: nx.DiGraph, values: dict, positions: list, dot_file: str):
    dot = nx.DiGraph()
    names = {key: f"s{i}" for i, key in enumerate(graph.nodes)}
    for key, name in names.items():
        dot.add_node(name, label=str(values[key]))
    for u, v, data in graph.edges(data=True):
        dot.add_edge(names[u], names[v], label=str(round(data["pheromone"], 2)),
                     penwidth=min(3, data["pheromone"] / 100), len=0.0001)
    for ant, position in enumerate(positions):
        dot.add_node(f"ant{ant}", label=str(ant), shape="circle", color="green")
        dot.add_edge(f"ant{ant}", names[position], len=0.0005)
    nx.drawing.nx_pydot.write_dot(dot, dot_file)
    log.info("ACO graph written to %s", dot_file)
