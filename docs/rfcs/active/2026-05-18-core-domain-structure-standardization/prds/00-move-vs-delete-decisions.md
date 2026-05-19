# PRD 00: Move Versus Delete Decisions

## Goal

Prevent the standardization PRDs from preserving dead or duplicate schemas just
because a folder move looks tidy.

## Decisions

| Item | Current Location | Verdict | Reason |
| --- | --- | --- | --- |
| `TelemetryRepository` | `core/persistence/telemetry/repository.py` | Delete, inline two private helpers into `EvaluationService`. | It has one production consumer and only wraps `RunTaskEvaluation` reads/writes for that service. Moving it would create a tiny fake repository. |
| `CreateTaskEvaluation` | `core/persistence/telemetry/models.py` | Delete. | It only shuttles arguments into `TelemetryRepository.create_task_evaluation()`. Once that repository dies, explicit keyword arguments are clearer. |
| `EvaluationSummary`, `CriterionOutcomeEntry`, `EvalCriterionStatus` | `core/persistence/telemetry/evaluation_summary.py` | Keep, move to `application/evaluation/summary.py`. | These are active semantic schemas for evaluation summaries. They are not storage tables, and read views need the same validation. |
| `RunTaskEvaluation.parsed_summary()` | `core/persistence/telemetry/models.py` | Delete. | It makes persistence import evaluation semantics. Application read paths should call `EvaluationSummary.model_validate(row.summary_json)` explicitly. |
| `WorkerYield` | `core/domain/generation/context_parts.py` | Delete. | It is only an alias for `ContextPartChunk`. |
| `ContextEventPayload` | `core/persistence/context/event_payloads.py` | Delete. | It is only an alias for `ContextPartChunkLog`. |
| `ContextEventType` | `core/persistence/context/event_payloads.py` | Keep, move to `core/shared/context_parts.py`. | It is an active event type literal used by read-model and dashboard contracts. |
| `WorkerRef` | `core/infrastructure/dashboard/event_contracts.py` | Delete during PRD 06. | It exists only to support `workflow.started.task_tree`; `RunSnapshotDto` already carries worker id/slug fields without a separate worker ref schema. |
| `TaskTreeNode` | `core/infrastructure/dashboard/event_contracts.py` | Delete during PRD 06. | It duplicates run snapshot task view and forces handwritten frontend recursive Zod schemas. |
| `DashboardWorkflowStartedEvent.task_tree` | `core/infrastructure/dashboard/event_contracts.py` | Replace with `snapshot: RunSnapshotDto`. | Reuses the existing run view instead of keeping a second graph-to-tree implementation. |
| `Dashboard*Event` contracts | `core/infrastructure/dashboard/event_contracts.py` | Keep, move to `views/dashboard_events/contracts.py`. | They are active generated frontend contracts, not emitter implementation details. |
| `CohortUpdatedEvent` | `core/infrastructure/dashboard/event_contracts.py` | Keep temporarily, delete in PRD 07. | It is active only while cohort UI/contracts remain. |
| `Test*Dto` classes | `core/rest_api/test_harness.py` -> `core/infrastructure/http/routes/test_harness.py` | Keep route-local. | They are Playwright/test-harness wire shapes, not product views. |
| `TrainingSession`, `TrainingMetric`, training DTOs/routes | `persistence/telemetry/models.py`, `application/read_models/models.py`, `rest_api/runs.py` -> `infrastructure/http/routes/runs.py` | Gated deletion. | Core has read endpoints and dashboard pages, but no in-repo production writer was found. If training is retained, make the writer explicit and move DTOs to `views/training.py`; if not, delete backend routes, generated contracts, and dashboard training UI together. |
| `RunReducer`, `RunReducerFootprint`, `RunDropsManifest` | `core/persistence/imports/models.py` | Delete. | No production writer/reader remains, and `RunReducer.node_id` references a non-existent graph column. |
| `Graph status` literals/helpers | `core/persistence/graph/status_conventions.py` | Keep, move to `application/runtime/status.py`. | They are active runtime lifecycle vocabulary, not persistence schema. |
| `BenchmarkDefinitionRecord` | `persistence/telemetry/models.py` | Keep temporarily behind `application/compat/legacy_experiments.py`, then delete in PRD 07. | Active compatibility table for dashboard/test/CLI/RL paths. |
| Cohort tables/services/DTOs | `persistence/telemetry/models.py`, `application/read_models/cohorts.py` | Keep temporarily behind `application/compat/cohorts.py`, then delete in PRD 07. | Active only for deprecated cohort UI and test harness compatibility. |

## Rule For Future PR Plans

When a PRD says "move schema", the implementation plan must first ask:

- Is this schema used by more than one production path?
- Is it a product/API contract, or just a local helper shape?
- Does an existing view already express the same data?
- Will moving it preserve duplicated logic that should be deleted instead?

If the answer points to a local helper, delete or inline it. If the answer
points to an active external contract, move it only when the old owner is wrong
and no existing contract can replace it.
