# Dead Code Audit - 2026-04-25

This document records a static dead-code audit of `ergon_core/ergon_core/core`
plus nearby call sites in `ergon_builtins`, `ergon_cli`, and tests. It is meant
to be an executable cleanup plan, not just an inventory.

## Method

- Searched repo-wide call sites with `rg`.
- Used focused read-throughs of the runtime propagation, persistence, generation,
  evaluation, and RL paths.
- Installed and ran `vulture`:
  - `python -m vulture ergon_core/ergon_core/core --min-confidence 80`
  - `python -m vulture ergon_core/ergon_core tests ergon_builtins ergon_cli --min-confidence 60`
- Treated ORM models, Pydantic models, FastAPI route functions, registry-loaded
  components, and public package exports conservatively.

## Decision Legend

| Decision | Meaning |
| --- | --- |
| Delete | Remove once a focused test/lint pass confirms no hidden caller. |
| Port/use | Old code contains useful behavior that should be moved into the active path before deletion. |
| Keep | Useful internal API, currently imported, or deliberately kept as an extension point. |
| Deprecate | Appears unused in-repo but may be public or externally imported. Mark first, remove later. |
| Investigate | Static evidence is not enough; confirm dynamic loading, external usage, or product intent. |

## Executive Summary

The largest risk is `core/runtime/execution/propagation.py`, which mixes active
graph-native propagation with stale legacy propagation helpers. The active path
is now service-driven:

1. `task/completed` event calls `TaskPropagationService.propagate()`.
2. `TaskPropagationService.propagate()` marks the source node completed.
3. It calls `on_task_completed_or_failed()` to satisfy edges and activate ready nodes.
4. It calls `is_workflow_complete_v2()` / `is_workflow_failed_v2()` for terminal detection.

Failures follow the same active helper through `TaskPropagationService.propagate_failure()`.
The old helpers still in the file either walk `ExperimentDefinitionTaskDependency`
directly or implement stale semantics. They should be removed before they are
accidentally reused.

## Propagation Decision Table

| Area | File | Symbol / module | Current evidence | Decision | Why | Risk | Follow-up test/check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Runtime propagation | `core/runtime/execution/propagation.py` | `on_task_completed` | No repo-wide caller. Static dependency walker over `ExperimentDefinitionTaskDependency`. Replaced by `TaskPropagationService.propagate()` plus `on_task_completed_or_failed()`. Vulture flags it. | Delete | Legacy completion path. It writes source completion and dependency satisfaction in one helper, while the active service now separates node finalization from graph propagation. | Medium | Run propagation integration tests after removal. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `on_task_completed_by_node` | No repo-wide caller. Docstring says deprecated. Vulture flags it. | Delete | Superseded by `on_task_completed_or_failed()`. It also has stale behavior: it considers dependencies satisfied when source nodes are any terminal status, not only `COMPLETED`. | High if reused | Add/keep test coverage for fan-in failure remaining `BLOCKED`, then remove. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `mark_task_completed` | Only used by dead `on_task_completed`. | Delete | No active caller. Completion is now handled in `TaskPropagationService.propagate()` with `WorkflowGraphRepository.update_node_status()`. | Low | Search after deleting `on_task_completed`. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `mark_task_ready` | Used by `get_initial_ready_tasks` and dead `on_task_completed`. | Keep for now | Still used by workflow initialization for root tasks. Could be made private or moved near initialization later. | Low | Keep until `WorkflowInitializationService` is refactored. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `get_current_task_status` | Only used by dead `on_task_completed`. | Delete | Legacy helper needed only for static dependency walker. | Low | Search after deleting `on_task_completed`. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `is_workflow_complete` | No repo-wide caller. Vulture flags it. | Delete | Replaced by `is_workflow_complete_v2()`, which understands terminal statuses and failed/cancelled behavior. | Medium | Run terminal-state propagation tests. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `is_workflow_failed` | No repo-wide caller. Vulture flags it. | Delete | Replaced by `is_workflow_failed_v2()`, which handles `BLOCKED` as settled and waits for no pending/running work. | Medium | Run failure/blocking propagation tests. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `mark_task_running_by_node` | No repo-wide caller. Vulture flags it. Graph-native prepare writes node status directly through `WorkflowGraphRepository`. | Delete | Unused wrapper around active repository method. | Low | Search after removal. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `mark_task_completed_by_node` | No repo-wide caller. Vulture flags it. | Delete | Source completion is handled directly in `TaskPropagationService.propagate()`. | Low | Search after removal. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `mark_task_running` | Imported by `TaskExecutionService._prepare_definition()`. | Keep | Active static definition execution path still uses it. | Low | Do not remove in first cleanup. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `mark_task_failed` | Imported by `TaskExecutionService.finalize_failure()` for static tasks. | Keep | Active failure finalization path still uses it. | Low | Do not remove in first cleanup. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `mark_task_failed_by_node` | Imported by `TaskExecutionService.finalize_failure()` for dynamic graph nodes. | Keep | Active dynamic failure finalization path still uses it. | Low | Do not remove in first cleanup. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `get_initial_ready_tasks` | Imported by `WorkflowInitializationService.initialize()`. | Keep | Active workflow initialization path uses it to mark root tasks ready. | Medium | Consider moving into initialization service later, but not dead. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `on_task_completed_or_failed` | Imported by `TaskPropagationService`. Covered by propagation integration tests. | Keep | Active v2 propagation implementation. | High if changed | Treat as production-critical. |
| Runtime propagation | `core/runtime/execution/propagation.py` | `is_workflow_complete_v2`, `is_workflow_failed_v2` | Imported by `TaskPropagationService`. | Keep | Active terminal-state checks. | High if changed | Keep integration coverage around `BLOCKED`, `FAILED`, `CANCELLED`, and empty graph behavior. |

