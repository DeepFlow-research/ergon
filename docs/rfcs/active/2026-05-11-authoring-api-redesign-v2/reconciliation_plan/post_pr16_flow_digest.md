# Post-PR16 Core Flow Digest

Date: 2026-05-18

Branch audited: `codex/v2-pr-11-deletion-final-schema`

Head used for this digest: `a6138755f3f1b4794b0c640c377c9e87dc42c6cf`

## Purpose

This document is the reader's-digest version of the reconciliation audit. It
does not list every debt item. Instead, it describes the core flows as they
should read after PRs 12-16 land, so reviewers can ask: "if this is where the
stack is taking us, does the final system make sense?"

Each section has:

- the main entry point;
- the expected step-by-step call path;
- what should be gone by the end of PR 16;
- the review question that matters most.

## 1. Authoring A Benchmark Definition

Entry point: benchmark author code, usually a concrete `Benchmark` subclass.

Post-PR16 flow:

1. The author creates a benchmark whose `build_instances()` returns concrete
   `Task` objects.
2. Each `Task` directly contains its runtime objects: `worker`, `sandbox`, and
   zero or more `evaluators`.
3. Each nested public object serializes itself with a `_type` discriminator:
   `module:qualname`.
4. The definition persistence layer calls `build_instances()` once for the
   persisted graph.
5. `persist_benchmark()` writes immutable definition metadata and stores the
   complete object-bound `task_json` snapshot for each task.
6. Normalized definition rows remain only where they are deliberately
   load-bearing, such as evaluator metadata/FK lookup or read-model/query
   ergonomics.

What should be gone:

- repeated `build_instances()` calls that can validate one graph and persist
  another;
- registry/spec authoring as a runtime requirement;
- `saved_specs`;
- `ExperimentRecord`;
- `_prepare_definition`;
- public examples that imply workers/evaluators are bound by slug at runtime.

Review question: is `task_json` obviously the canonical authored task, and are
all remaining normalized definition rows justified by a current read/write need?

## 2. Persisting And Launching A Run

Entry point: `persist_benchmark()` followed by `launch_run()`.

Post-PR16 flow:

1. `persist_benchmark()` stores the immutable definition graph.
2. `launch_run()` creates a `RunRecord` with unambiguous provenance back to the
   definition id/model chosen as final.
3. `WorkflowGraphRepository.initialize_from_definition()` copies definition
   tasks into run-tier graph rows.
4. Each run graph node receives the canonical runtime task identity,
   consistently named `task_id`.
5. Run graph rows carry their object-bound `task_json` snapshot.
6. Initial ready tasks are computed from run-tier graph edges only.
7. Runtime after launch reads from run-tier graph state, not from definition
   reconstruction paths.

What should be gone:

- mixed `RunGraphNode.id`/`task_id` public identity vocabulary;
- payloads that use `task_id=None` and smuggle the real id through `node_id`;
- inconsistent `RunRecord.experiment_id` vs definition id provenance;
- code that references `RunGraphNode.task_id` before the model actually has the
  final field;
- schema reset drift between SQLModel models and Alembic.

Review question: can a reader follow one identity from authored task, to run
graph node, to execution/evaluation/read-model/dashboard without learning a
second public name?

## 3. Executing A Task

Entry point: `task/ready` event handled by `execute_task`.

Post-PR16 flow:

1. A `TaskReadyEvent` arrives with `run_id`, `definition_id`, and canonical
   `task_id`.
2. `execute_task` calls `TaskExecutionService.prepare()` and creates a
   `RunTaskExecution`.
3. `execute_task` invokes `sandbox_setup`.
4. `sandbox_setup` loads the run-tier task through
   `WorkflowGraphRepository.node(run_id, task_id)` and calls
   `task.sandbox.provision()`.
5. `execute_task` invokes `worker_execute` with `task_id`, `execution_id`, and
   `sandbox_id`.
6. `worker_execute` reloads the same run-tier task with the live `sandbox_id`.
7. `worker_execute` validates and runs `task.worker`.
8. Context chunks are persisted as they stream.
9. Exactly one terminal `WorkerOutput` is persisted.
10. `execute_task` invokes `persist_outputs`.
11. `execute_task` fans out evaluators, waits for them, then emits
    `task/completed` or `task/failed`.

What should be gone:

- registry lookup to choose the runtime worker for a persisted task;
- `WorkerExecuteRequest.task_id=None`;
- public `node_id` dependence in job payloads, traces, and worker context;
- worker execution paths that rebuild a task from definition rows;
- output extraction from context events as the main worker-output path.

Review question: does task execution look like "load the object-bound task and
run its worker", or are there still hidden fallback paths deciding what worker
to run?

