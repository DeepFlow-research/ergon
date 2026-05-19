# Public API Lifecycle Audit Log

Date: 2026-05-18

Scope: read-only audit of the public authoring API object lifecycle across
`ergon_core`, `ergon_builtins`, and tests. The audit looked for duplicate write
paths, duplicate execution paths, dead transitional paths, and places where the
v2 public API object model is not actually the runtime source of truth.

This is an evidence log, not an implementation plan. Items marked "PR 11
covered" are already in or adjacent to the deletion-final-schema PR. Items
marked "uncovered" need either a PR 11 checklist entry or a separate cleanup/fix
PR.

## Executive Summary

The duplication suspicion is well formed. The most serious issues are not just
dead code; several v2 object-bound public API paths exist but are not yet the
canonical runtime/persistence path.

Highest-risk findings:

1. Object-bound evaluators can be authored and serialized but never fanned out,
   because execution still counts `task.evaluator_binding_keys`.
2. If evaluator fanout is fixed, evaluation persistence can still fail because
   object-bound inline evaluators do not create the legacy
   `ExperimentDefinitionEvaluator` rows that persistence currently requires.
3. Worker-side `Task.sandbox` may be config-only during execution; tools can bind
   to a non-live sandbox unless `worker_execute` inflates the task with the live
   `sandbox_id`.
4. `ReActWorker(toolkit=...)` does not rehydrate nested toolkit JSON, so
   persisted v2 workers can fail at runtime before tools bind.
5. Generic `Task[Payload]` snapshots can serialize an unimportable `_type`.
6. `WorkerContext` exposes public methods that appear out of sync with current
   management/inspection service APIs.
7. The registry/catalog slug path still coexists with `_type` import dispatch.
   Some uses are intentional transition bridges; others are validation/routing
   leftovers that need explicit keep/delete decisions.

## Findings By Object Family

### Criterion / Criteria

| Severity | Finding | Evidence | PR 11 covered? | Action |
| --- | --- | --- | --- | --- |
| High | Criterion serialization is incomplete: `Criterion` has no `_type` serializer/from-definition, and nested `Criterion` fields can lose subclass fields. | `ergon_core/api/criterion/criterion.py`; `ergon_core/api/rubric/rubric.py`; `ergon_builtins/benchmarks/gdpeval/rubric.py` | No | Add `Criterion` discriminator serialization/from-definition, or ban persisted criterion objects and require authored-data rebuild patterns. |
| Medium | Two `CriterionContext` models coexist with different meanings. | `ergon_core/api/criterion/context.py`; `ergon_core/core/application/evaluation/models.py`; `_legacy_evaluator_bridge.py` imports both | Mostly | Delete or rename the internal context with `CriterionExecutor`; keep public `api.criterion.CriterionContext` as the v2 runtime context. |
| Medium | Runtime injection has two paths: object-bound sandbox runtime and legacy synthesized runtime. | `core/application/jobs/evaluate_task_run.py`; `_legacy_evaluator_bridge.py` | Yes | Remove bridge branch with TaskSpec deletion; add a guard that object-bound tasks attach live sandbox runtime when `sandbox_id` is available. |
| Medium | Duplicate criterion execution paths remain. | `EvaluationService.evaluate`; `EvaluationService.evaluate_legacy`; `InngestCriterionExecutor` | Yes | Delete legacy executor path in PR 11. |
| Low | `SandboxFileCheckCriterion` bypasses public runtime DI and connects to E2B directly. | `ergon_builtins/evaluators/criteria/sandbox_file_check.py` | No | Delete if unused; otherwise rewrite through `CriterionContext`. |
| Low | TODOs around magic runtime injection and slug/name compatibility are real API ambiguity. | `api/criterion/context.py`; `api/criterion/results.py`; telemetry `evaluation_summary.py` | No | Normalize criterion identity on `slug`; make runtime injection explicit and singular. |

Clean checks:

- One canonical persisted criterion outcome shape was found:
  `RunTaskEvaluation.summary_json` containing `EvaluationSummary` /
  `CriterionOutcomeEntry`.
- No second criterion result table or duplicate outcome row writer was found.
- Active production evaluation loops criteria inline once per evaluator; the
  duplicate executor path is legacy-only and PR11-marked.

