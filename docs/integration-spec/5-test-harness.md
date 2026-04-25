# Test Harness Design

This document defines the shared infrastructure all integration tests use — stub workers, assertion helpers, fixture pattern, and xfail conventions.

## Harness Components

Every test needs four ingredients:

**1. Stub workers** — workers that deterministically succeed, fail, or spawn subtasks with no E2B or LLM dependency. The system already has `training-stub` and the smoke worker fixtures. The integration tier needs its own small named set:
- `StubSuccessWorker` — returns `WorkerOutput(success=True)` immediately
- `StubFailWorker` — raises a controlled exception
- `StubSubtaskWorker(plan)` — calls `plan_subtasks()` with a provided spec, then succeeds

**2. A run submitter** — posts a `benchmark/run-request` event to the local Inngest dev server via the existing `inngest_client` and returns the `run_id`.

**3. A run poller** — polls `RunRecord.status` directly against Postgres until terminal. Times out with a clear message if convergence doesn't happen within a threshold (suggested: 30s for stub-only runs).

**4. Shared assertion helpers** — functions that take a `run_id` and assert the cross-cutting invariants above. These live in `tests/integration/helpers/` and are imported by every test, not copy-pasted.

The pattern for every test is then:

```python
run_id = submit_run(worker="stub-success", tasks=[...])
await wait_for_terminal(run_id, timeout=30)

assert_run_completed(run_id)           # RunRecord
assert_all_nodes_terminal(run_id)      # graph
assert_wal_complete(run_id)            # mutations
assert_executions_have_outputs(run_id) # telemetry
# ...plus test-specific assertions
```

## Fixture Layout

```
tests/integration/
├── conftest.py                  ← Inngest + Postgres session fixtures (scoped only to tests that need live infra)
├── helpers/
│   ├── __init__.py
│   ├── run_factory.py           ← submit_run(), wait_for_terminal()
│   ├── assertions.py            ← assert_run_completed(), assert_wal_complete(), assert_all_nodes_terminal(), etc.
│   └── stubs.py                 ← StubSuccessWorker, StubFailWorker, StubSubtaskWorker
├── smokes/
├── swebench_verified/
└── minif2f/
```

Note that `conftest.py` should be split: the Inngest preflight (TCP probe + `pytest.exit()`) should be in a sub-conftest scoped only to the directories that actually need live Inngest, not session-wide.

## Cross-Cutting Invariant Helpers

| Invariant | What to assert |
|-----------|---------------|
| WAL completeness | Every `RunGraphNode` in the run has at least one `RunGraphMutation` entry |
| Execution coverage | Every node that reached `COMPLETED` or `FAILED` has a `RunTaskExecution` with non-null `completed_at` |
| No orphaned executions | Every `RunTaskExecution.node_id` references an existing `RunGraphNode` in the same run |
| RunRecord terminal consistency | `COMPLETED` implies all nodes are in `{COMPLETED, CANCELLED}`; `FAILED` implies at least one node is `FAILED` |
| Edge–node consistency | Every `EDGE_SATISFIED` edge has a source node with `status == COMPLETED`; every `EDGE_INVALIDATED` edge does not |
| Level consistency | Every node with `parent_node_id != NULL` has `level == parent.level + 1` |
| Append-only WAL | Mutation count for any given node only ever increases; no mutation rows are deleted or updated |
| Timeline consistency | `started_at ≤ completed_at` on every `RunTaskExecution` |

These helpers must be called at the end of every control-flow test, not copy-pasted. They live in `tests/integration/helpers/assertions.py`. Each takes `run_id: UUID` and a database session and raises `AssertionError` with a descriptive message on failure.

Once violated assumption L is resolved (`triggered_by_mutation_id` added to `RunGraphMutation`), add a ninth invariant:

| Cascade lineage | Every `RunGraphMutation` with `reason` in `{parent_failed, parent_restart, dep_invalidated, downstream_invalidation}` has a non-null `triggered_by_mutation_id` |

## xfail Conventions

Tests for known-broken behaviours (violated assumptions A–L documented in `4-violated-assumptions.md`) are marked with:

```python
@pytest.mark.xfail(
    strict=True,
    reason="violated assumption X: <one-line description>",
)
def test_name(): ...
```

Rules:
- `strict=True` is required. Without it, an xfail test that unexpectedly passes is silently ignored; with it, CI fails until the marker is explicitly removed.
- The `reason` string must cite the assumption letter so it traces directly to `4-violated-assumptions.md`.
- When the production fix is merged and the test passes, remove the `xfail` marker in the same PR as the fix.
- Never use `xfail` for tests that are merely slow or environment-dependent — use `pytest.mark.slow` or `pytest.mark.docker_build` instead.

Reference table of current xfail targets:

| Assumption | Short description | Marker reason string |
|---|---|---|
| A | run/cleanup kills one sandbox per run | `"violated assumption A: run/cleanup uses single sandbox_id from RunRecord.summary_json"` |
| B | is_stub_sandbox_id in prod path | `"violated assumption B: stub sandbox logic leaks into production handlers"` |
| C | evaluate_task_run uses empty BenchmarkTask | `"violated assumption C: evaluate_task_run constructs BenchmarkTask with empty strings"` |
| D | empty-string defaults instead of nullable | `"violated assumption D: criterion fields use empty-string defaults not None"` |
| E | InngestCriterionExecutor sandbox reuse unverified | `"violated assumption E: evaluator may spin up new sandbox instead of reusing task sandbox"` |
| F | restart_task ignores stale containment children | `"violated assumption F: restart_task does not cancel prior-execution subtask children"` |
| G | criterion/evaluate orphaned event | `"violated assumption G: CriterionEvaluationEvent has no registered handler"` |
| H | prior-attempt sandbox leaks on restart | `"violated assumption H: failed-attempt sandbox not killed before restart container starts"` |
| I | silent missing evaluations on completed run | `"violated assumption I: completed run with missing RunTaskEvaluation rows emits no signal"` |
| J | children marked CANCELLED not FAILED on parent failure | `"violated assumption J: parent failure cascade sets CANCELLED not FAILED on containment children"` |
| K | restart does not reset containment subtree | `"violated assumption K: restart_task does not reset containment subtree recursively"` |
| L | no causal lineage on RunGraphMutation | `"violated assumption L: RunGraphMutation has no triggered_by_mutation_id field"` |