## 4. Worker Context And Worker-Authored Actions

Entry point: `WorkerContext._for_job()` inside `worker_execute`.

Post-PR16 flow:

1. `worker_execute` constructs `WorkerContext` with a non-null `task_id`.
2. Worker code uses the public facade: `spawn_task`, `subtasks`,
   `descendants`, `get_task`, `cancel_task`, `refine_task`, `restart_task`,
   `resources`.
3. Every target-taking facade method enforces containment: a worker can act on
   itself or descendants, not arbitrary tasks in the run.
4. `WorkerContext.spawn_task(Task(...))` creates object-bound dynamic children.
5. `spawn_task()` is wrapped in Inngest step memoization so replay does not
   duplicate graph rows or `task/ready` events.
6. Slug/registry dynamic authoring workflows are gone; worker-authored actions
   use concrete `Task` objects.

What should be gone:

- worker-authored code reading `context.node_id`;
- public facade methods returning empty state because `task_id` is null;
- slug/registry synthesis in worker-authored dynamic task creation;
- duplicate sibling slugs;
- dependencies on non-descendant task ids;
- `refine_task()` updating graph description without updating embedded
  `task_json`.

Review question: can a worker author understand the facade without knowing
about run graph internals?

## 5. Dynamic Subtask Propagation

Entry point: `WorkerContext.spawn_task()` and object-bound subtask tools.

Post-PR16 flow:

1. A worker spawns a child by passing a concrete `Task` object.
2. `TaskManagementService.spawn_dynamic_task()` writes a run-tier graph node
   with object-bound `task_json`.
3. Dependencies are checked for same-run, acyclic, and containment-valid.
4. If the new child has no unsatisfied dependencies, a `task/ready` event is
   emitted with canonical `task_id`.
5. If the child depends on another task, graph propagation readies it after all
   dependencies complete.
6. Parent workers do not synchronously wait inside `worker_execute` for sibling
   Inngest jobs to finish.
7. PR 11's smoke behavior is preserved: parent/recursive smoke workers plan and
   return; later graph/e2e assertions observe child completion.

What should be gone:

- dynamic `task/ready` events with `task_id=None`;
- child execution that only works because smoke fixtures bypass the facade and
  use `context.node_id`;
- un-memoized worker-authored spawn replay;
- slug/registry planning exposed as a worker authoring model.

Review question: if a dynamic child is spawned during worker execution, is its
lifecycle graph-native and replay-safe from the first write?

## 6. Evaluating A Task

Entry point: evaluator fanout from `execute_task`.

Post-PR16 flow:

1. After worker output and output resources are persisted, `execute_task`
   reloads the run-tier task.
2. Evaluator count is `len(task.evaluators)`.
3. For each evaluator index, `execute_task` invokes `evaluate_task_run` with an
   id-only payload: `run_id`, `task_id`, `execution_id`, `evaluator_index`.
4. `evaluate_task_run` reloads the run-tier task with the live sandbox id from
   the execution row.
5. `evaluate_task_run` selects `task.evaluators[evaluator_index]`.
6. `EvaluationService.evaluate()` runs the evaluator and criteria.
7. The evaluator returns criterion outcomes and task-level summary.
8. Results persist to `RunTaskEvaluation.summary_json` and any retained
   evaluator metadata/FK fields.
9. Dashboard/read models emit evaluation updates from persisted results.

What should be gone:

- `Task.evaluator_binding_keys`;
- fallback fanout based on binding keys;
- `EvaluationService.prepare_dispatch()` as a runtime dispatch path;
- v1 dispatch DTOs used only by tests;
- `CriterionExecutor`/Inngest criterion executor references.

Review question: is there exactly one runtime answer to "which evaluator runs":
the evaluator object inside the task snapshot at `evaluator_index`?

## 7. Sandbox Lifecycle

Entry point: `sandbox_setup`, `worker_execute`, `evaluate_task_run`, terminal
task events.

Post-PR16 flow:

1. `sandbox_setup` loads the run-tier task and calls `task.sandbox.provision()`.
2. The sandbox object attaches its live runtime and returns `sandbox_id`.
3. `worker_execute` reloads the task with `sandbox_id`, so worker code sees a
   live `task.sandbox`.
4. `evaluate_task_run` reloads the same task with `sandbox_id`, so criteria can
   use the same sandbox while evaluation runs.
5. Evaluators detach local runtime handles without terminating the external
   sandbox.
6. `execute_task` emits a terminal task event after worker, output persistence,
   and evaluators are done.
7. `sandbox_cleanup` is the single owner for terminal sandbox release.
8. Observability events/WAL rows are emitted by that same lifecycle owner.

