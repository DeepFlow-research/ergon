# PRD 01: Persistence And Schema Boundary

## Goal

Make `ergon_core.core.persistence` a true storage-definition layer and remove
business/application concepts that currently live there by accident.

## Target State

`persistence/` owns:

- SQLModel table definitions;
- database/session setup;
- storage-safe enums/types and ids;
- low-level row validation for JSON columns and persisted enum values;
- schema artifacts needed by migrations and final schema audits.

`persistence/` does not own:

- application command DTOs;
- domain repositories;
- runtime lifecycle status policy;
- evaluation summary semantics;
- compatibility-service logic;
- infrastructure writes that duplicate application services.

Application-facing repositories live under their application domain. Persistence
table modules may expose row helpers, but command semantics live above them.

## Required Moves

### Evaluation Persistence

- Delete `core/persistence/telemetry/repository.py` rather than moving it.
  `TelemetryRepository` has only one production consumer,
  `core/application/evaluation/service.py`, and only two methods.
- Delete `CreateTaskEvaluation` from `core/persistence/telemetry/models.py`
  rather than moving it. It exists only to pass arguments from
  `EvaluationService` back into the single-consumer repository.
- Add private helpers to `EvaluationService`:
  `_list_task_evaluations(session, run_id)` and
  `_create_task_evaluation(session, *, run_id, task_execution_id, task_id,
  definition_evaluator_id, score, passed, feedback, summary_json)`.
- Keep `RunTaskEvaluation` in `core/persistence/telemetry/models.py`; it is the
  storage table the evaluation service writes.
- Do not create `core/application/evaluation/repository.py` in this PRD.

### Evaluation Summary Contract

- Move `core/persistence/telemetry/evaluation_summary.py` to
  `core/application/evaluation/summary.py`.
- Move `CriterionOutcomeEntry`, `EvaluationSummary`, and
  `EvalCriterionStatus` together.
- Update these imports to the application path:
  `core/application/evaluation/service.py`,
  `core/application/read_models/models.py`,
  `core/application/read_models/cohorts.py`, and tests.
- Delete `RunTaskEvaluation.parsed_summary()` from
  `core/persistence/telemetry/models.py`; application read paths should call
  `EvaluationSummary.model_validate(evaluation.summary_json)` explicitly.
- Merge the duplicated DTO mapping in
  `EvaluationService.build_dashboard_evaluation_dto()` and
  `read_models/run_snapshot._task_keyed_evaluations()` into
  `core/application/evaluation/dto_mapping.py::evaluation_row_to_dto(...)`.
- Keep the schema in `application/evaluation`, not persistence, because it is
  evaluation-domain semantics over a JSON column rather than storage shape.

### Runtime Status Contract

- Create `core/application/runtime/status.py`.
- Move the contents of `core/persistence/graph/status_conventions.py` into
  `core/application/runtime/status.py`.
- Update imports in `application/graph`, `application/tasks`,
  `application/workflows`, dashboard event contracts, dashboard emitter, smoke
  fixtures, and propagation/restart tests to import from
  `core.application.runtime.status`.
- Delete `core/persistence/graph/status_conventions.py`; graph table models
  keep string columns and do not own runtime lifecycle vocabulary.

### Context Event Payload Alias

- Delete `core/persistence/context/event_payloads.py`.
- PRD 02 moves `ContextEventType` into `core/shared/context_parts.py` and
  deletes `ContextEventPayload`; persistence, read-model, and dashboard code
  should annotate payloads as `ContextPartChunkLog` directly.

### Import/Reducer Tables

- Delete `core/persistence/imports/models.py` and the
  `core/persistence/imports/` package.
- Remove `RunReducer` and `RunReducerFootprint` from schema creation.
- Reason: no production writer/reader remains, and `RunReducer.node_id`
  references `run_graph_nodes.id`, which is not the canonical v2 graph
  identity.

### Run Identity And Legacy Experiment Fields

- Make `RunRecord.definition_id` the canonical FK to
  `experiment_definitions.id`.
- Backfill `RunRecord.definition_id` from `RunRecord.workflow_definition_id`,
  update all reads/writes to use `definition_id`, then delete
  `workflow_definition_id`.
- Delete stale references to `RunRecord.experiment_id`; for CLI run filtering,
  remove the broken `--experiment` join until PRD 07 adds run grouping through
  `RunRecord.experiment`.
- Keep `RunRecord.model_target` active; `TaskExecutionService` still uses it as
  a fallback model target.
- Keep `RunRecord.assignment_json` active as the run-level launch/provenance
  metadata bag.
- Keep `RunRecord.worker_team_json`, `RunRecord.evaluator_slug`,
  `RunRecord.sandbox_slug`, and `RunRecord.dependency_extras_json` in PRD 01,
  but mark them compatibility/display-only in `RunRecord` field descriptions.
  PRD 05 removes runtime reads of `sandbox_slug`; PRD 07 removes legacy
  dashboard/CLI display dependencies.

### Training And Rollout Tables

- Treat `TrainingSession` and `TrainingMetric` as gated deletion candidates,
  not folder-move candidates. Core has REST reads and dashboard pages for them,
  but the audit found no in-repo production writer.
- If training observability is still a product surface, make the writer
  explicit and move `TrainingCurvePointDto`, `TrainingSessionDto`, and
  `TrainingMetricDto` to `views/training.py`.
- If training observability is stale, delete `TrainingSession`,
  `TrainingMetric`, `/runs/training/*`, generated REST contract entries, and
  dashboard training UI together.
- Move rollout batch status vocabulary out of persistence-local strings into a
  shared rollout status enum, `core/shared/rollout_status.py`, and have both
  `core/rl/rollout_types.py` and `RolloutBatch.status` use that enum.

### Compatibility Tables

- Keep `BenchmarkDefinitionRecord`, `ExperimentCohort`, and
  `ExperimentCohortStats` only as compatibility tables until PRD 07 removes
  their writers, dashboard contracts, REST routes, and frontend pages.
- Move all non-table helpers and service logic for those tables into
  `core/application/compat/legacy_experiments.py` and
  `core/application/compat/cohorts.py`; persistence keeps only the SQLModel
  classes while the compatibility window is open.

## Non-Goals

- Do not restructure `application/tasks`, `application/workflows`, and
  `application/graph` in this slice.
- Do not delete cohort/dashboard compatibility until the dashboard PRD has a
  replacement.
- Do not split all telemetry tables purely for aesthetics.

## Acceptance Criteria

- New tests enforce that persistence model modules do not import concrete
  infrastructure or define application command DTOs.
- No production code references `RunRecord.experiment_id`.
- No schema field references a non-existent target column.
- Evaluation persistence is reached through `EvaluationService`, with no
  separate single-consumer telemetry repository.
- Status constants used by runtime services no longer live under
  `persistence/graph`.
- `core/persistence/imports/` is gone.
- Training tables are either backed by an explicit writer and moved to a
  training view, or deleted together with REST/frontend consumers.
- Any remaining legacy/compatibility tables are reachable only through
  `core/application/compat/*`.

## Evidence

- [`../audits/persistence-boundary-audit.md`](../audits/persistence-boundary-audit.md)
- [`../audits/schema-concept-debt-audit.md`](../audits/schema-concept-debt-audit.md)
