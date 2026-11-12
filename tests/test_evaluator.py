import pytest

from tests.helpers import evaluator, link, node, pod

TWO_NODES = [node(1), node(2)]


def test_perfect_placement_scores_zero():
    e = evaluator(TWO_NODES, [], [pod(10), pod(11)])
    assert e.evaluate({10: 1, 11: 2}).total == 0


def test_unscheduled_pod():
    e = evaluator(TWO_NODES, [], [pod(10)])
    assert e.evaluate({10: None}).network == 500


def test_resources_overload_cpu_and_mem():
    e = evaluator([node(1, cpu=10, mem=10)], [], [pod(10, cpu=8, mem=1), pod(11, cpu=5, mem=12)])
    assert e.evaluate({10: 1, 11: 1}).resources == (13 - 10) + (13 - 10)


def test_labels_every_missing_label_counts():
    e = evaluator([node(1, labels=["a"])], [], [pod(10, labels=["a", "b", "c"])])
    assert e.evaluate({10: 1}).labels == 2000


def test_latency_and_throughput_on_a_path():
    # 1 -> 2 -> 3, the pod on 1 wants 15 to the pod on 3
    nodes = [node(1), node(2), node(3)]
    links = [link(1, 2, throughput=10, latency=5), link(2, 3, throughput=4, latency=2)]
    e = evaluator(nodes, links, [pod(10, network=[(11, 0, 15)]), pod(11)])
    evaluation = e.evaluate({10: 1, 11: 3})
    # latency: 7ms * 100; first link carries 15 of 10 (5 over), it forwards 10 to the second
    # link which can serve 4 (6 over): (5 + 6) * 10
    assert evaluation.network == 700 + 110
    assert e.network_penalty({10: 1, 11: 3})[1] == {(1, 2): 15, (2, 3): 10}


def test_connections_share_link_capacity():
    links = [link(1, 2, throughput=10, latency=1)]
    pods = [pod(10, network=[(12, 0, 6)]), pod(11, network=[(12, 0, 6)]), pod(12)]
    e = evaluator(TWO_NODES, links, pods)
    assert e.evaluate({10: 1, 11: 1, 12: 2}).network == 2 * 100 + (12 - 10) * 10


def test_no_route_and_unscheduled_partner_are_ignored():
    e = evaluator(TWO_NODES, [], [pod(10, network=[(11, 0, 5)]), pod(11)])
    assert e.evaluate({10: 1, 11: 2}).network == 0      # no link between 1 and 2
    assert e.evaluate({10: 1, 11: None}).network == 500  # only the unscheduled pod itself


def test_spread_most_even_distribution_is_free():
    pods = [pod(10), pod(11), pod(12)]
    e = evaluator(TWO_NODES, [], pods)
    assert e.evaluate({10: 1, 11: 1, 12: 2}).spread == 0
    assert e.evaluate({10: 1, 11: 1, 12: 1}).spread == pytest.approx(20)  # one pod too many on 1, too few on 2
    e = evaluator(TWO_NODES, [], pods[:2])
    assert e.evaluate({10: 1, 11: 2}).spread == 0
    assert e.evaluate({10: 1, 11: 1}).spread == pytest.approx(20)


def test_spread_ignores_unscheduled_pods():
    e = evaluator(TWO_NODES, [], [pod(10), pod(11), pod(12)])
    assert e.evaluate({10: 1, 11: 2, 12: None}).spread == 0


def test_stability_penalty_depends_on_the_placement():
    e = evaluator(TWO_NODES, [], [pod(10), pod(11)], crash_rates={1: 0.5, 2: 0.0})
    assert e.evaluate({10: 1, 11: 1}).stability == 2 * 20 * 0.5
    assert e.evaluate({10: 2, 11: 2}).stability == 0


def test_move_penalty():
    e = evaluator(TWO_NODES, [], [pod(10), pod(11)], previous={10: 1, 11: None})
    assert e.evaluate({10: 1, 11: 2}).move == 0      # 11 is new
    assert e.evaluate({10: 2, 11: 2}).move == 400    # 10 moved
    assert e.evaluate({10: None, 11: 2}).move == 400  # 10 stopped


def test_total_is_sum_of_components_and_cached():
    e = evaluator(TWO_NODES, [link(1, 2, latency=3)], [pod(10, network=[(11, 0, 1)]), pod(11)],
                  previous={10: 2, 11: 2})
    evaluation = e.evaluate({10: 1, 11: 2})
    assert evaluation.total == round(sum(evaluation.components().values()), 2)
    e.evaluate({10: 1, 11: 2})
    assert e.calls == 2 and e.unique_evaluations == 1
