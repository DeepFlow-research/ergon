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

## Estimated Size Impact

If every row currently marked `Delete` is removed, the cleanup removes about:

- 6 entire modules.
- 38 audit-listed delete items.
- 13 top-level classes.
- 17 top-level functions.
- 45 class methods.
- 2 unused type aliases.
- 1,079 physical Python lines, or 941 nonblank Python lines.

Against `ergon_core/ergon_core/core`, that is roughly 5.7% of physical Python
lines and 5.9% of nonblank Python lines (`18,919` physical lines, `15,883`
nonblank lines total). This estimate counts the deleted symbols/modules
themselves, not the small import/export/test cleanup that will come with them.

Propagation alone accounts for 8 top-level functions and about 221 physical
lines. That is the most important qualitative reduction because it removes stale
alternative control flow, not just unused helpers.

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
| Evaluation events | `core/runtime/events/evaluation_events.py` | `TaskEvaluationEvent` | Only re-exported from `events/__init__.py`; no in-repo instantiation. Current evaluation dispatch uses `EvaluateTaskRunRequest` and raw `task/evaluate` trigger names. | Delete | Runtime does not use it, and external compatibility is not a concern for this repo. | Medium | Remove export and run tests/import checks. |
| Evaluation events | `core/runtime/events/evaluation_events.py` | `CriterionEvaluationEvent` | Only re-exported from `events/__init__.py`; no active criterion event function found. | Delete | Orphaned planned feature/event contract, and external compatibility is not a concern for this repo. | Medium | Remove export and run tests/import checks. |
| Tracing | `core/runtime/tracing.py` | `action_context` | No repo-wide caller. | Delete | Unused context helper. Current code uses task/evaluation-specific context helpers and `emit_span()`. | Low | Search for `action_context` after removal. |
| Tracing | `core/runtime/tracing.py` | `TraceSink.add_event`, `TraceSink.child_context` | No active call sites; implemented on protocol/noop/otel sinks. | Keep | Reasonable extension points for tracing API, even if currently unused. | Low | Keep unless simplifying tracing API intentionally. |
| Delegation errors | `core/runtime/errors/delegation_errors.py` | `TaskNotPendingError` | Exported from `errors/__init__.py`, but no raises in repo. Comment says kept for backwards compatibility. | Delete | Backwards compatibility is not needed; no active runtime behavior depends on it. | Low | Remove export and run import checks. |
| Graph errors | `core/runtime/errors/graph_errors.py` | `AnnotationNotFoundError` | Re-exported but not raised in repo. | Delete | No active graph path raises it, and external compatibility is not a concern. | Low | Remove export and run import checks. |

## Persistence

| Area | File | Symbol / module | Current evidence | Decision | Why | Risk | Follow-up test/check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Definitions persistence | `core/persistence/definitions/repositories.py` | `DefinitionRepository` | No repo-wide import or instantiation. Reads happen through `queries`, `graph_repository`, services, or direct sessions. | Delete | Superseded read repository. Docstring points writes elsewhere. | Medium | Ensure no package-level import consumers. |
| Saved specs persistence | `core/persistence/saved_specs/repositories.py` | `SavedSpecsRepository`, `saved_specs_repository` | No repo-wide import or call site. | Delete | Repository wrapper appears never wired. | Medium | Keep ORM models; only remove repository if imports stay clean. |
| Saved specs persistence | `core/persistence/saved_specs/models.py` | Saved spec ORM models | Models are schema objects and may be loaded by Alembic metadata. | Keep | ORM models are not dead just because repository is unused. | High | Do not remove without migration/schema audit. |
| Telemetry persistence | `core/persistence/telemetry/repositories.py` | `TelemetryRepository.get_run`, `get_task_executions`, `get_resources`, `create_run`, `create_task_execution`, `complete_task_execution`, `create_resource` | `TelemetryRepository` is used by `EvaluationPersistenceService`, but only evaluation methods are called in repo. Run/task/resource lifecycles are handled through services or direct ORM queries. | Delete | Stale facade methods. The active evaluation methods should stay, but these seven methods are not wired. | Medium | Delete the seven methods only; keep `create_task_evaluation`, `get_task_evaluations`, and `refresh_run_evaluation_summary`. |
| Telemetry persistence | `core/persistence/telemetry/repositories.py` | `TelemetryRepository.create_task_evaluation`, `refresh_run_evaluation_summary`, `get_task_evaluations` | Used by evaluation persistence flow. | Keep | Active evaluation persistence. | Medium | Do not remove. |
| Telemetry persistence | `core/persistence/telemetry/repositories.py` | `GenerationTurnRepository.persist_single` | Current worker execution persists `RunContextEvent`, not `RunGenerationTurn`. Earlier investigation treated this as a missing write, but the frontend/backend action-log direction is context events. | Delete | Do not revive the old generation-turn write path. Finish migrating readers/UI to `RunContextEvent`, then delete this stale writer. | High | Add tests proving yielded turns render from context events in both live updates and persisted snapshots. |
| Telemetry persistence | `core/persistence/telemetry/repositories.py` | `GenerationTurnRepository.add_listener`, `persist_turns`, `get_for_execution`, `get_for_run`, `mark_execution_outcome` | No generation-turn writes are active. `get_for_execution` is only used by the stale base `Worker.get_output()` path; `ReActWorker` already reads context events. Context event listeners are handled by `ContextEventRepository.add_listener`. | Delete | Once base `Worker.get_output()` and API readers use context events, the generation-turn repository surface is obsolete. | Medium | Migrate base output/readers first, then delete the repository class. |
| Query namespace | `core/persistence/queries.py` | `queries.evaluations` / `EvaluationsQueries` | No repo-wide `queries.evaluations` usage. Evaluation reads use direct `select(RunTaskEvaluation)` in run read paths or evaluation-specific services. | Delete | Unused namespace branch. With no external consumers, keeping a complete-but-unused query facade is unnecessary. | Medium | Remove `EvaluationsQueries` and `Queries.evaluations`; run import/type checks. |
| Query namespace | `core/persistence/queries.py` | `ResourcesQueries.list_latest_for_execution` | No repo-wide caller found. Other code uses `list_by_execution`, `list_by_run`, `latest_by_path`, `append`, or direct queries. | Delete | Unused convenience method. | Low | Remove method; run tests that touch resources. |
| Shared typing | `core/persistence/shared/types.py` | `BenchmarkSlug`, `ExecutionId` | No repo-wide imports beyond definition. Sibling aliases like `TaskSlug`, `AssignedWorkerSlug`, `NodeId`, `RunId`, `DefinitionId`, and `EdgeId` are used. | Delete | They are not part of the live type surface. | Low | Remove only these aliases. |