### Rubric / Evaluator

| Severity | Finding | Evidence | PR 11 covered? | Action |
| --- | --- | --- | --- | --- |
| Critical | Object-bound evaluators can be silently skipped. | `_fan_out_evaluators` in `core/application/jobs/execute_task.py` counts `view.task.evaluator_binding_keys`; MiniF2F/SWEBench tasks set `evaluators=(...)` without binding keys. | No | Make fanout count/select from `task.evaluators` for object-bound tasks; keep binding fallback only until PR 11 removes legacy. |
| Critical | Object-bound evaluation persistence still requires legacy evaluator rows. | `persist_benchmark` does not create `ExperimentDefinitionEvaluator` rows for inline `Task.evaluators`; `EvaluationService.persist_success/persist_failure` calls `lookup_evaluator_id`; FK is non-null. | Partially hinted | Either persist evaluator definition rows from inline evaluators, or make the FK nullable/remove lookup in the object-bound final state. |
| High | Plain `Rubric(criteria=...)` does not round-trip. | `Rubric.criteria` is `exclude=True`; `Evaluator.from_definition` just `model_validate`s dumped JSON. | Maybe related | Serialize criteria with `_type`, or make base `Rubric` non-persistable unless a subclass can rebuild criteria. |
| Medium | `EvaluationService.prepare_dispatch` is a dead v1 dispatch DTO path. | `core/application/evaluation/service.py`; callers only in tests | Not explicitly | Delete with evaluator bridge cleanup or add to PR11 ledger. |
| Low | Evaluation DTO mapping is duplicated. | `build_dashboard_evaluation_dto` and `read_models/run_snapshot.py` both map evaluation summary to dashboard DTOs. | No | Share one mapper from persisted `EvaluationSummary` to DTO. |

Clean checks:

- `Evaluator.model_dump` injects `_type`.
- `Task` serialization re-dumps nested evaluators with concrete subclass
  schemas.
- `evaluate_task_run` prefers object-bound `task.evaluators[index]` before
  legacy fallback.
- Only one canonical persisted evaluation row writer was found:
  `TelemetryRepository.create_task_evaluation`.

### Worker / WorkerContext / WorkerOutput

| Severity | Finding | Evidence | PR 11 covered? | Action |
| --- | --- | --- | --- | --- |
| High | `WorkerContext` public facade is partially broken or stale. | `api/worker/context.py` calls service methods whose current signatures/names do not line up in `tasks/inspection.py` and `tasks/management.py`. | No | Add thin adapters or align `WorkerContext` with command/session service APIs; test every public facade method. |
| High | `ReActWorker` cannot deserialize nested `toolkit` from JSON. | `ReActWorker.toolkit: Toolkit | None`; `Worker.from_definition` directly calls `WorkerCls.model_validate(worker_json)`. Diagnostic probe hit abstract `Toolkit` instantiation. | No | Add `Toolkit.from_definition`, a field validator, or pre-validation in `Worker.from_definition`; test concrete toolkit rehydration. |
| Medium | `_resource_repo` is injected into `WorkerContext` but unused and unexposed. | `api/worker/context.py`; `worker_execute.py`; `rg _resource_repo` finds only assignments. | No | Remove injection or add explicit worker resource methods with containment semantics. |
| Medium | `persist_outputs` is marked as PR11-dead, but it is still live sandbox resource publication. | `execute_task.py`; `persist_outputs.py`; architecture dead-path audit | Misclassified | Split ledger: delete legacy WorkerOutput resource path, but keep or rename resource publication unless worker execution absorbs it. |
| Low | Dead context-derived `WorkerOutput` helper remains. | `core/application/context/output_extraction.py`; no callers except architecture test. | No | Delete after confirming no external import contract. |
| Low | `PersistOutputsResult.output_resource_ids` and `FinalizeTaskExecutionCommand.output_resource_ids` are effectively unused. | `core/application/jobs/models.py`; `execute_task.py`; `tasks/execution.py` | Adjacent | Remove stale IDs or plumb actual resource IDs if attempt-level IDs are still desired. |

Clean checks:

- `Worker` serialization/from-definition is coherent for the top-level worker.
- `WorkerOutput` has one live authoritative persistence path:
  terminal stream item -> `WorkerOutputRepository.persist()` ->
  `run_task_executions.worker_output_json`.
