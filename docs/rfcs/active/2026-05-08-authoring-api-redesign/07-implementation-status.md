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
  no custom constructors on `Benchmark`, `Criterion`, `Rubric`, or `Worker`.
- `WorkerContext` now exposes the curated runtime facade for task spawning,
  graph inspection, mutation, and resource lookup, with framework-only service
  injection through private attributes and `SpawnedTaskHandle`.
- `CriterionContext` is pure data. Criteria receive the live task `Sandbox`
  directly, and the old `CriterionRuntime` indirection, `ScoreScale`,
  `Criterion.weight`, and `Criterion.score_spec` are gone.
- The old public/component registry path and component catalog implementation
  were deleted from `ergon_core`; builtins now expose explicit metadata maps
  instead of registering through `ergon_core.api.registry`.
- The runtime graph uses `(run_id, task_id)` identity as the persisted node key,
  and task execution/evaluation telemetry points at `task_id`.
- Definition worker/evaluator pool rows were deleted from persistence and the
  definition writer/read-model paths.
- The old sandbox manager base classes and job steps were deleted. Builtin
  sandbox definitions now derive from public `Sandbox` / direct E2B adapters,
  and worker/evaluator execution shares sandbox lifecycle through
  `SandboxLifecycleHub`.
- Old-shape registry/runtime/sandbox-manager tests were removed or updated, and
  unit verification is green for `ergon-core`, `ergon-builtins`, and
  `ergon-cli`.
- `RunGraphNode` no longer duplicates task definition metadata columns. The
  graph row keeps runtime state plus `task_json`; read models derive
  `description`, `task_slug`, `instance_key`, and assigned worker name from the
  object-bound task definition.
- Builtin benchmark ReAct workers now use the generic
  `ReActWorker(toolkit=...)` shape and serializable toolkit specs under
  `ergon_builtins.toolkits`. Benchmark-specific ReAct subclasses were removed.
- Architecture docs outside this RFC folder were updated for the accepted
  authoring API and sandbox lifecycle shape.

## Partially Landed

- None.

## Not Landed

- None.

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
- This PR now lands the object-bound authoring surface plus the runtime
  identity, WorkerContext, criterion-runtime, sandbox-manager, registry,
  denormalized graph column, ReAct/toolkit, and architecture documentation
  cleanups.
