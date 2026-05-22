# PR 11 Gap Register

Date: 2026-05-18

Branch audited: `codex/v2-pr-11-deletion-final-schema`

## P0 / P1 Gaps

### Final schema identity collapse is incomplete

The plan says `RunGraphNode` final identity is `(run_id, task_id)` with no
`id`, no `definition_task_id`, and no graph-edge definition dependency bridge.
On PR 11 head, `RunGraphNode` still has `id` as primary key and no `task_id`
column. `RunTaskExecution` and `RunTaskEvaluation` still carry both `node_id`
and `task_id`.

Worse, some readers already reference columns that do not exist on the current
model, such as `RunGraphNode.task_id` in read/evaluation code. That is a live
runtime correctness gap.

Decision needed: either finish the schema collapse in PR 11, or revise the PR
11 plan to keep `id` as the final runtime task identity and update all docs,
guards, and readers accordingly. The current halfway state is the riskiest
option.

### Launch provenance and definition metadata are inconsistent

`launch_run()` passes a definition id as `experiment_id`, but `RunRecord`
foreign-keys `experiment_id` to the old experiments/benchmark-definition
telemetry table shape. `persist_benchmark()` writes `ExperimentDefinition`
rows, not `BenchmarkDefinitionRecord` rows. The plan's final
`BenchmarkDefinitionRecord` shape does not match the current model.

This is not dead code. It is an unresolved data-model decision across
definition persistence, run provenance, read models, and migrations.

### Registry deletion plan does not match runtime reality

The process-local core registry remains public and runtime-used. It is exported
from `ergon_core.api`, used by workflow service, task management dynamic
subtasks, REST/test harnesses, CLI discovery/onboarding, and smoke fixtures.

PR 14 deletes `ergon_core/api/registry.py`; the live consumers must move to
object-bound `_type` snapshots, explicit imports, benchmark dependency
declarations, package entrypoints, or fixture-local factories.

### Sandbox lifecycle observability has split ownership

Behavioral provisioning is now object-bound via `Sandbox.provision()`, but
sandbox event/WAL bookkeeping still assumes manager-owned lifecycle. Direct E2B
provisioning can bypass manager created/closed events. Failure cleanup is also
duplicated: both failure propagation and sandbox cleanup handle failed-task
sandbox termination.

Final owner should be one thing. If it is `sandbox_cleanup`, propagation should
stop terminating sandboxes directly.

### Smoke lifecycle regressions were patched on PR 11

PR 11 commit `a613875` fixed the smoke lifecycle regressions that were visible
when this audit was first drafted. It changed smoke parent and recursive workers
so they plan children and return instead of polling child completion inside the
same `worker_execute` job. It also readies dependency-free dynamic children when
their parent completes, relaxes dynamic worker payloads with no model target,
and adds parser coverage for wrapped graph mutation events and backend context
part payloads.

This removes the smoke-fixture wait-semantics work from the follow-on stack.
It does not remove the remaining identity/API risks:

- dynamic child workers still receive `WorkerContext.task_id=None` in the
  dynamic `task/ready` path, with the real graph id carried through `node_id`;
- public `WorkerContext.spawn_task()` is still not Inngest-step memoized and
  can duplicate graph mutations/events on replay;
- the evaluator binding fallback can still produce eval jobs that the receiver
  rejects;
- the run/read schema mismatch can still break dashboard/read-model paths.

## P2 Gaps

### Dead evaluator fallback and dispatch DTOs remain

`Task.evaluator_binding_keys`, fanout fallback, `EvaluationService.prepare_dispatch()`,
and internal v1 evaluation dispatch DTOs remain despite the new per-evaluator
id-only path being canonical.

### Dynamic subtasks still have two authoring models

`WorkerContext.spawn_task(Task)` is the canonical object-bound path.
`TaskManagementService.add_subtask()` / `plan_subtasks()` and
`SubtaskLifecycleToolkit` slug tools still use registry synthesis. PR 14 deletes
those slug/registry authoring paths and leaves `SubtaskLifecycleToolkit` as a
worker-authoring object-bound toolkit.

This lane has correctness bugs, not only cleanup: `refine_task` updates graph
description without updating embedded `task_json`; dependency containment is not
enforced; duplicate sibling slugs are not consistently prevented; and
`WorkflowService` restart/abandon duplicate task-management lifecycle semantics
with weaker guards.

### Worker/task DTO bridges remain

`PreparedTaskExecution` and `WorkerExecuteJobRequest` still carry bridge fields
such as `assigned_worker_slug`, `worker_type`, `model_target`, and `node_id`.
Some of these feed traces/read models; others are likely removable once schema
identity is decided.

### Public toolkit surface is unstable

`Toolkit` is part of the v2 ReAct worker authoring story, but it is not exposed
through a stable builtins/baselines package path. It should not move into
`ergon_core`: core should expose the generic `Worker` contract, while
ReAct/toolkit composition remains a builtins baseline authoring surface.

### PR ledgers are not fully drained

At least one repository companion-file violator remains, and the walkthrough
sandbox acquire/release guard is still xfailed. PR 16 drains these completely:
no known-violator ledgers or xfails remain.

### Dashboard live contracts drift from backend contracts

PR 11 commit `a613875` added compatibility parsing for backend-wrapped graph
mutation events and backend context-part payloads. The remaining gap is now
narrower: graph mutation and context events are still not generated first-class
frontend event contracts, and frontend graph edge contracts still normalize
backend `source_task_id` / `target_task_id` into `source_node_id` /
`target_node_id`. PR 15 should replace those compatibility shims with canonical
generated contracts and final task-id vocabulary.

## PR 11 Work Already Present

These current-state facts are important context for planning the remaining PR
11 work:

- Production builtins are object-bound.
- Smoke fixture benchmarks are mostly object-bound.
- Inline evaluator persistence rows exist.
- `Task.from_definition()` handles nested worker/sandbox/evaluator objects.
- `worker_execute` requires a live sandbox.
- Legacy worker/evaluator bridge modules are gone.
- Criterion executor modules are gone.
- `saved_specs` is gone.
