# PR 01: Persistence Evaluation And Status Cleanup

## What

Remove application semantics from persistence where the replacement is already
obvious: evaluation summary schemas, the single-consumer telemetry repository,
and graph status vocabulary.

## Why

Persistence currently owns more than storage shape. `TelemetryRepository` and
`CreateTaskEvaluation` form a tiny repository around one evaluation service,
`evaluation_summary.py` models evaluation-domain semantics over a JSON column,
and `graph/status_conventions.py` owns runtime lifecycle vocabulary. Keeping
these in persistence makes later runtime and views work inherit the wrong
ownership boundary.

## How

- Delete `core/persistence/telemetry/repository.py`.
- Delete `CreateTaskEvaluation` from
  `core/persistence/telemetry/models.py`.
- Add private helpers to `core/application/evaluation/service.py`:
  `_list_task_evaluations(...)` and `_create_task_evaluation(...)`.
- Move `core/persistence/telemetry/evaluation_summary.py` to
  `core/application/evaluation/summary.py`.
- Move dashboard/read DTO conversion that is duplicated between evaluation
  service and run snapshots into
  `core/application/evaluation/dto_mapping.py`.
- Delete `RunTaskEvaluation.parsed_summary()` from
  `core/persistence/telemetry/models.py`.
- Move `core/persistence/graph/status_conventions.py` to
  `core/application/runtime/status.py`.
- Update imports in application graph/tasks/workflows, dashboard contracts,
  dashboard emitter, smoke fixtures, and tests.

## Plan

1. Add characterization tests for `EvaluationService.evaluate()` persistence:
   one test should assert that a `RunTaskEvaluation` row is written with the
   same `summary_json`, score, pass/fail, task execution id, task id, and
   definition evaluator id as today.
2. Add a unit test for the new `evaluation_row_to_dto(...)` mapper using a
   stored `RunTaskEvaluation` row with multiple criterion outcomes.
3. Add an architecture test that `core.persistence.telemetry.models` does not
   import `core.application.evaluation.summary`.
4. Inline `TelemetryRepository.get_task_evaluations()` and
   `TelemetryRepository.create_task_evaluation()` into private helpers on
   `EvaluationService`.
5. Replace `CreateTaskEvaluation(...)` construction with explicit keyword
   arguments.
6. Move `EvaluationSummary`, `CriterionOutcomeEntry`, and
   `EvalCriterionStatus` into `application/evaluation/summary.py`.
7. Replace all imports of
   `core.persistence.telemetry.evaluation_summary`.
8. Replace `RunTaskEvaluation.parsed_summary()` call sites with
   `EvaluationSummary.model_validate(evaluation.summary_json)`.
9. Move status constants/helpers into `application/runtime/status.py`.
10. Delete the old persistence files after imports are clean.

## Acceptance Criteria

- No production code imports `core.persistence.telemetry.repository`.
- No production code references `CreateTaskEvaluation`.
- No production code imports `core.persistence.telemetry.evaluation_summary`.
- No production code imports `core.persistence.graph.status_conventions`.
- Evaluation summary validation still happens through `EvaluationSummary`.
- Runtime status vocabulary lives under `core.application.runtime.status`.

## Tests

```bash
pytest ergon_core/tests/unit/evaluation -q
pytest ergon_core/tests/unit/runtime -q
pytest ergon_core/tests/unit/dashboard/test_event_contract_types.py -q
pytest ergon_core/tests/unit/architecture -q
rg -n "TelemetryRepository|CreateTaskEvaluation|persistence\\.telemetry\\.evaluation_summary|persistence\\.graph\\.status_conventions" ergon_core/ergon_core
```