## Runtime Events and Tracing

| Area | File | Symbol / module | Current evidence | Decision | Why | Risk | Follow-up test/check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Evaluation events | `core/runtime/events/evaluation_events.py` | `TaskEvaluationEvent` | Only re-exported from `events/__init__.py`; no in-repo instantiation. Current evaluation dispatch uses `EvaluateTaskRunRequest` and raw `task/evaluate` trigger names. | Deprecate | Name is public-ish via `__all__`, but runtime does not use it. | Medium | Check package consumers before deleting. |
| Evaluation events | `core/runtime/events/evaluation_events.py` | `CriterionEvaluationEvent` | Only re-exported from `events/__init__.py`; no active criterion event function found. | Deprecate | Public-ish export and potentially planned feature, but currently orphaned. | Medium | Search docs/scripts before deleting. |
| Tracing | `core/runtime/tracing.py` | `action_context` | No repo-wide caller. | Delete | Unused context helper. Current code uses task/evaluation-specific context helpers and `emit_span()`. | Low | Search for `action_context` after removal. |
| Tracing | `core/runtime/tracing.py` | `TraceSink.add_event`, `TraceSink.child_context` | No active call sites; implemented on protocol/noop/otel sinks. | Keep | Reasonable extension points for tracing API, even if currently unused. | Low | Keep unless simplifying tracing API intentionally. |
| Delegation errors | `core/runtime/errors/delegation_errors.py` | `TaskNotPendingError` | Exported from `errors/__init__.py`, but no raises in repo. Comment says kept for backwards compatibility. | Deprecate | Public compatibility error, not active runtime behavior. | Low | Mark deprecated before deleting. |
| Graph errors | `core/runtime/errors/graph_errors.py` | `AnnotationNotFoundError` | Re-exported but not raised in repo. | Deprecate | Public-ish error class; possibly planned annotation API. | Low | Confirm no external consumers. |

## Persistence

