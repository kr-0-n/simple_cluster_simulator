# Scenario files
A scenario is a topology (`topologies/<name>.yaml`) combined with a deployment (`deployments/<name>.yaml`).
Both are referenced by name or by path. Check them with `python -m simulator validate --combinations`.

Node ids and pod ids are separate id spaces.

## Topology
```yaml
name: small
defaults:                      # optional, applied to every entry that does not set the field
  node: {stability: 0.99}
  link: {stability: 0.99}
nodes:
  - {id: 1, cpu: 100, mem: 100, labels: [SSD], stability: 0.7}
links:                         # directed; bidirectional adds the reverse link with the same values
  - {from: 1, to: 2, throughput: 5, latency: 2}
  - {from: 3, to: 4, throughput: 10, latency: 10, bidirectional: true}
```
`stability` is the probability that the node/link survives one step.

## Deployment
```yaml
name: small
defaults:
  pod: {stability: 0.99}
pods:
  - {id: 5, cpu: 30, mem: 30, network: [{to: 6, latency: 3, throughput: 5}]}
  - {id: 11, cpu: 30, mem: 30, labelSelector: [SSD], network: [{to: 9, latency: 5, throughput: 3}]}
```
`network` lists the connections the pod wants to other pods. `labelSelector` lists labels the node must have.

## Validation
Errors: duplicate ids, missing fields, links to unknown nodes or to the node itself, non-positive
resources/throughput, stability outside [0, 1], connections to unknown pods or to the pod itself,
label selectors no node of the topology satisfies.
Warnings: network not strongly connected, pods that fit on no matching node, more demand than capacity.

## Generating topologies
`python -m simulator generate-topology --base-stations 6 --clients 20 --satellites 8 --seed 1 -o topologies/large.yaml`
creates an edge network in the style of `medium`.
