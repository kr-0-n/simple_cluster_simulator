import pytest

from simulator.scenarios import (
    SCENARIO_DIR,
    ScenarioError,
    deployment_from_dict,
    generate_edge_topology,
    load_deployment,
    load_scenario,
    load_topology,
    topology_from_dict,
    validate_combination,
    validate_deployment,
    validate_topology,
)

TOPOLOGIES = sorted(p.stem for p in (SCENARIO_DIR / "topologies").glob("*.yaml"))
DEPLOYMENTS = sorted(p.stem for p in (SCENARIO_DIR / "deployments").glob("*.yaml"))


def errors(issues):
    return [i.message for i in issues if i.level == "error"]


@pytest.mark.parametrize("name", TOPOLOGIES)
def test_shipped_topologies_are_valid(name):
    assert validate_topology(load_topology(name)) == []


@pytest.mark.parametrize("name", DEPLOYMENTS)
def test_shipped_deployments_are_valid(name):
    assert validate_deployment(load_deployment(name)) == []


@pytest.mark.parametrize("name", ["mini", "small", "medium"])
def test_matching_scenarios_are_valid(name):
    load_scenario(name, name)


def test_label_selectors_that_no_node_satisfies_are_rejected():
    # the combination conf.py used to run
    with pytest.raises(ScenarioError, match="no node has the labels"):
        load_scenario("small", "medium")


def test_defaults_and_bidirectional_links():
    topology = topology_from_dict("t", {
        "defaults": {"node": {"stability": 0.9}, "link": {"stability": 0.8, "latency": 3}},
        "nodes": [{"id": 1, "cpu": 1, "mem": 1}, {"id": 2, "cpu": 1, "mem": 1, "stability": 0.5}],
        "links": [{"from": 1, "to": 2, "throughput": 5, "bidirectional": True}],
    })
    assert [n.stability for n in topology.nodes] == [0.9, 0.5]
    assert [(x.source, x.target, x.latency, x.stability) for x in topology.links] == [(1, 2, 3, 0.8), (2, 1, 3, 0.8)]


def test_missing_fields_are_reported():
    with pytest.raises(ScenarioError, match="stability"):
        topology_from_dict("t", {"nodes": [{"id": 1, "cpu": 1, "mem": 1}]})


def test_topology_errors():
    topology = topology_from_dict("t", {
        "nodes": [{"id": 1, "cpu": 1, "mem": 1, "stability": 1}, {"id": 1, "cpu": 1, "mem": 1, "stability": 2}],
        "links": [{"from": 1, "to": 9, "throughput": 1, "latency": 1, "stability": 1},
                  {"from": 1, "to": 1, "throughput": 0, "latency": 1, "stability": 1}],
    })
    messages = errors(validate_topology(topology))
    assert "duplicate node id 1" in messages
    assert any("stability 2" in m for m in messages)
    assert any("unknown node 9" in m for m in messages)
    assert any("itself" in m for m in messages)
    assert any("throughput must be positive" in m for m in messages)


def test_deployment_errors():
    deployment = deployment_from_dict("d", {"pods": [
        {"id": 1, "cpu": 1, "mem": 1, "stability": 1, "network": [{"to": 1, "latency": 1, "throughput": 1}]},
        {"id": 2, "cpu": 1, "mem": 1, "stability": 1, "network": [{"to": 7, "latency": 1, "throughput": 1}]},
    ]})
    messages = errors(validate_deployment(deployment))
    assert "pod 1: connection to itself" in messages
    assert "pod 2: connection to unknown pod 7" in messages


def test_unreachable_nodes_are_a_warning():
    topology = topology_from_dict("t", {
        "nodes": [{"id": 1, "cpu": 1, "mem": 1, "stability": 1}, {"id": 2, "cpu": 1, "mem": 1, "stability": 1}],
        "links": [{"from": 1, "to": 2, "throughput": 1, "latency": 1, "stability": 1}],
    })
    issues = validate_topology(topology)
    assert errors(issues) == [] and "not strongly connected" in issues[0].message


def test_generated_topology_is_valid_and_reproducible():
    data = generate_edge_topology("g", base_stations=5, clients=12, satellites=4, seed=3)
    assert data == generate_edge_topology("g", base_stations=5, clients=12, satellites=4, seed=3)
    topology = topology_from_dict("g", data)
    assert validate_topology(topology) == []
    assert len(topology.nodes) == 5 + 12 + 4
    assert len(topology.links) == 5 * 4 + 2 * (12 + 4)
    assert errors(validate_combination(topology, load_deployment("medium"))) == []
