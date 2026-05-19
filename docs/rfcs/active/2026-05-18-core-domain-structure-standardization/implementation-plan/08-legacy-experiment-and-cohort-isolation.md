# PR 08: Legacy Experiment And Cohort Isolation

## What

Route all remaining cohort and legacy experiment-record behavior through
explicit compatibility modules without deleting the frontend/backend surfaces
yet.

## Why

Cohorts and `BenchmarkDefinitionRecord` are deprecated, but still active in
dashboard, CLI, test harness, RL rollout, and completion/failure paths. Deleting
them before replacement would break users. This PR makes every remaining usage
obviously temporary and prepares the deletion PR.

## How

- Add nullable `RunRecord.experiment: str | None` for v2 run grouping.
- Create `core/application/compat/legacy_experiments.py`.
- Create `core/application/compat/cohorts.py`.
- Move legacy fallback experiment detail builders into
  `legacy_experiments.py`.
- Move `ExperimentCohortService` into
  `DeprecatedCohortCompatibilityService`.
- Route HTTP cohort endpoints and test harness marker writes through compat.
- Move deprecated cohort event emission orchestration into compat.
- Stop RL rollout from creating `BenchmarkDefinitionRecord`; use
  `RolloutBatch` and canonical `RunRecord.definition_id`.
- Update CLI experiment tag reads to prefer `RunRecord.experiment`.

## Plan

1. Add tests showing canonical experiment reads use `ExperimentDefinition`
   before legacy fallback.
2. Add tests around `RunRecord.experiment` grouping.
3. Add tests that RL rollout does not write `BenchmarkDefinitionRecord`.
4. Create `application/compat` modules with docstrings marking deletion owner.
5. Move legacy experiment helper logic.
6. Move cohort service logic into the deprecated compatibility service.
7. Route HTTP/test harness/dashboard cohort emission through compat.
8. Update CLI experiment listing and lookup to use `RunRecord.experiment`.
9. Add architecture/source tests limiting `BenchmarkDefinitionRecord` and
   cohort table imports to compat, persistence table definitions, and tests.

## Acceptance Criteria

- All non-table `BenchmarkDefinitionRecord` behavior is behind
  `application/compat/legacy_experiments.py`.
- All cohort behavior is behind `application/compat/cohorts.py` or
  `views/compat/cohorts.py`.
- RL rollout provenance no longer creates `BenchmarkDefinitionRecord`.
- CLI grouping can use `RunRecord.experiment`.
- New runtime/application code does not depend on cohorts.

## Tests

```bash
pytest ergon_core/tests/unit/read_models -q
pytest ergon_core/tests/unit/rl -q
pytest ergon_core/tests/unit/rest_api -q
pytest ergon_cli/tests -q
pytest ergon_core/tests/unit/architecture -q
rg -n "BenchmarkDefinitionRecord|ExperimentCohort|ExperimentCohortStats" ergon_core/ergon_core/core ergon_cli
```

