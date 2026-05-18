# PR 12 Runtime Identity And Dynamic Task Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make runtime task identity coherent after PR 11 and fix dynamic child task execution so object-bound recursive workers can rely on the public `WorkerContext` facade.

**Architecture:** This PR implements the RFC v2 target: `task_id` is the public and runtime identity. Legacy `node_id` vocabulary is removed from models, schema, events, job payloads, worker context, telemetry, dashboard registration, and tests rather than hidden behind adapters. Dynamic subtasks must create graph-native task snapshots, pass the canonical task id into workers, and make worker-authored spawning replay-safe.

**Tech Stack:** Python, SQLModel, Alembic, Inngest, pytest.

---

## PR 11 Head Update

PR 11 commit `a613875` fixed the smoke-fixture lifecycle deadlock by making
smoke parent and recursive workers plan children and return instead of polling
child completion inside `worker_execute`. It also readies dependency-free
dynamic children on parent completion. This PR therefore no longer owns smoke
fixture wait-semantics changes. It still owns the underlying identity cleanup:
dynamic worker payloads can still carry `task_id=None` with the real id in
`node_id`, and `WorkerContext.task_id` can still be null for dynamic children.

## Locked Decisions

- Final runtime identity is `task_id`.
- `node_id` bridge fields are removed outright, not retained internally, with
  final end-to-end tests as the merge gate.
- `RunRecord.experiment_id` is renamed/replaced with explicit `definition_id`
  provenance rather than overloaded.

## Scope

This PR should land immediately after PR 11. It should not change evaluator
semantics, public registry decisions, or frontend dashboard contract generation
except where they directly depend on `task_id` naming.

## Primary Files

- Modify: `ergon_core/ergon_core/core/persistence/graph/models.py`
- Modify: `ergon_core/ergon_core/core/application/graph/repository.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/execute_task.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/worker_execute.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/sandbox_setup.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/persist_outputs.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py`
- Modify: `ergon_core/ergon_core/api/worker/context.py`
- Modify: `ergon_core/ergon_core/core/application/tasks/management.py`
- Modify: `ergon_core/ergon_core/api/worker/results.py`
- Modify: `ergon_core/ergon_core/core/application/read_models/*`
- Modify: `ergon_core/ergon_core/core/infrastructure/dashboard/event_contracts.py`
- Modify: `ergon_core/tests/unit/runtime/test_identity_invariants.py`
- Modify: `ergon_core/tests/unit/runtime/test_spawn_dynamic_task.py`
- Modify: `ergon_core/tests/unit/runtime/test_spawned_task_handle.py`
- Modify: `ergon_core/tests/unit/runtime/test_child_function_payloads.py`
- Modify: `ergon_core/tests/unit/runtime/test_graph_worker_identity.py`
- Modify: `ergon_core/tests/unit/runtime/test_worker_context_containment.py`
- Modify: `ergon_core/tests/unit/runtime/test_run_graph_task_snapshot.py`

## Code TODOs / Comments To Remove

When PR 12 lands, remove or rewrite the code comments that describe
`node_id` as a temporary bridge rather than leaving them for PR 16. Expected
cleanup targets include:

- `ergon_core/ergon_core/api/worker/context.py`: remove the transitional
  `task_id` field description that says PR 11 will make it required, remove
  the `node_id` bridge field and its `RunGraphNode.id` description, and delete
  worker-context tests/fixtures that use `context.node_id` as a public escape
  hatch.
- `ergon_core/ergon_core/core/application/graph/repository.py`: remove comments
  that explain `RunGraphNode.id` or parent/source/target node columns as the
  pre-PR-12 identity shape once the repository operates on `task_id`.
- `ergon_core/ergon_core/core/application/tasks/execution.py`: remove
  `TODO(PR 11)` comments about bridge metadata and worker assignment rows if
  the PR has moved runtime worker selection entirely onto the task snapshot.
- `ergon_core/ergon_core/core/application/graph/propagation.py`: remove
  `execution_id  # TODO: dead param` if the identity rewrite proves the
  parameter unused.
- Dashboard and e2e helper comments/tests that mention `parent_node_id`,
  `source_node_id`, `target_node_id`, or "node_id join" should be removed when
  the backend vocabulary changes. If frontend parser compatibility still needs
  work, leave only the PR 15-owned parser note, not a backend identity TODO.

## Tasks

### Task 1: Lock The Identity Decision In Tests

- [ ] Add failing tests proving `RunGraphNode` exposes `task_id` as the canonical runtime identifier and does not require public callers to use `node_id`.
- [ ] Extend `ergon_core/tests/unit/runtime/test_identity_invariants.py` to assert graph, execution, evaluation, task events, and worker context all agree on the same task id for a static task.
- [ ] Add a dynamic child variant proving a spawned child receives `WorkerContext.task_id == spawned_task_id`.
- [ ] Run:

