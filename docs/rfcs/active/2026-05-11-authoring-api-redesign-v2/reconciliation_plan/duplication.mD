# Duplication And Core-Construct Audit On PR 11 Head

Date: 2026-05-18

Branch audited: `codex/v2-pr-11-deletion-final-schema`

## Reconciliation Map

Use this section as the review index for the rest of the document:

- Benchmark/task definition duplication is owned mostly by
  [PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md), with
  evaluator-row cleanup bounded by
  [PR 13](pr13-evaluation-cleanup.md) and residual dead-code sweep by
  [PR 16](pr16-core-debt-sweep.md).
- Worker context identity and worker-authored dynamic actions are owned by
  [PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md); the builtins
  toolkit import surface is owned by
  [PR 14](pr14-public-api-registry-surface.md).
- Sandbox ownership and cleanup consolidation are owned by
  [PR 16](pr16-core-debt-sweep.md), after PR 12 finishes identity cleanup.
- Evaluator/rubric/criterion dispatch cleanup is owned by
  [PR 13](pr13-evaluation-cleanup.md).
- Registry, serialization, component discovery, and public import boundaries
  are owned by [PR 14](pr14-public-api-registry-surface.md), which deletes the
  core registry and persistent component catalog.
- Data access, run copying, launch provenance, and schema identity are owned by
  [PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md).
- Runtime orchestration identity bugs are owned by
  [PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md); failed-task
  sandbox cleanup ownership is finished in [PR 16](pr16-core-debt-sweep.md).
- Dynamic subtask containment spans
  [PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md) for identity
  and replay safety, [PR 14](pr14-public-api-registry-surface.md) for
  removing slug/registry authoring paths while keeping `SubtaskLifecycleToolkit`
  worker-authored, and [PR 16](pr16-core-debt-sweep.md) for duplicate lifecycle
  methods.
- Dashboard/read-model/event contract drift is owned by
  [PR 15](pr15-dashboard-event-contracts.md), after PR 12 settles final task-id
  vocabulary.

The intended destination across the stack is summarized in
[post_pr16_flow_digest.md](post_pr16_flow_digest.md).

## Benchmark And Task

Reconciliation owner:
[PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md) for task/run
identity and the definition-to-run copy shape;
[PR 13](pr13-evaluation-cleanup.md) for deciding which evaluator metadata rows
remain because evaluation still needs them;
[PR 16](pr16-core-debt-sweep.md) for deleting residual dead files/comments once
the shape is settled.

The canonical path is now object-bound. `Benchmark.build_instances()` returns
`Mapping[str, Sequence[Task[BaseModel]]]`, and `Task` carries the runtime graph
fields plus `worker`, `sandbox`, and `evaluators`. Production MiniF2F,
SWE-Bench Verified, GDPEval, ResearchRubrics, and the smoke fixture benchmarks
all construct object-bound `Task` objects.

Duplication remains in the persistence shape. `persist_benchmark()` stores full
`task_json`, but definition tables also store workers, evaluators, task payloads,
assignments, dependencies, and task-evaluator rows separately. Some duplication
is currently load-bearing: evaluator rows are still needed for
`RunTaskEvaluation.definition_evaluator_id`, and worker assignment rows still
feed preparation/read-model metadata. The system therefore has two partially
canonical representations of the same authored task: the object snapshot in
`task_json`, and normalized definition rows.

There is also a smaller but real logic duplication inside definition writing:
`persist_benchmark()` validates by calling `benchmark.build_instances()`, then
calls `build_instances()` again while persisting. Dataset-backed benchmarks can
load or sample twice, and the graph validated may not be the exact graph
persisted.

## Worker, WorkerContext, Toolkit, WorkerOutput

Reconciliation owner:
[PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md) for
`WorkerContext.task_id`, job payload identity, worker-authored `spawn_task()`
replay safety, and removal of public `node_id` dependence;
[PR 14](pr14-public-api-registry-surface.md) for keeping `Toolkit` out of core
and giving it a stable builtins/baselines import path;
[PR 16](pr16-core-debt-sweep.md) for deleting dead output extraction or stale
worker comments after the runtime path is final.

The worker execution path is mostly canonical. `worker_execute` reads the
run-tier task view through `WorkflowGraphRepository.node(..., sandbox_id=...)`,
requires `task.sandbox.is_live`, validates `task.worker`, constructs
`WorkerContext._for_job()`, consumes the worker stream, persists context chunks,
and persists exactly one terminal `WorkerOutput`.