What should be gone:

- failure propagation terminating sandboxes directly;
- double cleanup on failed tasks;
- comments promising cancelled-task sandbox release if the code does not do it;
- manager-owned observability assumptions that direct `Sandbox.provision()`
  bypasses;
- unused `SandboxSetupRequest` fields if they are not part of final
  provisioning.

Review question: is there exactly one owner for external sandbox termination,
and does observability follow that owner?

## 8. Registry, Serialization, And Discovery

Entry point: `_type` serialization for runtime and explicit package/module
discovery.

Post-PR16 flow:

1. Runtime task snapshots carry `_type` for `Task`, `Worker`, `Sandbox`,
   `Evaluator`, and `Criterion`.
2. Rehydration imports the concrete class from `_type`.
3. `_type` is stripped before Pydantic validates constructor payloads.
4. Persisted runtime execution never needs registry lookup.
5. CLI discovery, onboarding, tests, and smoke fixtures use explicit imports,
   dependency declarations, package entrypoints, or fixture-local factories.
6. Architecture guards prevent registry use from creeping back into the tree.
7. `Toolkit` has a stable builtins/baselines import path if it remains part of
   the v2 ReAct authoring story.

What should be gone:

- builtins static registry files;
- persistent component catalog;
- `ergon_core.api.registry` as a recommended authoring path;
- `ergon_core.api.registry` as an importable registry;
- runtime worker/evaluator selection by registry slug;
- stale docs pointing at deleted registry files.
- `Toolkit` exported from `ergon_core`.

Review question: can persisted tasks run in a fresh process using only importable
`_type` snapshots and installed packages?

## 9. Dashboard Events And Read Models

Entry point: REST snapshot reads and live dashboard events.

Post-PR16 flow:

1. Backend read models build run snapshots from persistence rows.
2. Backend live event contracts model task status, graph mutation, context,
   resource, sandbox, evaluation, communication, workflow started/completed, and
   cohort updates.
3. Generated frontend contracts include every live backend event shape.
4. Frontend live parsers consume generated/canonical event shapes.
5. Graph mutation payloads use final `task_id` vocabulary, including
   `source_task_id` and `target_task_id`.
6. Context event live parsing and REST hydration share the same canonical
   conversion path.
7. Reducers update run state from live events without stale compatibility
   field names.

What should be gone:

- handwritten-only event shapes for graph/context events;
- frontend normalization from `source_task_id` into `source_node_id`;
- live parsers that accept backend reality only through ad hoc shims;
- workflow-started task-tree drift around `status`, `level`, and resource ids;
- test harness DTOs using deleted `parent_node_id` names.

Review question: when backend emits a live event, is there a generated frontend
contract and one obvious parser path for it?

## 10. Task Lifecycle Operations

Entry point: `TaskManagementService` and object-bound worker/tool wrappers.

Post-PR16 flow:

1. Lifecycle operations are owned by `TaskManagementService`.
2. Restart, abandon/cancel, refine, dependency invalidation, and descendant
   traversal go through one semantics layer.
3. Terminal guards prevent illegal mutation of completed/failed tasks unless an
   explicit restart flow reopens them.
4. Cascade invalidation updates downstream graph status and edges.
5. Worker-facing operations enforce containment through `WorkerContext`.
6. CLI/tool operations use the same canonical lifecycle service rather than
   duplicate weaker semantics.

What should be gone:

- weaker duplicate `WorkflowService.restart_task()` and
  `WorkflowService.abandon_task()` paths;
- lifecycle behavior that bypasses containment;
- graph description updates that leave embedded `task_json` stale;
- repository companion-file ledger exceptions.

Review question: if a task changes lifecycle state, is there one service where
the invariants live?

## Final Post-PR16 Picture

If PRs 12-16 land as planned, the core should read like this:

1. Authors create object-bound tasks.
2. Persistence stores immutable definitions plus complete task snapshots.
3. Launch copies tasks into a run graph with one public runtime identity:
   `task_id`.
4. Runtime jobs load run-tier tasks and execute their embedded objects.
5. Workers interact through `WorkerContext`, not graph internals.
6. Dynamic children are graph-native and replay-safe.
7. Evaluators run from `task.evaluators[index]`, not binding registries.
8. Sandbox lifecycle has one cleanup owner.
9. The core registry and persistent component catalog are gone.
10. Dashboard live and snapshot contracts use generated/canonical task-id
    shapes.
11. PR 16 deletes the old scaffolding, stale comments, duplicate lifecycle
    paths, and all remaining ledgers.

The desired feeling after PR 16 is not "there is no complexity." The desired
feeling is "there is one place to look for each kind of complexity."