| Area | File | Symbol / module | Current evidence | Decision | Why | Risk | Follow-up test/check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Definitions persistence | `core/persistence/definitions/repositories.py` | `DefinitionRepository` | No repo-wide import or instantiation. Reads happen through `queries`, `graph_repository`, services, or direct sessions. | Delete | Superseded read repository. Docstring points writes elsewhere. | Medium | Ensure no package-level import consumers. |
| Saved specs persistence | `core/persistence/saved_specs/repositories.py` | `SavedSpecsRepository`, `saved_specs_repository` | No repo-wide import or call site. | Delete | Repository wrapper appears never wired. | Medium | Keep ORM models; only remove repository if imports stay clean. |
| Saved specs persistence | `core/persistence/saved_specs/models.py` | Saved spec ORM models | Models are schema objects and may be loaded by Alembic metadata. | Keep | ORM models are not dead just because repository is unused. | High | Do not remove without migration/schema audit. |
| Telemetry persistence | `core/persistence/telemetry/repositories.py` | `TelemetryRepository.get_run`, `get_task_executions`, `get_resources`, `create_run`, `create_task_execution`, `complete_task_execution`, `create_resource` | `TelemetryRepository` is used by `EvaluationPersistenceService`, but only evaluation methods are called in repo. | Investigate | Could be intended as a facade, but active code does not use most of it. | Medium | Decide whether telemetry write/read facade is product API or stale. |
| Telemetry persistence | `core/persistence/telemetry/repositories.py` | `TelemetryRepository.create_task_evaluation`, `refresh_run_evaluation_summary`, `get_task_evaluations` | Used by evaluation persistence flow. | Keep | Active evaluation persistence. | Medium | Do not remove. |
| Telemetry persistence | `core/persistence/telemetry/repositories.py` | `GenerationTurnRepository.add_listener`, `persist_single`, `persist_turns`, `get_for_run`, `mark_execution_outcome` | `GenerationTurnRepository` is instantiated by `api/worker.py`, but only `get_for_execution` appears called. | Investigate | This may be a wiring gap: reads are active, but writes/listeners are not. Do not delete until generation-turn persistence ownership is clear. | High | Trace worker execution and turn persistence before deciding. |
| Telemetry persistence | `core/persistence/telemetry/repositories.py` | `GenerationTurnRepository.get_for_execution` | Used by `api/worker.py`. | Keep | Active read path. | Medium | Do not remove. |
| Query namespace | `core/persistence/queries.py` | `queries.evaluations` / `EvaluationsQueries` | No repo-wide `queries.evaluations` usage. | Investigate | `queries` is a broad namespace API; low usage may be intentional. | Medium | Determine whether `queries` is public API before pruning. |
| Query namespace | `core/persistence/queries.py` | `ResourcesQueries.list_latest_for_execution` | No repo-wide caller found. | Investigate | May be useful API despite no active caller. | Low | Keep unless pruning query namespace. |
| Shared typing | `core/persistence/shared/types.py` | `BenchmarkSlug`, `ExecutionId` | No repo-wide imports beyond definition. | Investigate | Tiny type aliases. If this file is intended to define canonical domain IDs, keeping is cheap; if the goal is a strict type surface, delete them. | Low | Prefer keep unless cleaning type surface aggressively. |

## Generation, Judges, and Evaluation Helpers

| Area | File | Symbol / module | Current evidence | Decision | Why | Risk | Follow-up test/check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LLM judge provider | `core/providers/judges/llm_judge.py` | Entire module, `LLMJudgeResponse`, `call_llm_judge` | No imports from `core.providers.judges`. Criterion runtime has its own `call_llm_judge()` implementation. | Investigate | If a shared judge wrapper is desired, port the active criterion-runtime implementation to this module and call it. Otherwise delete stale duplicate. | Medium | Decide whether shared judge utility is a desired architecture. |
| VLLM generation | `core/providers/generation/vllm_model.py` | Entire module, `resolve_model_target`, `ResolvedModel`, `_discover_vllm_model_name`, `VLLMDiscoveryError` | Production imports use `core/providers/generation/model_resolution.py` and builtins vLLM backend. Only tests reference this stale module. | Delete | Duplicate model-resolution path. Keeping two implementations risks divergent behavior. | Medium | Remove/replace stale tests that target this module. |
| PydanticAI format parsing | `core/providers/generation/pydantic_ai_format.py` | `extract_text`, `extract_tool_calls` | No repo-wide callers. `extract_logprobs` is used by builtins `react_worker`. | Investigate | The module claims to be the single source of truth; either move telemetry parsing here or trim unused functions. | Medium | Compare with `_extract_response_text` / `_extract_tool_calls_json` in telemetry repository. |
| PydanticAI format parsing | `core/providers/generation/pydantic_ai_format.py` | `extract_logprobs` | Imported by `ergon_builtins/workers/baselines/react_worker.py`. | Keep | Active behavior. | Low | None. |
| Evaluation schema re-exports | `core/runtime/evaluation/evaluation_schemas.py` | `LLMJudgeResponse` | Listed in `__all__`, no imports from this file found. There is another `LLMJudgeResponse` in stale judge provider. | Deprecate | Public-ish schema export, likely redundant. | Low | Confirm evaluator API expectations. |
| Evaluation schema re-exports | `core/runtime/evaluation/evaluation_schemas.py` | `CommandResult`, `SandboxResult` re-exports | Imported into this module and re-exported, but no callers import these names from this module. | Deprecate | Barrel/re-export noise. | Low | Confirm no external import path. |

