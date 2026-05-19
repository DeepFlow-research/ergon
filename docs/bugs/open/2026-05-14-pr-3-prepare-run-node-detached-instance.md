---
status: open
opened: 2026-05-14
fixed_pr: null
priority: P0
invariant_violated: null
related_rfc: docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/
---

# Bug: PR 3 `_prepare_run_node` accesses ExperimentDefinition after session close

## Symptom

Every benchmark smoke (`minif2f`, `swebench-verified`, `researchrubrics`)
on `feature/v2-pr-*` branches starting at PR 3 hangs in
`status: "running"` with `context_event_count: 0` and `error: null`
until the harness times out at 270s. The run never produces a single
context chunk, never transitions out of running, and never surfaces
the underlying exception.

Confirmed regression boundary from CI history:

- **PR 52** (PR 1 run-tier snapshot, sha `79d043c`): smokes ✅
- **PR 52** (PR 2 typed run-node boundary, sha `03409b3`): smokes ✅
- **PR 53** (PR 3 worker_execute typed run nodes, sha `8651fd3`): smokes ❌
- **PR 54** (PR 4 sync fanout): smokes ❌
- **PR 55** (PR 4.5 ANN gaps): smokes ❌
- **PR 56** (PR 5 object-bound API): smokes ❌ (first surfaced as
  `ConfigurationError: task.worker is None` — masked the underlying
  hang. PR 5's `_legacy_worker_bridge.py` fix restored compat with
  `TaskSpec`-returning benchmarks; smokes now hit the same hang the
  earlier PRs hit.)

## Repro

`gh run view --log --job 75958883560` (PR 56 minif2f) shows the
sequence:

```text
mutations: [
  {sequence: 0, mutation_type: "node.added", target_task_slug: "mathd_algebra_478"},
  {sequence: 1, mutation_type: "annotation.set", ...},
  {sequence: 2, mutation_type: "node.status_changed", ...},   # pending → ready
  {sequence: 3, mutation_type: "node.status_changed", ...},   # ready → running
]
executions: [{status: "running", error: null, task_slug: "mathd_algebra_478"}]
graph_nodes: [{status: "running", level: 0, parent_node_id: null, ...}]
context_event_count: 0
```

The api container log dump (`docker compose logs api --tail 200`) is
silent past Alembic startup — per CLAUDE.md the uvicorn reloader eats
worker-side stdout in CI. The Inngest GraphQL endpoint isn't reachable
from CI, so the function-level error (if any) is lost.

## Root cause

**Confirmed empirically** via local stack + Inngest GraphQL probe at
`http://localhost:8289/v0/gql`. The hypothesis about sandbox-key
divergence was wrong; the actual error is a SQLAlchemy
`DetachedInstanceError` in `ergon-core-task-execute`:

```
Instance <ExperimentDefinition at 0x...> is not bound to a Session;
attribute refresh operation cannot proceed
(https://sqlalche.me/e/20/bhk3)
```

Worker-execute never fires — the orchestrator (`execute_task`)
crashes during `prepare`, before sandbox_setup. Inngest swallows the
SQLAlchemy error and silently retries with exponential backoff. The
test sees `status: "running"` (task was set RUNNING before the crash)
and `context_event_count: 0` (no worker ever ran) until the 270s
timeout.

**Source:** `ergon_core/.../application/tasks/execution.py:88-169`
(`TaskExecutionService._prepare_run_node`, introduced in PR 3).

The function takes this shape:

```python
with get_session() as session:
    view = await self._graph_repo.node(...)
    definition = session.get(ExperimentDefinition, command.definition_id)
    ...
    session.add(execution); session.flush()
    await self._graph_repo.update_node_status(...)
    session.commit()                       # ← expires all ORM instances
                                           #   (expire_on_commit=True default)
# ← session closes here

return PreparedTaskExecution(
    ...,
    benchmark_type=definition.benchmark_type,   # ← DetachedInstanceError
    execution_id=execution.id,                  # ← DetachedInstanceError
)
```

`session.commit()` expires every ORM instance loaded in the session
(SQLAlchemy default `expire_on_commit=True`). The next attribute
access triggers a refresh from the DB — but the `with` block has
already closed the session, so the refresh fails.

Pre-PR-3, the equivalent code paths (`_prepare_legacy_graph_native`
and `_prepare_legacy_definition`) read the same fields *inside* the
session block before commit, so the bug didn't exist.

## Why CI logs hid this

CLAUDE.md warns that uvicorn's reloader eats handler stdout in the api
container, so `docker compose logs api` was empty. The smoke test
only sees the harness-level `TimeoutError` because Inngest absorbs the
SQLAlchemy error from `task-execute` into its retry queue. The
authoritative source — Inngest's GraphQL endpoint — is reachable only
from the host network, not from CI runners.

## Scope

- All three canonical smokes (`minif2f`, `swebench-verified`,
  `researchrubrics`) fail on every push to `feature/v2-pr-3+` branches.
- Unit / state / integration tests are unaffected — the regression is
  observable only against a live sandbox lifecycle.
- Production unaffected — none of the v2 PRs have shipped to `main`
  yet (latest `main` is sha `3aaa844` 2026-05-13).

## Proposed fix

Capture the ORM-derived scalars (`definition.benchmark_type` and
`execution.id`) into local variables *inside* the session block before
`session.commit()` expires the instances. Two-line fix.

```python
# inside the `with get_session() as session:` block, before commit
benchmark_type = definition.benchmark_type
execution_id = execution.id
...
session.commit()

# outside the block — use the captured locals
return PreparedTaskExecution(
    ...,
    benchmark_type=benchmark_type,
    execution_id=execution_id,
)
```

Alternative considered: pass `expire_on_commit=False` to the session
factory. Rejected — that's a global behaviour change that would mask
similar bugs elsewhere. The narrow fix is to read the values you need
before the lifetime boundary, which is also clearer to future readers.

**Follow-ups worth queuing (not blocking this fix):**

1. The architecture guard `test_repository_layer_conventions.py`
   should add a check that no `PreparedTaskExecution`-style return
   value is constructed outside the session block from ORM instances
   loaded inside. Hand-rolled grep would catch
   `definition.<attr>` after `session.commit()`.
2. Inngest's retry on SQLAlchemy errors hides bugs. Worth a separate
   bug to either classify SQLAlchemy errors as `NonRetriableError` at
   the orchestrator boundary, or to flush the function-error payload
   into the api container logs so `docker compose logs api` would
   have surfaced this without GraphQL.

## On fix

When moving from `open/` to `fixed/`:
  - Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
  - Update the v2 implementation-plan doc set (PR 3 plan) to call
    out the sandbox-key alignment.