```bash
cd /Users/charliemasters/.config/superpowers/worktrees/ergon/codex-v2-pr-11-deletion-final-schema
uv run pytest ergon_core/tests/unit/runtime/test_identity_invariants.py -q
```

Expected before implementation: fail on missing or inconsistent `task_id` fields.

### Task 2: Finish The Graph Model Collapse

- [ ] Update `RunGraphNode` so `(run_id, task_id)` is the runtime identity.
- [ ] Remove `RunGraphNode.id` as the public/runtime identity; do not leave a public/internal `node_id` bridge behind.
- [ ] Update `RunGraphEdge` to store `source_task_id` and `target_task_id`.
- [ ] Update `RunTaskExecution`, `RunTaskEvaluation`, and related repositories so `task_id` is canonical and old `node_id` bridge fields are removed.
- [ ] Rename or replace `RunRecord.experiment_id` with `definition_id` so run provenance points at the immutable definition without overloading the old experiment table relationship.
- [ ] Update the final Alembic reset to match the selected schema.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_run_graph_task_snapshot.py ergon_core/tests/unit/runtime/test_graph_traversal.py -q
```

Expected after implementation: graph read/write tests pass using `task_id`.

### Task 3: Repair Job Payloads And Event Flow

- [ ] Update `TaskReadyEvent`, `WorkerExecuteJobRequest`, sandbox setup requests, output persistence requests, and evaluator requests so the public task identifier is always `task_id`.
- [ ] Remove payload branches where dynamic tasks send `task_id=None` and smuggle the real id through `node_id`.
- [ ] Update `execute_task` so static and dynamic tasks produce the same downstream payload shape.
- [ ] Update `worker_execute` so `WorkerContext._for_job()` receives the canonical task id for every task.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_child_function_payloads.py ergon_core/tests/unit/runtime/test_graph_worker_identity.py -q
```

Expected after implementation: static and dynamic children use the same task-id path.

### Task 4: Make Worker-Authored Spawning Replay-Safe

- [ ] Add a failing test showing repeated Inngest replay of `WorkerContext.spawn_task()` does not create duplicate graph nodes or duplicate child-ready events.
- [ ] Extend `_StepAwareTaskManagementService` or the equivalent step wrapper so `spawn_dynamic_task()` is memoized under `ctx.step.run` / `ctx.step.invoke`, matching `plan_subtasks()`.
- [ ] Keep idempotency at the worker facade boundary; do not require worker authors to pass custom replay keys.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_spawn_dynamic_task.py ergon_core/tests/unit/runtime/test_spawned_task_handle.py -q
```

Expected after implementation: replay emits one child task and one handle.

### Task 5: Preserve The PR 11 Smoke Lifecycle Fix While Cleaning Identity

- [ ] Keep the PR 11 `a613875` smoke behavior: smoke parent and recursive workers plan children and return instead of polling child completion inside `worker_execute`.
- [ ] Add or update a full-stack unit/integration smoke proving dependency-free dynamic children become ready after parent completion.
- [ ] Add coverage proving this behavior does not require worker code to read `context.node_id` once PR 12 identity cleanup is complete.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py ergon_core/tests/unit/runtime/test_smoke_topology_drift.py -q
```

Expected after implementation: recursive smoke topology still passes, and public worker code no longer needs direct `context.node_id` escape hatches.

### Task 6: Update Read Models And Architecture Guards

- [ ] Update run snapshots, dashboard registration, and telemetry DTOs to expose `task_id` consistently.
- [ ] Remove or tighten tests that permit `node_id` as public runtime vocabulary.
- [ ] Add architecture guard coverage preventing new application-layer public DTOs from adding `node_id`.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_run_read_service.py ergon_core/tests/unit/architecture/test_runtime_read_boundaries.py -q
```

Expected after implementation: read models use task id vocabulary and architecture guards pass.

## Acceptance Criteria

- Dynamic children receive a non-null `WorkerContext.task_id`.
- Worker-authored `spawn_task()` is Inngest replay-safe.
- Public runtime DTOs, events, tests, and telemetry no longer expose `node_id`.
- Run provenance is explicit through `definition_id`.
- Schema reset and SQLModel models agree on the chosen identity.
- Unit tests covering static tasks, dynamic tasks, read models, and recursive smoke behavior pass.
- Final end-to-end smoke coverage passes on the branch before merge.

## Do Not Include

- Evaluator dispatch deletion.
- Registry deletion work.
- Dashboard frontend parser rewrites beyond backend contract naming required by this identity change.