- Stream contract enforces exactly one terminal `WorkerOutput`.
- Sandbox file/resource publication no longer writes fake worker-output
  resources.

### Benchmark / Task

| Severity | Finding | Evidence | PR 11 covered? | Action |
| --- | --- | --- | --- | --- |
| Critical | Object-bound inline evaluators are not launched or persisted. | MiniF2F/SWEBench create `Task(..., evaluators=(...))`; `persist_benchmark` and fanout still use `task.evaluator_binding_keys`. | No | Make object-bound tasks the source for evaluator rows and fanout. |
| High | Generic `Task[Payload]` snapshots serialize an unimportable `_type`. | `Task.model_serializer` uses `type(self).__qualname__`; MiniF2F/SWEBench instantiate `Task[Payload]`. Diagnostic probe produced an import failure for `Task[SWEBenchTaskPayload]`. | No | Serialize origin class for parametrized generics, or introduce concrete importable task subclasses. |
| High | Object-bound task worker/sandbox identity is duplicated, while execution prep still depends on legacy assignment rows. | `persist_benchmark` does not write `ExperimentDefinitionWorker` / assignment rows; graph init and prepare still derive worker metadata from those rows. | Partial | Decide whether definition worker/assignment rows are obsolete. If yes, remove read/prepare dependence; if no, populate from object-bound tasks. |
| High | ResearchRubrics and GDPEval still produce `TaskSpec`. | `ergon_builtins/benchmarks/researchrubrics/benchmark.py`; `ergon_builtins/benchmarks/gdpeval/benchmark.py` | Yes, sequencing risk | Block PR 11 deletion until PR 10b/10c migrate them to object-bound `Task`. |
| Medium | Two definition write and launch paths remain. | `persist_benchmark`; `_ExperimentDefinitionWriter.persist_definition`; `_ExperimentRunLauncher` fallback | Yes | Delete old writer/domain launch path once legacy launch is gone. |
| Medium | Two task snapshot fallback paths synthesize `TaskSpec` JSON. | `_definition_task_snapshot`; `_dynamic_task_snapshot` in graph repository | Yes | Delete both helpers and require object-bound `task_json`. |
| Medium | Dynamic subtask APIs are split. | `WorkerContext.spawn_task` writes object-bound `Task`; `SubtaskLifecycleToolkit` still creates slug/description/worker legacy nodes. | Partial | Convert tool APIs to accept/create `Task`, or retire legacy add/plan APIs. |

Clean checks:

- `Task` serialization tries to preserve nested worker/sandbox/evaluator
  subclass fields.
- `worker_execute` prefers `task.worker`; legacy worker lookup is isolated behind
  `_legacy_worker_bridge`.
- `evaluate_task_run` prefers `task.evaluators`; legacy evaluator lookup is
  isolated behind `_legacy_evaluator_bridge`.
- `start_workflow` is definition-first and does not go through
  `BenchmarkDefinitionRecord`.

### Sandbox / SandboxRuntime