Duplication remains around toolkits and manager-facing dynamic tools.
`ReActWorker(toolkit=...)` is now the active baseline pattern, but the `Toolkit`
base lives under `ergon_builtins/ergon_builtins/workers/baselines/toolkit.py`
and is not exported through a stable builtins/baselines authoring facade.
`Toolkit` should not move into `ergon_core`: core owns the generic `Worker`
contract, while ReAct/toolkit composition is a builtins baseline concern. If
toolkit authoring is part of the public surface, the stable path should remain
under builtins, not `ergon_core.api`.

`WorkerContext` is the object-bound worker facade, but it still carries bridge
identity: both `task_id` and `node_id`. Many smoke fixtures and CLI tests still
read `context.node_id`. The PR 11 plan says this should collapse to task id,
but the branch has not done that. This is not merely a rename: job payloads,
telemetry rows, dashboard registration, task events, and test helpers still use
`node_id`.

ResearchRubrics has an important behavioral regression candidate: the v2
worker is a plain `ReActWorker` with `ResearchRubricsToolkit`, but the toolkit
only exposes bash/write_report/read_report. The old web/search tool language
remains in `_tools.py`, while the legacy worker files that apparently owned
those tools are gone. If the benchmark expects a sourced report, this is a
functional gap, not dead code.

## Sandbox And Sandbox Runtime

Reconciliation owner:
[PR 16](pr16-core-debt-sweep.md) for single-owner sandbox cleanup, actual
cancelled-task sandbox release, stale lifecycle comments, and failure
propagation not terminating sandboxes directly. [PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md)
must land first where cleanup payloads depend on final task identity.

The canonical behavior path is object-bound. `sandbox_setup` loads the typed
task view and calls `task.sandbox.provision()`. `worker_execute` and
`evaluate_task_run` rehydrate the task with the live `sandbox_id`, then builtins
bind through the sandbox runtime helpers. Evaluators detach local runtime
handles; terminal cleanup is intended to happen through `sandbox_cleanup` on
`task/completed` or `task/failed`.

The duplicate ownership problem is observability and failure cleanup. Builtin
`Sandbox.provision()` now provisions E2B directly and returns a direct runtime,
but manager event/WAL bookkeeping still assumes `BaseSandboxManager` owns
created sandboxes. Cleanup later calls manager termination, which can kill the
raw E2B sandbox but bypass manager-created/closed bookkeeping for direct
provisioned sandboxes. In addition, `TaskFailedEvent` is handled by both
failure propagation and sandbox cleanup, and failure propagation still calls
the sandbox termination path directly. That creates two registered terminators
for the same failure event.

Cancelled-task cleanup is also incomplete. The event/job docstring promises
sandbox release on `task/cancelled`, but `TaskCleanupService` explicitly leaves
E2B release unimplemented and returns `sandbox_released=False`. A manager or
cascade cancellation can therefore keep a running sandbox alive until timeout
unless a separate terminal cleanup path happens to run.

There are also public fields with unclear force. `Sandbox.requires_network` is
declared and set by builtins, but current provisioning passes template,
timeout, envs, and API key only. `SandboxSetupRequest.envs` and `sandbox_slug`
exist but are not consumed in the object-bound setup path.

## Evaluator, Rubric, Criterion

Reconciliation owner:
[PR 13](pr13-evaluation-cleanup.md) owns deletion of evaluator binding fallback,
v1 dispatch DTOs, `EvaluationService.prepare_dispatch()` as a runtime path, and
stale criterion executor references. [PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md)
is a prerequisite only where evaluator rows still carry bridge task/node ids.

The evaluator execution path is now comparatively narrow. `persist_benchmark()`
mirrors inline `Task.evaluators` into evaluator rows,
`execute_task._fan_out_evaluators()` counts `task.evaluators`, and
`evaluate_task_run` reloads the run-tier task and executes
`task.evaluators[evaluator_index]` through `EvaluationService.evaluate()`. The
old executor modules and legacy evaluator bridge are absent on PR 11 head.

The remaining duplication is stale dispatch/payload infrastructure.
`EvaluationService.prepare_dispatch()` and its related DTOs reconstruct
definition-table evaluator dispatches even though production uses
`TaskEvaluateRequest` and the run-tier task snapshot. That old path appears
test-only. `Task.evaluator_binding_keys` also remains as a public field, and
fanout still falls back to it. Since persistence rejects it and the eval worker
does not support it, this fallback is harmful rather than transitional.

The result side is relatively stable: `CriterionOutcome` and
`EvaluationSummary` flow into `RunTaskEvaluation.summary_json`, and dashboard
DTOs are emitted from the persisted summary. There is still some compatibility
magic in outcome slug/name handling, but it is lower priority than deleting the
dead dispatch path.

## Registry, Serialization, Component Discovery