## Generation, Judges, and Evaluation Helpers

| Area | File | Symbol / module | Current evidence | Decision | Why | Risk | Follow-up test/check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LLM judge provider | `core/providers/judges/llm_judge.py` | Entire module, `LLMJudgeResponse`, `call_llm_judge` | No imports from `core.providers.judges`. Active judge behavior lives on `DefaultCriterionRuntime.call_llm_judge()` and includes runtime options like model, max tokens, and temperature. | Delete | Stale duplicate. If a shared helper is wanted later, extract it from the active runtime method rather than keeping this older subset. | Medium | Delete module and run evaluator tests. |
| VLLM generation | `core/providers/generation/vllm_model.py` | Entire module, `resolve_model_target`, `ResolvedModel`, `_discover_vllm_model_name`, `VLLMDiscoveryError` | Production imports use `core/providers/generation/model_resolution.py` and builtins vLLM backend. Only tests reference this stale module. | Delete | Duplicate model-resolution path. Keeping two implementations risks divergent behavior. | Medium | Remove/replace stale tests that target this module. |
| PydanticAI format parsing | `core/providers/generation/pydantic_ai_format.py` | `extract_text`, `extract_tool_calls` | No repo-wide callers. `extract_logprobs` is used by builtins `react_worker`. Active text/tool extraction uses typed `ModelResponse` / `GenerationTurn.response_parts`, not serialized dict parsing. | Delete | Unused dict parsers. Keep `extract_logprobs` and the module because logprob extraction is active. | Medium | Remove these two functions only; run generation-turn tests. |
| PydanticAI format parsing | `core/providers/generation/pydantic_ai_format.py` | `extract_logprobs` | Imported by `ergon_builtins/workers/baselines/react_worker.py`. | Keep | Active behavior. | Low | None. |
| Evaluation schema re-exports | `core/runtime/evaluation/evaluation_schemas.py` | `LLMJudgeResponse` | Listed in `__all__`, no imports from this file found. There is another `LLMJudgeResponse` in stale judge provider. | Delete | Redundant schema export with no in-repo caller. | Low | Remove and run evaluator/import tests. |
| Evaluation schema re-exports | `core/runtime/evaluation/evaluation_schemas.py` | `CommandResult`, `SandboxResult` re-exports | Imported into this module and re-exported, but no callers import these names from this module. | Delete | Barrel/re-export noise with no in-repo caller. | Low | Remove and run evaluator/import tests. |

## RL and Rollout

| Area | File | Symbol / module | Current evidence | Decision | Why | Risk | Follow-up test/check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RL polling | `core/rl/polling.py` | `PollTimeoutError`, `poll_until_all_complete` | No repo-wide caller. Docstring says used by TRL adapter, but adapter polls through `RolloutService`. | Delete | Stale helper. | Low | Search after deletion. |
| TRL adapter | `core/rl/trl_adapter.py` | `make_ergon_rollout_func` | No repo-wide caller. Module is explicitly marked deprecated in favor of HTTP adapter. Vulture flags unused `trainer` parameter. | Delete | Sunset path. `ergon_infra/adapters/trl_http.py` is the current replacement. | Medium | Confirm no external in-process TRL users. |
| RL package exports | `core/rl/__init__.py` | `VLLM_LOGPROB_SETTINGS` | Alias to `LOGPROB_SETTINGS`; no repo-wide caller. | Delete | Compatibility alias only, and external compatibility is not needed. | Low | Remove and run import checks. |

