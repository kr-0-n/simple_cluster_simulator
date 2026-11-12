from random import Random

import pytest

from simulator.algorithms import ALGORITHMS, SchedulingProblem
from simulator.algorithms.common import neighbour_at_index, neighbours, number_of_neighbours
from simulator.clock import Clock
from simulator.cluster import Cluster
from simulator.config import Penalties
from simulator.evaluator import Evaluator
from simulator.scenarios import load_scenario

FAST_PARAMS = {}
SEARCH = ["simulated_annealing_solve", "evolutionary_solve", "ant_colony_solve"]


def problem(scenario="small", seed=1, placed=(), budget=300):
    topology, deployment = load_scenario(scenario, scenario)
    cluster = Cluster(topology, deployment, Clock())
    placement = dict(cluster.placement)
    placement.update(placed)
    evaluator = Evaluator(cluster.network, cluster.pods, Penalties(), previous=placement)
    return SchedulingProblem(evaluator, Random(seed), placement, [p for p, n in placement.items() if n is None], budget)


@pytest.mark.parametrize("name", sorted(ALGORITHMS))
def test_algorithms_place_all_new_pods_on_existing_nodes(name):
    p = problem()
    placement = ALGORITHMS[name](p, **FAST_PARAMS.get(name, {}))
    assert set(placement) == set(p.pod_ids)
    assert all(node is None or node in p.node_ids for node in placement.values())
    # like the reference scheduler, the algorithms never unassign pods
    # (kubernetes_default leaves a pod pending if no node is feasible)
    if name != "kubernetes_default":
        assert all(node is not None for node in placement.values())


@pytest.mark.parametrize("name", sorted(ALGORITHMS))
def test_algorithms_are_deterministic(name):
    params = FAST_PARAMS.get(name, {})
    assert ALGORITHMS[name](problem(seed=4), **params) == ALGORITHMS[name](problem(seed=4), **params)


@pytest.mark.parametrize("name", sorted(ALGORITHMS))
def test_perfect_solve_is_optimal(name):
    reference = problem("mini")
    best = reference.score(ALGORITHMS["perfect_solve"](reference))
    p = problem("mini")
    assert best <= p.score(ALGORITHMS[name](p, **FAST_PARAMS.get(name, {})))


def test_kubernetes_default_does_not_move_running_pods():
    p = problem(placed={5: 1, 6: 2})
    placement = ALGORITHMS["kubernetes_default"](p)
    assert placement[5] == 1 and placement[6] == 2


GREEDY_START_MEDIUM = 25 * 20  # all 25 pods are new, each is tried on all 20 nodes


@pytest.mark.parametrize("name", SEARCH)
def test_search_algorithms_use_the_budget(name):
    p = problem("medium", budget=2000)
    ALGORITHMS[name](p)
    assert 2000 <= p.evaluations <= 2001


@pytest.mark.parametrize("name", SEARCH)
def test_greedy_start_completes_beyond_the_budget(name):
    p = problem("medium", budget=100)
    placement = ALGORITHMS[name](p)
    assert all(node is not None for node in placement.values())
    assert GREEDY_START_MEDIUM <= p.evaluations <= GREEDY_START_MEDIUM + 1


def test_greedy_initial_placement_puts_pods_on_their_best_node():
    p = problem()
    placement = p.greedy_initial_placement()
    assert placement[11] == 1  # pod 11 needs the SSD of node 1
    assert all(node is not None for node in placement.values())
    assert p.score(placement) < p.score(p.random_initial_placement())


def test_reoptimisation_without_new_pods():
    current = ALGORITHMS["random_solve"](problem())
    p = problem(placed=current)
    assert p.new_pod_ids == []
    improved = ALGORITHMS["simulated_annealing_solve"](p)
    assert p.score(improved) <= p.score(current)
    assert ALGORITHMS["kubernetes_default"](problem(placed=current)) == current  # never moves pods


def test_algorithm_parameters_are_used():
    # with the same budget, different parameters explore different parts of the search space
    explored = []
    for params in [{"ants": 1, "moves_per_ant": 1}, {"ants": 4, "moves_per_ant": 5}]:
        p = problem("medium", seed=2, budget=1500)
        ALGORITHMS["ant_colony_solve"](p, **params)
        explored.append(p.evaluator.unique_evaluations)
    assert explored[0] != explored[1]


def test_search_beats_random_placement():
    random_score = problem().score(ALGORITHMS["random_solve"](problem()))
    for name in ["simulated_annealing_solve", "ant_colony_solve", "evolutionary_solve"]:
        p = problem()
        assert p.score(ALGORITHMS[name](p, **FAST_PARAMS.get(name, {}))) < random_score


def test_neighbour_at_index_matches_neighbour_list():
    p = problem()
    placement = p.random_initial_placement()
    all_neighbours = neighbours(p, placement)
    assert len(all_neighbours) == number_of_neighbours(p)
    assert all(neighbour_at_index(p, placement, i) == n for i, n in enumerate(all_neighbours))


def test_ant_colony_writes_dot_file(tmp_path):
    path = tmp_path / "aco.dot"
    ALGORITHMS["ant_colony_solve"](problem(), dot_file=str(path))
    assert path.read_text().startswith("strict digraph") or path.read_text().startswith("digraph")


def test_perfect_solve_refuses_huge_problems():
    with pytest.raises(ValueError, match="combinations"):
        ALGORITHMS["perfect_solve"](problem("medium"))
