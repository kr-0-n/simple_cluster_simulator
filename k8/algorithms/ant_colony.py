import math

import networkx as nx

from k8.algorithms import common
from k8.algorithms.common import assign_randomly, generate_neighbour_states, graph_hash
from k8.evaluator import evaluate_step
from metrics import update_metric

AMOUNT_OF_ANTS = 2
MOVES_PER_ANT = 3
ROUNDS = 2
PHEROMONE_EVAPORATION = 0.5
PHEROMONE_CONSTANT = 50000
INITIAL_PHEROMONE = 0.1
ALPHA = 1  # weight of the pheromone
BETA = 1   # weight of the heuristic
HEURISTIC_MULTIPLIER_FOR_WORSE_SOLUTIONS = 0


def ant_colony_solve(graph, pods=None, debug=False, visualize=False):
    """
    Ant colony optimisation over the space of solutions.

    The ant solution graph contains the ants and solution nodes. A solution node is a
    tuple (evaluation, graph); its out edges lead to its neighbour states and carry
    pheromone. Ants start at the root solution (new pods assigned randomly), move
    MOVES_PER_ANT times along the edges (probability ~ pheromone^ALPHA * heuristic^BETA)
    and deposit pheromone on their path after each round. Returns the best solution
    seen, or immediately a solution with evaluation 0.
    """
    first_solution = graph.copy()
    if pods is not None:
        for pod in pods:
            print(f"adding pod {pod}")
            first_solution = assign_randomly(first_solution, pod)

    ant_solution_graph = nx.DiGraph()
    root_node = (evaluate_step(graph, first_solution, debug=False), first_solution)
    ant_solution_graph.add_node(root_node, type="solution")
    if debug:
        print(f"ACO configuration: amount_of_ants={AMOUNT_OF_ANTS}, moves_per_ant={MOVES_PER_ANT}, pheromone_evaporation={PHEROMONE_EVAPORATION}")

    ants = list(range(AMOUNT_OF_ANTS))
    for ant in ants:
        ant_solution_graph.add_node(ant, type="ant", color='green')
        ant_solution_graph.add_edge(ant, root_node, type="sits")

    def solution_nodes():
        return [node for node in ant_solution_graph.nodes if ant_solution_graph.nodes[node]["type"] == "solution"]

    def position(ant):
        out_edges = list(ant_solution_graph.out_edges(ant))
        assert len(out_edges) == 1
        return out_edges[0][1]

    def heuristic(edge: tuple):
        current_value, next_value = edge[0][0], edge[1][0]
        if next_value > current_value:
            return ((next_value - current_value) / next_value) * HEURISTIC_MULTIPLIER_FOR_WORSE_SOLUTIONS
        return (current_value - next_value) / current_value * 100

    def move_ant(ant):
        node = position(ant)
        out_edges = list(ant_solution_graph.out_edges(node))
        if not out_edges:
            return  # nowhere to go, the ant stays
        ant_solution_graph.remove_edge(ant, node)
        attractiveness = lambda e: math.pow(ant_solution_graph.edges[e]["pheromone"], ALPHA) * math.pow(heuristic(e), BETA)
        try:
            denominator = sum(attractiveness(e) for e in out_edges)
        except ZeroDivisionError:
            denominator = None
        probability = []
        for out_edge in out_edges:
            try:
                probability.append(attractiveness(out_edge) / denominator)
                if debug: print("Edge with pheromone", ant_solution_graph.edges[out_edge]["pheromone"], "and heuristic", heuristic(out_edge), "has probability", probability[-1])
            except (ZeroDivisionError, TypeError):
                probability.append(0.001)
        # move according to probability
        threshold = common.rnd.random() * sum(probability)
        cumulative_probability = 0
        next_node = out_edges[-1][1]  # fallback in case of float rounding
        for out_edge, p in zip(out_edges, probability):
            cumulative_probability += p
            if cumulative_probability > threshold:
                next_node = out_edge[1]
                break
        ant_solution_graph.add_edge(ant, next_node, type="sits")

    def draw_ant_graph():
        dot_file = "aco.dot"
        for edge in ant_solution_graph.edges:
            if ant_solution_graph.edges[edge]["type"] == "solution":
                ant_solution_graph.edges[edge]["len"] = 0.0001
                ant_solution_graph.edges[edge]["label"] = str(round(ant_solution_graph.edges[edge]["pheromone"], 2))
                ant_solution_graph.edges[edge]["width"] = min(3, ant_solution_graph.edges[edge]["pheromone"]/100)
            elif ant_solution_graph.edges[edge]["type"] == "sits":
                ant_solution_graph.edges[edge]["len"] = 0.0005
        for node in ant_solution_graph.nodes:
            if ant_solution_graph.nodes[node]["type"] == "ant":
                ant_solution_graph.nodes[node]["label"] = str(node)
                ant_solution_graph.nodes[node]["shape"] = "circle"
                ant_solution_graph.nodes[node]["width"] = 0.5
            elif ant_solution_graph.nodes[node]["type"] == "solution":
                ant_solution_graph.nodes[node]["label"] = str(node[0])
        nx.drawing.nx_pydot.to_pydot(ant_solution_graph).write_raw(dot_file)
        print(f"ACO graph written to {dot_file}")
        input("press enter to continue")

    node_hash_map = {}  # graph hash -> solution node, so equal solutions are evaluated only once

    def attach_solutions(node, solution_list):
        """
        Attach the solutions as neighbours of node. Returns a perfect solution (evaluation 0) if one was found.
        """
        perfect_solution = None
        for solution in solution_list:
            solution_hash = graph_hash(solution)
            if solution_hash not in node_hash_map:
                node_hash_map[solution_hash] = (evaluate_step(graph, solution, debug=False), solution)
            solution_node = node_hash_map[solution_hash]

            if solution_node[0] == 0:
                perfect_solution = solution_node[1]
            if not ant_solution_graph.has_node(solution_node):
                ant_solution_graph.add_node(solution_node, type="solution", color='blue')
            if not ant_solution_graph.has_edge(node, solution_node):
                ant_solution_graph.add_edge(node, solution_node, type="solution", pheromone=INITIAL_PHEROMONE)
        return perfect_solution

    def update_pheromones():
        # the path of every ant as a list of edges (shortest path from the root to its position)
        path_list = []
        for ant in ants:
            path = nx.shortest_path(ant_solution_graph, root_node, position(ant))
            path_list.append(list(zip(path, path[1:])))

        for edge in ant_solution_graph.edges:
            if "pheromone" in ant_solution_graph.edges[edge]:
                for path in path_list:
                    if edge in path:
                        # pheromone_constant / the value of the solution the ant is on
                        ant_solution_graph.edges[edge]["pheromone"] += PHEROMONE_CONSTANT / path[-1][1][0]
            else:
                ant_solution_graph.edges[edge]["pheromone"] = INITIAL_PHEROMONE

    def reset_ants():
        for ant in ants:
            if len(list(ant_solution_graph.out_edges(ant))) == 1:
                ant_solution_graph.remove_edge(ant, position(ant))
        for ant in ants:
            ant_solution_graph.add_edge(ant, root_node, type="sits")

    def evaporate_pheromones():
        for edge in ant_solution_graph.edges:
            if "pheromone" in ant_solution_graph.edges[edge]:
                ant_solution_graph.edges[edge]["pheromone"] *= PHEROMONE_EVAPORATION

    for _ in range(ROUNDS):
        for _ in range(MOVES_PER_ANT):
            # generate the neighbour states for every solution an ant sits on
            # (unless they have been generated before)
            nodes_to_generate_neighbours_for = {}  # dict as an insertion ordered set
            for ant in ants:
                node = position(ant)
                if len(ant_solution_graph.out_edges(node)) == 0:
                    nodes_to_generate_neighbours_for[node] = None

            if debug:
                print(f"generating neighbours for {len(nodes_to_generate_neighbours_for)} nodes")
            for node in nodes_to_generate_neighbours_for:
                perfect_solution = attach_solutions(node, generate_neighbour_states(node[1]))
                if perfect_solution is not None:
                    if debug:
                        print(f"perfect solution found: {perfect_solution}")
                    if visualize:
                        draw_ant_graph()
                    update_metric("num_eval_func_calls", len(solution_nodes()))
                    return perfect_solution

            for ant in ants:
                move_ant(ant)

        update_pheromones()
        evaporate_pheromones()
        reset_ants()

    solution_list = sorted(solution_nodes(), key=lambda x: x[0])
    update_metric("num_eval_func_calls", len(solution_list))

    if visualize:
        draw_ant_graph()
    return solution_list[0][1]
