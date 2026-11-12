# reference_eval
Evaluates placements with the evaluator of the reference scheduler
(`network_aware_k8s_scheduler/k8_scheduler/scheduler/evaluator`), which must be checked out
next to the simulator. Used by `tests/test_reference_parity.py` to check that
`simulator/evaluator.py` computes exactly the same violations and scores.

```sh
cd tools/reference_eval && go build -o /tmp/reference_eval . && echo '[]' | /tmp/reference_eval
```
Input (stdin): a JSON list of cases (nodes, links, pods with base assignment, penalties,
assignments to evaluate), see `main.go`. Output: the violations and score per assignment.
