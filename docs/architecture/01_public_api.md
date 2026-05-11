# 01 — public api

## purpose

This layer defines the types a contributor touches to add a benchmark, worker, evaluator, criterion, sandbox, or experiment to Ergon. Everything below this layer (Inngest functions, DB writes, provider clients, resource publishing) is implementation detail hidden behind the authoring API.

## core abstractions

All public authoring objects live under `ergon_core.api` and serialize through explicit `to_definition()` / `from_definition()` entry points. Persisted definitions use core-owned `_type` envelopes in `ergon_core.core.domain.definitions`; the public API no longer owns a hidden definition mixin or calls `model_rebuild()`.

- **`Benchmark`** — abstract base that produces object-bound `Task` instances via `build_instances()`.
- **`Task`** — the single public task type. It carries `task_slug`, `instance_key`, `description`, `task_payload`, `worker`, `sandbox`, `evaluators`, `parent_task_slug`, and `dependency_task_slugs`. Runtime identity is attached as private `_task_id` and exposed through `task.task_id` after materialization.
- **`Worker`** — abstract base with `execute(task, *, context, sandbox)`. Worker constructors use normal Pydantic construction; runtime-only services live in `WorkerContext` private attrs, not in public fields.
- **`WorkerContext`** — curated runtime facade for spawning tasks, inspecting/mutating the task graph, and listing/reading resources. It delegates to internal services and returns stable public handles such as `SpawnedTaskHandle`.
- **`Sandbox`** — public base class for benchmark sandbox definitions. Runtime-backed operations are delegated through a `SandboxRuntime` protocol. Builtins that use E2B now derive from public sandbox definitions rather than legacy manager classes.
- **`Evaluator` / `Rubric`** — task-bound evaluators. Dispatch resolves evaluators from the task object by index/name; definition-level evaluator pool rows are gone.
- **`Criterion`** — scores one aspect of a completed task. `CriterionContext` is pure data, and `Criterion.evaluate()` receives the live task `Sandbox` directly. The old criterion runtime protocol, `ScoreScale`, criterion `weight`, and `score_spec` fields are gone.
- **`Experiment`** — public binding of benchmark, worker/evaluator objects, metadata, and launch behavior. It persists object-bound tasks directly rather than separate worker/evaluator pools.

## control flow

```
Benchmark.build_instances()
    -> Task(worker=..., sandbox=..., evaluators=...)
    -> Experiment.persist() writes definition task JSON
    -> run graph materializes RunGraphNode(run_id, task_id, task_json, status, parent_task_id)
    -> worker_execute acquires Sandbox via SandboxLifecycleHub
    -> Worker.execute(task, context, sandbox) yields context parts + WorkerOutput
    -> evaluator dispatch calls task-bound evaluators and criteria with the same Sandbox
    -> telemetry and resources are keyed by task_id
```

## invariants

- **`task_id` is canonical runtime identity.** Run graph nodes use `(run_id, task_id)` as their key, and task execution/evaluation telemetry points at `task_id`. Do not reintroduce separate `node_id` or `definition_task_id` identities.
- **Task metadata lives in `task_json`.** `RunGraphNode` stores runtime state only: `run_id`, `task_id`, `task_json`, `status`, `parent_task_id`, `level`, and timestamps. Read models derive `task_slug`, `instance_key`, `description`, and assigned worker name from the task definition.
- **Workers see the public task and sandbox.** Runtime jobs should consume `RunGraphNodeView.task`, not rebuild task details from duplicated columns.
- **Criteria are sandbox-aware but context-light.** Keep `CriterionContext` as data; pass capabilities explicitly through the `sandbox` argument.
- **Builtins are explicit maps, not a core registry.** `ergon_builtins` exposes benchmark/evaluator/worker maps for CLI composition. `ergon_core.api.registry` and the component catalog are deleted.
- **ReAct workers are toolkit-configured.** Builtin benchmark slugs construct the generic `ReActWorker(toolkit=..., system_prompt=..., max_iterations=...)`; benchmark-specific ReAct subclasses should not be added.