Reconciliation owner:
[PR 14](pr14-public-api-registry-surface.md) owns deletion of the core registry,
replacement of discovery/onboarding/test consumers, public import cleanup,
deletion of persistent component catalog files/tests, and the
builtins/baselines toolkit path.

The `_type` path is the canonical object-bound serializer. `Task`, `Worker`,
`Sandbox`, `Criterion`, and `Evaluator` inject `module:qualname`; rehydration
goes through `ergon_core.api._serialization.import_component()` and
`import_component_subclass()`.

But the process-local registry is still public and live:
`ergon_core.api.__init__` exports `ComponentCatalog` and `registry`, and
`ergon_core.api.registry` remains in tree. Core runtime still imports it for
workflow setup, dynamic subtask worker validation, REST startup/test harnesses,
CLI discovery, onboarding, and smoke fixtures. This is a major discrepancy
with the PR 11 deletion plan, which lists `api/registry.py` as a deletion
target.

The current state is therefore not "registry deleted." It is "builtins registry
tables deleted, core process-local registry still used." PR 14 resolves this by
deleting the core process-local registry entirely and replacing CLI/discovery,
onboarding, REST startup, test harness, and smoke fixture consumers with
explicit imports, dependency declarations, entrypoints, or fixture-local
factories.

## Data Access, Definition Persistence, And Run Copying

Reconciliation owner:
[PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md) owns final
schema identity, `RunGraphNode`/edge/task execution/evaluation id vocabulary,
run launch provenance, definition-to-run copying, and Alembic reset alignment.
[PR 13](pr13-evaluation-cleanup.md) may narrow evaluator definition metadata
after PR 12 decides the final FK/read-model shape.

Definition persistence is in `persist_benchmark()`. Launch is in `launch_run()`.
Definition-to-run copying is in `WorkflowGraphRepository.initialize_from_definition()`.
Runtime reads are centered on `WorkflowGraphRepository.node()`, which is the
right architectural boundary.

The biggest duplication is schema identity. The PR 11 plan promises final graph
identity as `(run_id, task_id)` with no `RunGraphNode.id`, but the model still
has `id` as the primary key and no `task_id` column. Telemetry still carries
both `node_id` and `task_id` on execution/evaluation rows. Some code now
references `RunGraphNode.task_id` as if the collapse had happened, while the
model has not caught up.

There is also provenance ambiguity. `launch_run()` passes `experiment_id` as
the definition id, while `RunRecord.experiment_id` is foreign-keyed to the old
`experiments` table shape. `persist_benchmark()` writes no matching
`BenchmarkDefinitionRecord`, so fresh launches can depend on an unrelated or
missing row. The PR 11 plan's final `BenchmarkDefinitionRecord` shape does not
match the current telemetry model.

The Alembic reset is also only partially aligned with the plan. The current
single migration uses `SQLModel.metadata.create_all()` / `drop_all()` and
revision `"00000000"`, while the PR 11 plan calls for a hand-audited final
schema and a non-downgradeable reset.

## Runtime Orchestration And Propagation

Reconciliation owner:
[PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md) owns the
`task/ready` -> `execute_task` -> `worker_execute` identity repair and dynamic
child context correctness. [PR 16](pr16-core-debt-sweep.md) owns failure
propagation vs sandbox cleanup single-owner behavior after the identity fix.

The live event flow is still a multi-job orchestrator:
`task/ready -> execute_task -> sandbox_setup -> worker_execute -> persist_outputs -> evaluate_task_run fanout -> task/completed|task/failed -> propagation + sandbox cleanup`.

This is final-shape behavior despite older plan text that implied some job
files would be deleted. The duplicate area is failure cleanup: failed task
events currently reach both propagation and sandbox cleanup, and propagation
still has a direct termination call. The final owner should be `sandbox_cleanup`;
propagation should handle graph/run state only.

The prepare failure path is still awkward. If preparation fails before an
execution row exists, `execute_task` logs loudly but leaves the graph node in a
bad state because `payload.task_id` may be `None` for dynamic subtasks and the
code still relies on bridge identity. This is another symptom of incomplete
`node_id`/`task_id` collapse.

There is a concrete dynamic-child identity bug in the event flow. Dynamic
`task/ready` events intentionally carry `task_id=None` and the real graph id in
`node_id`. `execute_task` passes that `None` into
`WorkerExecuteJobRequest.task_id`, and `worker_execute` constructs
`WorkerContext(task_id=None, node_id=...)`. Dynamic workers using the public
facade (`spawn_task`, `subtasks`, `descendants`, containment methods) therefore
fail or see empty state, while smoke fixtures can hide the problem by bypassing
the facade and using `context.node_id` plus direct task-management services.