| Severity | Finding | Evidence | PR 11 covered? | Action |
| --- | --- | --- | --- | --- |
| High | Worker-side v2 `Sandbox` is inflated config-only, so toolkit tools can bind to a dead sandbox. | `worker_execute` loads `graph_repo.node(...)` without `sandbox_id`; `ReActWorker` passes `task.sandbox` into tools; tools call `sandbox.run_command/write_file`. | Partial/new | In `worker_execute`, inflate task with `sandbox_id=payload.sandbox_id`, or make setup return/bind a real runtime consistently. |
| High | Acquisition still uses `BaseSandboxManager` registry, not author-defined `Sandbox.provision()`. | `sandbox_setup.py` resolves `registry.sandbox_managers` and calls `sandbox_manager.create`; public API exposes `Sandbox.provision()`. | Partial | Decide the acquisition owner. For v2, setup should load task snapshot and call `task.sandbox.provision()`, or mark manager path transitional. |
| High | Object-bound evaluation does not inject `CriterionRuntime`, while built-in criteria still call `context.ensure_sandbox/run_command/write_file`. | `evaluate_task_run` creates bare `CriterionContext`; runtime injection only happens in legacy branch; SWE/MiniF2F criteria use proxy methods. | New | Either inject runtime for object-bound contexts during transition, or migrate criteria to `context.task.sandbox` and remove proxies. |
| Medium | Authored `Sandbox.output_path` is ignored by output publishing. | Public field in `api/sandbox/sandbox.py`; publisher hard-codes `/workspace/final_output/`; `persist_outputs` never reads `task.sandbox`. | No | Thread `task.sandbox.output_path` into `SandboxResourcePublisher`, or remove the public field until honored. |
| Medium | Duplicate cleanup owners on `task/failed`. | `sandbox_cleanup.py` terminates on `task/failed`; `propagate_execution.py` also terminates on same event. | Partial | Keep termination in `sandbox_cleanup`; remove `_terminate_failed_task_sandbox` from propagation. |
| Medium | Stale run-level cleanup still tries sandbox termination via run summary. | `run_cleanup.py` reads `summary_json["sandbox_id"]` and calls `terminate_sandbox_by_id`. | Partial | Remove sandbox termination from run cleanup or constrain it to explicitly legacy records. |
| Low | Manager registry leaks creation locks. | `_creation_locks` allocated in sandbox manager; termination cleanup omits it. | No | Pop `_creation_locks[task_id]` in termination paths. |

Clean checks:

- `Task.from_definition(..., sandbox_id=...)` correctly attaches object-bound
  sandbox runtime when used.
- Eval-side object-bound detach is scoped to the local handle and runs in
  `finally`.
- Completed cleanup is gated after evaluator fanout.
- `SandboxResourcePublisher` is append-only and content-hash deduped.

### Toolkit / Tools

| Severity | Finding | Evidence | PR 11 covered? | Action |
| --- | --- | --- | --- | --- |
| High | `ReActWorker` nested toolkit rehydration fails. | Same as Worker finding; diagnostic rehydrate failed on abstract `Toolkit`. | No | Add toolkit discriminator rehydration and regression test. |
| High | SWE-Bench v2 editor allows path traversal outside `repo_root`. | `swebench_verified/_tools.py` builds `repo_root + "/" + path.lstrip("/")`; legacy duplicate in `_legacy_workers.py`. | Legacy duplicate yes; v2 tool no | Normalize POSIX paths and reject empty, absolute, and `..` segments. |
| Medium | Toolkit `max_tool_calls` config is exposed but unenforced. | MiniF2F/SWEBench toolkit classes define it; only round-trip tests reference it. | No | Enforce through wrappers/deps or remove/rename until real. |
| Medium | Multiple runtime-only `Toolkit` classes coexist with new Pydantic `Toolkit`. | Public `api/toolkit.py`; GDPEval/ResearchRubrics/Graph/Subtask runtime toolkit classes. | No | Rename runtime factories away from `Toolkit`, or migrate persisted benchmark-owned toolkits to the public shape. |
| Medium | Subtask lifecycle tools bypass `WorkerContext` containment facade. | TODO in `subtask_lifecycle_toolkit.py`; direct sessions/services mutate graph. | No | Rebuild around `WorkerContext` or add descendant validation before mutation/read. |
| Low | ResearchRubrics path traversal helper is duplicated. | `_workspace_path` appears in `researcher_worker.py` and `workflow_cli_react_worker.py`. | No | Move to shared ResearchRubrics path helper. |
| Low | Some SWE-Bench toolkit tests still target the old constructor/API. | `tests/integration/swebench_verified/test_toolkit.py` expects `SWEBenchToolkit(sandbox=..., workdir=...)` and `.get_tools()`. | No | Update to v2 `tools(sandbox, task)` or delete if superseded. |

Clean checks:

- SWE-Bench and MiniF2F author construction embeds
  `ReActWorker(toolkit=...)`.
- `ReActWorker.execute()` binds `toolkit.tools(task.sandbox, task)` before
  creating the pydantic-ai agent.
- `Toolkit.model_serializer` injects `_type`.

### Registry / Serialization / Component Discovery

This portion was audited locally after the six parallel object-family audits.

