# 07 — Implementation status

> Status of the `authoring-api-redesign` PR against the accepted target in
> this RFC folder. The earlier files remain the target design; this file is
> the honest delta between that target and what the current PR implements.

## Landed

- `Experiment` is now a public API type in `ergon_core.api.experiment` and is
  exported from `ergon_core.api`.
- `Task` is the single public task type. `TaskSpec` is gone, `Task` carries
  `worker`, `sandbox`, and `evaluators` directly, and runtime identity is held
  in `_task_id` behind the `task.task_id` property.
- Public authoring objects have explicit `to_definition()` and
  `from_definition()` entry points. The old implicit definition mixin is gone.
- Definition serialization infrastructure moved out of `ergon_core.api` into
  `ergon_core.core.domain.definitions`.
- Public API import cycles were removed without `model_rebuild()` or function
  local imports in the public API modules.
- Evaluator dispatch now uses task-bound evaluators by index/name rather than
  requiring a definition-level evaluator binding id at execution time.
- `RunGraphNodeView` exists and the worker execution path consumes
  `node.task` rather than reconstructing the task in the job body.
- `Sandbox` is a public base class with a runtime-backed proxy surface and
  `SandboxRuntime` protocol.
- `SandboxLifecycleHub` exists as the internal live-sandbox coordination point
  and uses shared process state for acquire/release/discard behavior.
- Public JSON-shaped metadata and definition annotations use the shared
  `JsonObject` alias rather than raw `dict[str, Any]`.
- Several public API models were simplified to normal Pydantic construction:
  no custom constructors on `Benchmark`, `Criterion`, `Rubric`, or `Worker`;
  `CriterionContext` uses `with_runtime(...)` for explicit runtime injection.

## Partially Landed

- The public API export surface is partially updated. `Experiment`, `Sandbox`,
  `SandboxRuntime`, `WeightedCriterion`, and the new exception types are
  exported, but `SpawnedTaskHandle` is not present because the planned
  `WorkerContext.spawn_task` surface did not land.
- Task identity cleanup is only partial. `task_id` is now the runtime identity
  used by key paths, but the old `node_id`/row-id model still exists in graph
  persistence and several runtime/read-model paths.
- Repository inflation is only partial. `worker_execute.py` uses
  `RunGraphNodeView.task`, but evaluation paths still call
  `Task.from_definition(node.task_json, ...)` directly.
- Object-bound task JSON exists on definition and run rows, but old denormalized
  columns such as `description`, `task_slug`, `instance_key`, and
  `assigned_worker_slug` still exist.
- Sandbox lifecycle behavior was adjusted enough for the current execution and
  evaluation flow, but the old sandbox manager system still exists and remains
  used by builtins/integration paths.
- Evaluator execution is object-bound at dispatch time, but definition
  worker/evaluator pool tables and several references to those rows still
  exist.
- Public API construction cleanup is partial. The core public base classes have
  been simplified, but several builtin worker classes still override
  `__init__`, pass `tools=[]`, and mutate `self.tools` during execution.

## Not Landed

- The full "two tables, one identity" schema rewrite did not land. The target
  composite `(run_id, task_id)` primary key for `run_graph_nodes` is not the
  current schema.
- `run_graph_nodes.id`, `definition_task_id`, `parent_node_id`,
  `assigned_worker_slug`, `description`, `task_slug`, and `instance_key` were
  not fully removed from the runtime graph model.
- `run_graph_edges`, task execution rows, task evaluation rows, Inngest payloads,
  and internal DTOs were not fully rewritten around `(run_id, task_id)`.
- `ComponentRegistry`, `ComponentCatalogEntry`, and `ComponentCatalogService`
  were not deleted. `ergon_core.api.registry` and the component catalog code
  still exist.
- The `ergon_builtins` registry files were not deleted or reduced to CLI-only
  aliases. `ergon_builtins/registry.py`, `registry_core.py`,
  `registry_data.py`, and `registry_local_models.py` still exist.
- `experiment_definition_workers` and `experiment_definition_evaluators` were
  not deleted. Several application/read-model paths still reference those rows.
- `BaseSandboxManager` and `DefaultSandboxManager` were not deleted. Concrete
  builtins still include manager-backed sandbox implementations.
- The planned `ergon_builtins.sandboxes` package did not land. Concrete sandbox
  kinds were not moved to `ergon_builtins/sandboxes/{lean,python,swebench,...}.py`.
- The planned `ergon_builtins.toolkits` package did not land. Existing benchmark
  toolkits were not moved into a shared toolkit package or converted into the
  final `ReActWorker(toolkit=...)` shape.
- The ReAct worker/toolkit collapse did not land. Benchmark-specific ReAct
  workers such as `MiniF2FReactWorker`, `SWEBenchReactWorker`, and
  `ResearchRubricsWorkflowCliReActWorker` still exist.
- `WorkerContext` did not receive the planned curated runtime facade:
  `spawn_task`, `cancel_task`, `refine_task`, `restart_task`, `subtasks`,
  `descendants`, `get_task`, `resources`, service `PrivateAttr` injection, or
  `SpawnedTaskHandle`.
- `CriterionContext` was not reduced to pure data. It still owns runtime proxy
  methods and uses `CriterionRuntime` via `with_runtime(...)`.
- `DefaultCriterionRuntime` and `CriterionRuntimeOptions` were not deleted.
- `Criterion.evaluate(...)` still takes `CriterionContext`; it does not yet take
  the task sandbox directly as planned in Phase 4.
- `Criterion.weight` and `Criterion.score_spec` were not removed. The
  `WeightedCriterion` wrapper exists, but criteria still carry aggregation
  fields.
- The planned test/file deletion cleanup did not land. Registry-oriented tests,
  sandbox-manager integration tests, and other old-shape tests remain because
  the underlying old systems remain.
- Architecture docs outside this RFC folder were not updated. The migration
  doc's "On acceptance" tasks for `docs/architecture/01_public_api.md` and
  `docs/architecture/cross_cutting/sandbox_lifecycle.md` remain outstanding.

## Intentional Post-Plan Changes

- The original RFC files were copied into this worktree unchanged, even where
  their status tables still describe phases as "Not started." This status file
  is the source of truth for implementation state in this PR.
- The `_type` discriminator remains in persisted definition JSON, but the public
  model API now exposes it through explicit `to_definition()` methods rather
  than an inherited mixin.
- Definition serialization lives under `core.domain.definitions` rather than in
  a private public-API module. This was a follow-up cleanup after review.
- Public API modules have an architecture guard against hidden import cycles and
  `model_rebuild()` usage.
- Public JSON object typing was tightened to use
  `ergon_core.core.shared.json_types.JsonObject` consistently in
  `ergon_core.api`.

## Reviewer Notes

- Treat `01-api-surface.md` through `06-decisions-log.md` as the target state,
  not a claim that the PR is complete.
- This PR currently lands the object-bound authoring surface and a subset of the
  runtime/materialization changes. It does not complete the persistence,
  WorkerContext, criterion-runtime, sandbox-manager, or builtin ReAct/toolkit
  migrations.
- Before merge, decide whether this PR should remain a partial implementation of
  the target, or whether the "Not landed" items above are blockers that must be
  implemented in this branch.
