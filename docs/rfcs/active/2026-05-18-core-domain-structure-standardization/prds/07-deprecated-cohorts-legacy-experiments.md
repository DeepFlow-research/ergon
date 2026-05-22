# PRD 07: Deprecated Cohorts And Legacy Experiment Records

## Goal

Isolate and then remove v1/v2-bridge grouping concepts: cohorts and
`BenchmarkDefinitionRecord`.

## Target State

The v2 product concept is:

- an immutable definition describes authored work;
- a run executes one definition instance;
- an experiment is a collection/tag/composition of runs, not a legacy
  definition-shaped row;
- dashboard and CLI grouping use `RunRecord.experiment: str | None` as the v2
  grouping tag.

Cohorts and `BenchmarkDefinitionRecord` are not long-lived core domains.

## Required Moves

### V2 Run Grouping

- Add nullable `RunRecord.experiment: str | None`.
- Use this string as the v2 run grouping tag for Pythonic composition, CLI
  grouping, and dashboard run grouping.
- Do not create `application/cohorts` as a permanent domain and do not create a
  replacement cohort table.

### Legacy Experiment Record Isolation

- Keep `BenchmarkDefinitionRecord` temporarily as a compatibility table only.
- Move all non-table legacy experiment helpers to
  `application/compat/legacy_experiments.py`.
- Move the legacy fallback detail builder from
  `application/read_models/experiments.py::_legacy_benchmark_definition_record_detail`
  into `application/compat/legacy_experiments.py`.
- Update canonical experiment read paths to read `ExperimentDefinition` first
  and call the compatibility module only for legacy rows.
- Delete `BenchmarkDefinitionRecord` after RL rollout, test harness, CLI,
  dashboard, `application/jobs/complete_workflow.py`, and
  `application/jobs/fail_workflow.py` no longer read or write it.

### Cohort Compatibility Isolation

- Keep `ExperimentCohort`, `ExperimentCohortStats`, and
  `ExperimentCohortStatus` temporarily as compatibility tables only.
- Move `ExperimentCohortService` from `application/read_models/cohorts.py` to
  `application/compat/cohorts.py::DeprecatedCohortCompatibilityService`.
- Leave read-only DTO assembly in `views/dashboard_events/cohorts.py`
  and `views` after PRD 06.
- Route `core/infrastructure/http/routes/cohorts.py` through
  `DeprecatedCohortCompatibilityService` and mark the route module deprecated.
- Move test harness cohort marker writes to
  `application/compat/cohorts.py::write_legacy_cohort_marker`.
- Move module-level `emit_cohort_updated_for_run()` from
  `core/infrastructure/dashboard/emitter.py` to
  `application/compat/cohorts.py::emit_deprecated_cohort_updated_for_run`.

### RL Rollout Provenance

- Stop `core/rl/rollout_service.py` from creating `BenchmarkDefinitionRecord`.
- Use `RolloutBatch` as rollout provenance.
- Set `RunRecord.definition_id = request.definition_id` for rollout runs.
- After PRD 01 removes `workflow_definition_id`, do not write it.
- Store rollout policy/model metadata on `RolloutBatch` or
  `RunRecord.assignment_json`, not on `BenchmarkDefinitionRecord`.

### CLI Replacement

- Delete `BenchmarkDefinitionRecord.experiment` reads from
  `ergon_cli/commands/experiment.py`.
- Reimplement experiment tag listing and lookup against
  `RunRecord.experiment`.
- Delete the broken `RunRecord.experiment_id` join in
  `ergon_cli/commands/run.py`.
- Reimplement `ergon run --experiment <tag>` as
  `RunRecord.experiment == <tag>` after the new field exists.

### Dashboard And Frontend Deletion Gate

- Delete cohort UI/proxy/generated-contract dependencies before deleting
  backend cohort routes/tables:
  `ergon-dashboard/src/app/cohorts/page.tsx`,
  `ergon-dashboard/src/app/cohorts/[cohortId]/page.tsx`,
  `ergon-dashboard/src/app/cohorts/[cohortId]/runs/[runId]/page.tsx`,
  `ergon-dashboard/src/app/api/cohorts/route.ts`,
  `ergon-dashboard/src/hooks/useCohorts.ts`,
  `ergon-dashboard/src/lib/server-data/cohorts.ts`,
  generated `CohortUpdatedEvent`, generated REST contract entries for cohort
  endpoints, and smoke/e2e routes that navigate through cohorts.
- Replace dashboard cohort grouping with run grouping over
  `RunRecord.experiment`.
- Delete backend cohort REST routes, compatibility service, tables, and
  dashboard cohort event contracts after the frontend no longer imports them.

### Training Is Not Cohort Compatibility

- Do not fold `TrainingSession` and `TrainingMetric` into this PRD's
  cohort/legacy experiment deletion. PRD 01 owns the separate decision: either
  keep training observability with an explicit writer and a training view,
  or delete backend and frontend training surfaces together.

## Non-Goals

- Do not delete tables before dashboard and CLI replacements land.
- Do not invent a broad experiment-management product surface in this cleanup.
- Do not make `application/cohorts` a permanent domain.

## Acceptance Criteria

- All cohort and legacy experiment record usages are either deleted or routed
  through an explicitly named deprecated compatibility module.
- No new runtime service depends on cohort membership.
- RL rollout provenance no longer requires `BenchmarkDefinitionRecord`.
- Dashboard no longer imports/generated-types for cohort contracts before
  tables/routes are deleted.
- CLI experiment grouping uses `RunRecord.experiment`.

## Evidence

- [`../audits/schema-concept-debt-audit.md`](../audits/schema-concept-debt-audit.md)
- [`../audits/persistence-boundary-audit.md`](../audits/persistence-boundary-audit.md)