## Miscellaneous Core

| Area | File | Symbol / module | Current evidence | Decision | Why | Risk | Follow-up test/check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Core utils | `core/utils.py` | `get_mime_type` | No repo-wide caller. | Delete | Small unused helper. | Low | Search after deletion. |
| OpenRouter budget | `core/providers/generation/openrouter_budget.py` | `OpenRouterBudget` | Mostly referenced from tests/fixtures/benchmarks rather than active production modules. | Keep | Useful for real-LLM test budget gating. Not dead in the test harness context. | Low | None. |
| Dashboard emitter | `core/dashboard/emitter.py` | `_RunContextEvent` import | Vulture flags unused import. | Delete | Straight unused import cleanup. | Low | Run lint/type check. |
| RL extraction | `core/rl/extraction.py` | `add_special_tokens` parameter on `Tokenizer.encode()` protocol | Vulture flags it, but it is part of a `Protocol` signature matching common tokenizer APIs. Callers intentionally use bare `tokenizer.encode(...)`. | Keep | Static-analysis false positive. The parameter documents compatibility with tokenizer implementations such as Hugging Face tokenizers. | Low | If vulture noise matters, suppress/allowlist instead of deleting the protocol parameter. |

## Frontend / Dashboard Context-Event Migration

| Area | File | Symbol / module | Current evidence | Decision | Why | Risk | Follow-up test/check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Run state hydration | `ergon-dashboard/src/lib/runState.ts` | `deserializeRunState()` / `deserializeGenerationTurns()` | Snapshot hydration reads `generationTurnsByTask` but initializes `contextEventsByTask` as an empty `Map`. | Port/use | Snapshot state should hydrate `contextEventsByTask` from the backend and stop treating `generationTurnsByTask` as the action source. | High | Add a refresh/snapshot test proving tool calls render from persisted context events. |
| Run state live updates | `ergon-dashboard/src/hooks/useRunState.ts` | socket listener set | The hook subscribes to `generation:turn` but not `context:event`, even though the socket server broadcasts context events. | Port/use | Live action updates should flow through `context:event`. | High | Add a live delta test that posts/sends a context event and sees it in the task workspace/event stream. |
| Task action UI | `ergon-dashboard/src/components/workspace/TaskWorkspace.tsx` | `GenerationTracePanel` use | The workspace renders `GenerationTracePanel` from `runState.generationTurns`; `ContextEventLog` exists but is not mounted here. | Port/use | The task workspace should render agent actions from `ContextEventLog` / context-derived events. | High | Replace/demote the generations panel and assert tool calls/tool results appear for the selected task. |
| Unified event stream | `ergon-dashboard/src/lib/runEvents.ts` | generation/context event conversion | The stream includes both generation turns and context events, but context events are currently generic summaries and may never arrive in state. | Port/use | Use context events for action-level timeline entries; remove generation-turn timeline entries once the old source is gone. | Medium | Snapshot and live-stream tests should cover `tool_call`, `tool_result`, `assistant_text`, and `thinking`. |
| Dashboard event bridge | `ergon-dashboard/src/inngest/functions/index.ts` | `dashboard/generation.turn_completed` handler | Generation-turn dashboard handler remains, but Python no longer appears to emit generation-turn events; context-event handler is the active bridge. | Delete | Stale frontend event listener around the old generation-turn source. | Medium | Delete after context-event UI path is wired; verify no `generation:turn` tests depend on it. |
| Dashboard REST/API contracts | `ergon_core/core/api/schemas.py`, `ergon_core/core/runtime/services/run_read_service.py`, `ergon_core/core/api/runs.py`, `ergon-dashboard/src/generated/rest/contracts.ts` | `RunGenerationTurnDto`, `generation_turns_by_task`, `/runs/{run_id}/generations` | Backend snapshots still expose generation turns, and FE generated contracts still include `generationTurnsByTask`. | Delete | Once context-event hydration is exposed and consumed, the generation-turn API surface is stale. | High | Add/verify `contextEventsByTask` in contracts, then remove generation-turn endpoint/DTO fields. |
| Telemetry schema | `core/persistence/telemetry/models.py` and migrations | `RunGenerationTurn` table/model | The table/model exist for the old turn summary. Current canonical replay/action log is `RunContextEvent`. | Delete | Remove after all readers and tests migrate to context events. | High | Requires migration cleanup or a new migration strategy; do after application code no longer references it. |

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
   - Delete event/schema/error aliases directly; this repo has no external consumers to protect.

6. Context-event dashboard migration:
   - Wire snapshots and live socket updates to `contextEventsByTask`.
   - Render task actions from context events.
   - Remove generation-turn dashboard listeners, DTOs, API endpoint, repository, and table/model after readers are gone.

## Propagation-Specific Conclusion

The current active propagation logic is not missing from the old helpers; it is
more complete than the old helpers. The old helpers are stale because they either
operate on static definition dependencies or use pre-`BLOCKED` terminal semantics.
The highest-value cleanup is to remove the stale helpers from `propagation.py`
so future work cannot accidentally call them.