| Severity | Finding | Evidence | PR 11 covered? | Action |
| --- | --- | --- | --- | --- |
| High | There are two component resolution models: v2 `_type` import dispatch and slug/catalog lookup. | `_serialization.import_component`; `ComponentRegistry`; `ComponentCatalogService`; legacy bridges; launch/workflow validation still use registry. | Partially | Make `_type` import dispatch canonical for object-bound runtime; list every remaining slug lookup as keep/delete. |
| Medium | `ComponentCatalogService.resolve_benchmark` and `resolve_sandbox_manager` appear unused; `resolve_evaluator` is legacy-bridge-only. | `core/application/components/catalog.py`; `rg` results | Mostly not | Delete unused methods or ledger them under PR11 bridge cleanup. |
| Medium | `ComponentRegistry.publish` / persistent catalog writes are only tested and not used by runtime outside legacy lookup. | `api/registry.py`; registry tests; catalog publish tests | Partially | Decide whether persistent component catalog survives v2. If yes, document its runtime owner; if no, delete with ComponentRegistry. |
| Medium | Slug registry still validates dynamic subtasks and workflow service even when object-bound `Task` is the target shape. | `tasks/management.py`; `workflows/service.py` | No | Replace registry slug validation with object-bound worker validation, or explicitly keep slug-only tool contracts. |
| Low | `import_component_ref` and `_row_to_ref` are free helpers with TODOs to inline. | `core/application/components/catalog.py` | No | Inline into service or keep with a locality comment. |
| Low | `_serialization.import_component` returns `type[Any]` with a TODO. | `api/_serialization.py` | No | Type it as `type[BaseModel]` or add generic/cast helpers per component class. |

Clean checks:

- Builtins registration is explicit and eager; no decorator scanning.
- `_type` dispatch is centralized in `_serialization.import_component`.
- Runtime job bodies are mostly protected from direct `ComponentCatalogService`
  references by architecture tests; legacy bridges hold most violations.

## Cross-Cutting Duplicates And Dead Paths

### Uncovered or Misclassified

- `output_extraction.py` is dead context-derived worker output logic.
- `PersistOutputsResult.output_resource_ids` and
  `FinalizeTaskExecutionCommand.output_resource_ids` are stale.
- `WorkerContext._resource_repo` is injected but unused.
- `EvaluationService.prepare_dispatch` appears test-only and preserves old
  evaluator binding semantics.
- `ComponentCatalogService.resolve_benchmark` / `resolve_sandbox_manager` are
  unused; `resolve_evaluator` is bridge-only.
- `Sandbox.output_path` is public but ignored by output publishing.
- `SubtaskLifecycleToolkit` bypasses the newer `WorkerContext` containment
  facade and keeps a parallel mutation path.

### PR11-Covered Legacy Clusters Confirmed

- `TaskSpec`
- `WorkerSpec`
- `_legacy_worker_bridge`
- `_legacy_evaluator_bridge`
- `CriterionExecutor`
- `InngestCriterionExecutor`
- `EvaluateTaskRunRequest`
- `EvaluationService.evaluate_legacy`
- `_definition_task_snapshot`
- `_dynamic_task_snapshot`
- `_ExperimentDefinitionWriter`
- domain `Experiment`
- `terminate_sandbox_by_id`, with caveat that current cleanup callers must be
  reconciled before deletion

## Suggested Next Actions

1. Add a pre-PR11 blocking checklist item: object-bound evaluator fanout and
   persistence must be fixed before deleting the legacy evaluator bridge.
2. Add a pre-PR11 blocking checklist item: object-bound sandbox runtime must be
   live in worker execution before deleting manager/proxy transition paths.
3. Add a dedicated test for `Task.from_definition` round-tripping real MiniF2F
   and SWE-Bench `Task[Payload]` snapshots, including nested worker toolkit and
   evaluator objects.
4. Add a small cleanup PR for clearly dead/misclassified items:
   `output_extraction.py`, stale output resource IDs, unused
   `ComponentCatalogService` resolvers, and `prepare_dispatch` if tests can move.
5. Decide whether public `Toolkit`, runtime tool factories, and dynamic subtask
   tools should all remain named "Toolkit". The current naming hides two
   distinct lifecycles.
6. Decide whether the persistent component catalog survives v2. If it does,
   document its owner; if it does not, move the remaining slug/catalog users into
   PR11 deletion scope.

