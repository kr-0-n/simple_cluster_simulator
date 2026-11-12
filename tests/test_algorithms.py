from random import Random

import pytest

from simulator.algorithms import ALGORITHMS, SchedulingProblem
from simulator.algorithms.common import neighbour_at_index, neighbours, number_of_neighbours
from simulator.clock import Clock
from simulator.cluster import Cluster
from simulator.config import Penalties
from simulator.evaluator import Evaluator
from simulator.scenarios import load_scenario

FAST_PARAMS = {"evolutionary_solve": {"generations": 5}}


def problem(scenario="small", seed=1, placed=()):
    topology, deployment = load_scenario(scenario, scenario)
    cluster = Cluster(topology, deployment, Clock())
    placement = dict(cluster.placement)
    placement.update(placed)
    evaluator = Evaluator(cluster.network, cluster.pods, Penalties(), previous=placement)
    return SchedulingProblem(evaluator, Random(seed), placement, [p for p, n in placement.items() if n is None])


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


def test_algorithm_parameters_are_used():
    p = problem()
    ALGORITHMS["simulated_annealing_solve"](p, max_iterations=5)
    assert p.evaluator.calls == 6


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
