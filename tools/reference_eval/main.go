// Evaluates placements with the reference evaluator (read-only use of the reference code).
// stdin: JSON list of cases, stdout: JSON list (per case) of lists (per assignment) of violations.
package main

import (
	"encoding/json"
	"os"

	"k8_scheduler/common"
	"k8_scheduler/scheduler/evaluator"

	gograph "github.com/dominikbraun/graph"
)

type Case struct {
	Penalties struct {
		CPU, Memory, Label, UnconnectedPod, Latency, Throughput, MovePod, Spread, Stability float64
	}
	Nodes []struct {
		Name   string
		CPU    int64
		Memory int64
		Labels map[string]string
	}
	Links []struct {
		Source, Target string
		Latency        int
		Throughput     float64
	}
	Pods []struct {
		Name     string
		CPU      int64
		Memory   int64
		Selector map[string]string
		Reqs     []common.NetworkComRequirement
		Base     string
	}
	Assignments [][]string // node name per pod (in the order of Pods), "" = unassigned
}

type Result struct {
	evaluator.Violations
	Score float64
}

func main() {
	var cases []Case
	if err := json.NewDecoder(os.Stdin).Decode(&cases); err != nil {
		panic(err)
	}
	var out [][]Result
	for _, c := range cases {
		w := &common.Cfg.Penalties
		w.CPU, w.Memory, w.Label, w.UnconnectedPod = c.Penalties.CPU, c.Penalties.Memory, c.Penalties.Label, c.Penalties.UnconnectedPod
		w.Latency, w.Throughput, w.MovePod, w.Spread, w.Stability = c.Penalties.Latency, c.Penalties.Throughput, c.Penalties.MovePod, c.Penalties.Spread, c.Penalties.Stability
		common.Cfg.Stability.FloatingAverageWindow = 30

		g := gograph.New(func(n *common.Node) string { return n.Name }, gograph.Directed())
		for _, n := range c.Nodes {
			labels, _ := json.Marshal(n.Labels)
			g.AddVertex(&common.Node{Name: n.Name, Type: common.TypeNode, Properties: map[string]string{
				"cpu": itoa(n.CPU), "memory": itoa(n.Memory), "labels": string(labels)}})
		}
		for _, l := range c.Links {
			if err := g.AddEdge(l.Source, l.Target, common.EdgeAttributes(common.EdgeConnection, common.Link{Latency: l.Latency, Throughput: l.Throughput})...); err != nil {
				panic(err)
			}
		}
		for _, p := range c.Pods {
			selector, _ := json.Marshal(p.Selector)
			reqs, _ := json.Marshal(p.Reqs)
			g.AddVertex(&common.Node{Name: p.Name, Type: common.TypePod, Properties: map[string]string{
				"cpu": itoa(p.CPU), "memory": itoa(p.Memory), "nodeSelector": string(selector), "networkComRequirements": string(reqs)}})
			if p.Base != "" {
				g.AddEdge(p.Name, p.Base, common.EdgeAttributes(common.EdgeAssign, common.Link{})...)
			}
		}
		problem := evaluator.NewProblem(g, nil)
		var results []Result
		for _, names := range c.Assignments {
			a := problem.BaseAssignment()
			for i, p := range c.Pods {
				pod, _ := problem.PodIndex(p.Name)
				a[pod] = evaluator.Unassigned
				if names[i] != "" {
					a[pod], _ = problem.NodeIndex(names[i])
				}
			}
			v := problem.Violations(a)
			results = append(results, Result{v, v.Score()})
		}
		out = append(out, results)
	}
	json.NewEncoder(os.Stdout).Encode(out)
}

func itoa(v int64) string { b, _ := json.Marshal(v); return string(b) }
