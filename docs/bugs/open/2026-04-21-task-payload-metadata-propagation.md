---
status: open  # open | fixed
opened: 2026-04-21
fixed_pr: null  # set to PR number when moved to fixed/
priority: P0  # P0 = production broken; P1 = silent data loss or ux break; P2 = correctness; P3 = cleanup
invariant_violated: null  # e.g. docs/architecture/03_providers.md#sandbox-event-sink
related_rfc: null  # if a fix is being designed, link RFC here
---

# Bug: task_payload not propagated through Inngest dispatch to WorkerContext.metadata

## Symptom

`ReActGenericWorker._benchmark_slug()` raises
`ValueError("toolkit_benchmark not in ctx.metadata")` on every real run that
relies on toolkit-benchmark composition (e.g. any invocation that passes
`--toolkit-benchmark <slug>` on the CLI). `BenchmarkTask.task_payload` arrives
at the worker as `{}` and `WorkerContext.metadata` is also empty, so the
downstream slug lookup fails.

The payload is populated correctly at CLI composition time — keys like
`toolkit_benchmark` reach `ExperimentDefinitionTask.task_payload` in
Postgres — but the dispatch pipeline from that row to the in-process worker
drops it.

## Repro

Any production-shaped run that composes a toolkit benchmark, e.g.
`ergon run ... --toolkit-benchmark minif2f ...` against a `ReActGenericWorker`,
fails with the above `ValueError` inside the `worker-execute` Inngest function.

A state-level regression test reproduces the gap without Inngest:
`TaskExecutionService().prepare(...)` returns a `PreparedTaskExecution` with
no `task_payload` field at all, even though the backing
`ExperimentDefinitionTask.task_payload` contains
`{"toolkit_benchmark": "minif2f"}`.

## Root cause

`task_payload` is never threaded through the dispatch DTO chain. The DB side
is fine (`ergon_core/ergon_core/core/persistence/definitions/models.py` stores
`ExperimentDefinitionTask.task_payload` as JSON, and
`ergon_core/ergon_core/core/runtime/services/experiment_persistence_service.py:121`
writes it as `task_payload=dict(task.task_payload)`). But every DTO and
service between the DB row and the worker drops the field:

- `ergon_core/ergon_core/core/runtime/services/orchestration_dto.py`:
  `PreparedTaskExecution` (lines 63–78) has no `task_payload` field.
- `ergon_core/ergon_core/core/runtime/services/task_execution_service.py`:
  `_prepare_definition` (lines 170–258) reads `ExperimentDefinitionTask` but
  never reads `task.task_payload`; `_prepare_graph_native` (lines 76–166)
  has the same omission.
- `ergon_core/ergon_core/core/runtime/services/child_function_payloads.py`:
  `WorkerExecuteRequest` (lines 26–41) has no `task_payload` field.
- `ergon_core/ergon_core/core/runtime/inngest/execute_task.py:145-158`
  constructs `WorkerExecuteRequest(...)` without a `task_payload` kwarg.
- `ergon_core/ergon_core/core/runtime/inngest/worker_execute.py:65-78`
  builds `BenchmarkTask(...)` with no `task_payload` and `WorkerContext(...)`
  with empty `metadata`.

## Scope

Every real (non-stubbed) run using a toolkit-benchmark composition — i.e.
every invocation of `ReActGenericWorker` against a benchmark that relies on
`ctx.metadata["toolkit_benchmark"]` for slug resolution. Synthetic unit
tests that construct `BenchmarkTask` / `WorkerContext` directly are
unaffected, which is why the gap has not surfaced in the existing test
suite.

## Proposed fix

Add an optional `task_payload: dict[str, Any]` field (defaulting to `{}`) to
`PreparedTaskExecution` and `WorkerExecuteRequest`. Populate it in both
branches of `TaskExecutionService.prepare()` from the
`ExperimentDefinitionTask.task_payload` column, pass it through in
`execute_task.py`, and wire it to both `BenchmarkTask.task_payload` and
`WorkerContext.metadata` at the top of `worker_execute.py`. Cover with a
unit round-trip test plus a state test that asserts `prepare()` returns
the payload intact.

## On fix

When moving from `open/` to `fixed/`:
  - Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
  - If this bug violated an architecture invariant, confirm the invariant is
    restored (or the doc updated to reflect a revised invariant).