PR 11 commit `a613875` removed the smoke-fixture version of this deadlock:
smoke parent and recursive workers now plan children and return, and smoke
assertions wait outside the parent worker execution path. That does not solve
the broader identity duplication above: dynamic worker payloads still carry
`task_id=None` plus `node_id`, and `WorkerContext.task_id` can still be null for
dynamic children until the PR 12 identity cleanup lands.

## Dynamic Subtasks And Containment

Reconciliation owner:
[PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md) owns object-bound
dynamic child identity, `WorkerContext.spawn_task()` replay safety, dependency
containment, duplicate sibling guards, and `refine_task()`/`task_json`
coherence. [PR 14](pr14-public-api-registry-surface.md) owns deletion of
slug/registry authoring paths and makes `SubtaskLifecycleToolkit`
worker-authoring/object-bound only. [PR 16](pr16-core-debt-sweep.md) owns
deletion or consolidation of duplicate lifecycle methods once the API boundary
is explicit.

There are two dynamic-subtask surfaces. The canonical v2 surface is
`WorkerContext.spawn_task(Task)` to `TaskManagementService.spawn_dynamic_task()`,
which writes a graph-native node with object-bound `task_json` and no definition
row.

The legacy slug/registry surface remains:
`TaskManagementService.add_subtask()` and `plan_subtasks()` accept slugs and
`assigned_worker_slug`, validate through `registry.workers`, and synthesize
subtask `task_json` from the parent task and registry worker class.
`SubtaskLifecycleToolkit` exposes both object-bound context tools and explicit
slug-path tools. PR 14 deletes those slug/registry paths rather than retaining
them as admin APIs. The context path supports object-bound `add_subtask`, but
`plan_subtasks` is unavailable through context and only exists in the
slug-based path before PR 14.

Containment is split too. `WorkerContext.cancel_task`, `refine_task`,
`restart_task`, `get_task`, and `descendants` enforce descendant checks. The
slug path in `SubtaskLifecycleToolkit` calls `TaskManagementService` directly
and can bypass the worker-context facade. PR 14 should remove that bypass and
leave `SubtaskLifecycleToolkit` as a worker-authoring object-bound surface.

Mutation semantics are also split. `refine_task` updates
`run_graph_nodes.description` but does not update the embedded `task_json`;
execution rehydrates the authored `Task` from `task_json`, so
refine-then-restart can rerun the old description. `spawn_task` accepts
arbitrary dependency UUIDs, and repository edge creation only validates
same-run/no-cycle, not descendant containment. `spawn_dynamic_task`,
`add_subtask`, and `plan_subtasks` also do not prevent duplicate slugs against
existing siblings. Finally, `_StepAwareTaskManagementService` memoizes
`plan_subtasks` under Inngest steps but not `spawn_dynamic_task`, so public
`WorkerContext.spawn_task()` can replay and duplicate nodes/events.

## Dashboard, Read Models, And Frontend Contracts

Reconciliation owner:
[PR 15](pr15-dashboard-event-contracts.md) owns generated event contracts,
live parser cleanup, graph/context event drift, workflow-started task-tree
alignment, and frontend field vocabulary. [PR 12](pr12-runtime-identity-and-dynamic-task-correctness.md)
must land first for final `task_id` naming in read models and event payloads.

The backend exposes snapshot/read-model DTOs from
`ergon_core.core.application.read_models`, live dashboard event contracts from
`ergon_core.core.infrastructure.dashboard.event_contracts`, and generated
frontend event schemas in `ergon-dashboard/src/generated/events`.

Duplication remains between read-model snapshot builders and event DTOs. The
run snapshot path builds task maps, execution maps, resource maps, evaluation
maps, context events, and sandbox summaries from persistence rows. Dashboard
event contracts separately model task status changes, evaluation updates,
resource publication, sandbox events, graph mutations, and context events.

The most urgent read-model issue is tied to schema identity: snapshot helpers
still key data by `node_id` while some code assumes final `task_id`. Until the
schema collapse is finished, dashboard and read-model code will continue to
carry bridge naming. If the final schema collapse proceeds, the generated
frontend contracts and REST DTOs need regeneration/checking in the same slice.

Live dashboard events have additional contract drift. PR 11 commit `a613875`
added compatibility parsing for backend graph mutation events emitted as
`{ mutation: GraphMutationRecordDto }` and backend context-part payloads. The
remaining duplication is that this compatibility lives in handwritten frontend
parsers rather than generated event contracts. Backend graph edge payloads use
`source_task_id` / `target_task_id`, while frontend graph mutation contracts and
reducers still normalize to deleted `source_node_id` / `target_node_id` names.
`workflow.started` task-tree contracts also drift: backend requires `status`
and `level` and sends resource ids, while handwritten frontend schemas omit
those fields, expect resource objects, and add non-backend fields.