## RL and Rollout

| Area | File | Symbol / module | Current evidence | Decision | Why | Risk | Follow-up test/check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RL polling | `core/rl/polling.py` | `PollTimeoutError`, `poll_until_all_complete` | No repo-wide caller. Docstring says used by TRL adapter, but adapter polls through `RolloutService`. | Delete | Stale helper. | Low | Search after deletion. |
| TRL adapter | `core/rl/trl_adapter.py` | `make_ergon_rollout_func` | No repo-wide caller. Module is explicitly marked deprecated in favor of HTTP adapter. Vulture flags unused `trainer` parameter. | Delete | Sunset path. `ergon_infra/adapters/trl_http.py` is the current replacement. | Medium | Confirm no external in-process TRL users. |
| RL package exports | `core/rl/__init__.py` | `VLLM_LOGPROB_SETTINGS` | Alias to `LOGPROB_SETTINGS`; no repo-wide caller. | Deprecate | Compatibility alias only. | Low | Remove after one deprecation cycle if public API matters. |

## Miscellaneous Core

| Area | File | Symbol / module | Current evidence | Decision | Why | Risk | Follow-up test/check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Core utils | `core/utils.py` | `get_mime_type` | No repo-wide caller. | Delete | Small unused helper. | Low | Search after deletion. |
| OpenRouter budget | `core/providers/generation/openrouter_budget.py` | `OpenRouterBudget` | Mostly referenced from tests/fixtures/benchmarks rather than active production modules. | Keep | Useful for real-LLM test budget gating. Not dead in the test harness context. | Low | None. |
| Dashboard emitter | `core/dashboard/emitter.py` | `_RunContextEvent` import | Vulture flags unused import. | Delete | Straight unused import cleanup. | Low | Run lint/type check. |
| RL extraction | `core/rl/extraction.py` | `add_special_tokens` local/argument | Vulture flags unused variable. | Investigate | Could be a signature/API compatibility argument. | Low | Check tokenizer API and tests before removing. |

## Recommended Cleanup Order

1. Propagation cleanup first:
   - Delete only the stale helpers listed as `Delete`.
   - Keep active helpers used by `TaskExecutionService`, `WorkflowInitializationService`, and `TaskPropagationService`.
   - Run propagation integration tests.

2. Low-risk stale modules:
   - `core/utils.get_mime_type`
   - `core/rl/polling.py`
   - dashboard unused import

3. Duplicate implementation cleanup:
   - Decide whether to delete or centralize `core/providers/judges/llm_judge.py`.
   - Delete stale `core/providers/generation/vllm_model.py` and update/remove tests that target it.

4. Persistence cleanup:
   - Remove unused repository wrappers only after confirming no external package imports.
   - Do not remove ORM models as part of repository cleanup.

5. Public-ish exports:
   - Deprecate event/schema/error aliases before deletion if package compatibility matters.

## Propagation-Specific Conclusion

The current active propagation logic is not missing from the old helpers; it is
more complete than the old helpers. The old helpers are stale because they either
operate on static definition dependencies or use pre-`BLOCKED` terminal semantics.
The highest-value cleanup is to remove the stale helpers from `propagation.py`
so future work cannot accidentally call them.

