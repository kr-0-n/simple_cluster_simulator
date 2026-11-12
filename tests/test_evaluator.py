"""
Evaluator tests. The first tests are ports of the reference scheduler's
scheduler/evaluator/evaluator_test.go with the same expected values.
"""
import pytest

from simulator.config import Penalties
from simulator.evaluator import Violations
from tests.helpers import evaluator, link, node, pod


def violations(nodes, links, pods, placement, **kwargs) -> Violations:
    return evaluator(nodes, links, pods, previous=placement, **kwargs).evaluate(placement).violations


# --- ports of evaluator_test.go ------------------------------------------------------------

def test_resource_violations():
    nodes = [node(1, cpu=1000, mem=1024), node(2, cpu=1000, mem=1024)]
    pods = [pod(10, cpu=1500, mem=1536), pod(11, cpu=3000, mem=512)]  # node 1: 50 % over, node 2: 200 % over in CPU
    v = violations(nodes, [], pods, {10: 1, 11: 2})
    assert v.cpu == pytest.approx(0.5 + 2)
    assert v.memory == pytest.approx(0.5)


def test_latency_violation():
    # 30 ms where 10 ms are allowed: 2x over
    v = violations([node(1), node(2)], [link(1, 2, throughput=100, latency=30)],
                   [pod(10, network=[(11, 10, 0)]), pod(11)], {10: 1, 11: 2})
    assert v.latency == pytest.approx(2)


def test_throughput_shared_link():
    # two flows of 8 share a link with capacity 10: overloaded by 6, i.e. 60 %
    v = violations([node(1), node(2)], [link(1, 2, throughput=10, latency=0)],
                   [pod(10, network=[(12, 100, 8)]), pod(11, network=[(12, 100, 8)]), pod(12)], {10: 1, 11: 1, 12: 2})
    assert v.throughput == pytest.approx(0.6)


def test_throughput_scaled_down_along_path():
    # a flow of 20 over 1->2 (capacity 10) and 2->3 (capacity 5): only 10 reaches 2->3,
    # so both links are 100 % overloaded
    v = violations([node(1), node(2), node(3)], [link(1, 2, throughput=10, latency=0), link(2, 3, throughput=5, latency=0)],
                   [pod(10, network=[(11, 100, 20)]), pod(11)], {10: 1, 11: 3})
    assert v.throughput == pytest.approx(2)


def test_unconnected():
    pods = [pod(10), pod(11, network=[(10, 10, 1)]), pod(12, network=[(13, 10, 1)]), pod(13)]
    v = violations([node(1), node(2)], [], pods, {10: 2, 11: 1, 12: 1, 13: None})  # no link between 1 and 2
    assert v.unconnected == 2
    assert v.latency == 0


def test_label_violation():
    pods = [pod(10, labels=["zone-a", "hdd"]), pod(11, labels=["zone-b"]), pod(12, labels=["zone-a"])]
    v = violations([node(1, labels=["zone-a", "ssd"])], [], pods, {10: 1, 11: 1, 12: 1})
    assert v.label == pytest.approx(0.5 + 1)


@pytest.mark.parametrize("counts, expected", [
    ([2, 2, 2], 0),           # balanced
    ([2, 2, 1, 1], 0),        # as balanced as possible
    ([3, 1, 1, 1], 1),        # one pod too many
    ([2, 2, 2, 0], 1),        # empty node
    ([6, 0, 0], 4),           # all on one node
])
def test_spread_violation(counts, expected):
    nodes = [node(i) for i in range(len(counts))]
    placement = {}
    for node_id, count in enumerate(counts):
        for _ in range(count):
            placement[100 + len(placement)] = node_id
    assert violations(nodes, [], [pod(p) for p in placement], placement).spread == expected


def test_moves_and_score():
    e = evaluator([node(1), node(2)], [], [pod(10), pod(11)], previous={10: 1, 11: 1}, move_pod=3, spread=0)
    evaluation = e.evaluate({10: 2, 11: 2})
    assert evaluation.violations.move == 2
    assert evaluation.total == 6


def test_equal_weights_equal_impact():
    weights = Penalties(**{name: 7 for name in ["cpu", "memory", "label", "unconnected_pod", "latency", "throughput",
                                                 "move_pod", "spread", "stability"]})
    for term in Violations().as_dict():
        assert Violations(**{term: 1}).score(weights) == 7


# --- behaviour taken over from problem.go --------------------------------------------------

def test_fewest_hops_not_lowest_latency():
    # 1->3 directly takes 50 ms, 1->2->3 only 2 ms: the reference routes over the fewest hops
    nodes = [node(1), node(2), node(3)]
    links = [link(1, 3, latency=50), link(1, 2, latency=1), link(2, 3, latency=1)]
    v = violations(nodes, links, [pod(10, network=[(11, 10, 0)]), pod(11)], {10: 1, 11: 3})
    assert v.latency == pytest.approx((50 - 10) / 10)


def test_ties_are_broken_by_node_order():
    # 1->2->4 and 1->3->4 have the same number of hops, the path over node 2 is taken
    nodes = [node(1), node(2), node(3), node(4)]
    links = [link(1, 3, latency=1), link(3, 4, latency=1), link(1, 2, latency=5), link(2, 4, latency=5)]
    v = violations(nodes, links, [pod(10, network=[(11, 0, 0)]), pod(11)], {10: 1, 11: 4})
    assert v.latency == pytest.approx(10)  # 10 ms where 0 are allowed (measured per ms)


def test_both_pods_unassigned_count_as_same_node():
    # as in the reference: a requirement between two unassigned pods is not penalised
    v = violations([node(1)], [], [pod(10, network=[(11, 0, 5)]), pod(11)], {10: None, 11: None})
    assert v.unconnected == 0


def test_unscheduled_pods_without_requirements_are_free():
    v = violations([node(1)], [], [pod(10)], {10: None})
    assert v == Violations()


# --- simulator specific --------------------------------------------------------------------

def test_stability_depends_on_the_placement():
    e = evaluator([node(1), node(2)], [], [pod(10), pod(11)], crash_rates={1: 0.5, 2: 0.0}, spread=0)
    assert e.evaluate({10: 1, 11: 1}).violations.stability == pytest.approx(1.0)
    assert e.evaluate({10: 1, 11: 1}).total == pytest.approx(10 * 1.0)
    assert e.evaluate({10: 2, 11: 2}).violations.stability == 0


def test_evaluations_are_cached():
    e = evaluator([node(1), node(2)], [link(1, 2)], [pod(10, network=[(11, 0, 1)]), pod(11)])
    assert e.evaluate({10: 1, 11: 2}) == e.evaluate({11: 2, 10: 1})
    assert e.calls == 2 and e.unique_evaluations == 1


def test_link_loads():
    nodes = [node(1), node(2), node(3)]
    links = [link(1, 2, throughput=10, latency=0), link(2, 3, throughput=4, latency=0)]
    loads = evaluator(nodes, links, [pod(10, network=[(11, 0, 15)]), pod(11)]).link_loads({10: 1, 11: 3})
    assert loads == {(1, 2): 15, (2, 3): 10}
