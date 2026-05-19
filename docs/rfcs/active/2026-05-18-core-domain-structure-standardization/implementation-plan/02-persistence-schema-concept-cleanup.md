# PR 02: Persistence Schema Concept Cleanup

## What

Remove or isolate stale persistence concepts that are either invalid in the v2
schema or compatibility-only: import reducer tables, run definition identity
debt, training observability ambiguity, rollout status strings, and legacy
experiment/cohort table helpers.

## Why

PR 01 fixes ownership where the replacement is clear. This PR handles the
remaining schema concept debt so later adapter and runtime moves do not need to
carry broken identities or dead tables forward.

## How

- Delete `core/persistence/imports/models.py` and
  `core/persistence/imports/`.
- Make `RunRecord.definition_id` the canonical runtime definition id.
- Backfill/update runtime reads and writes away from
  `RunRecord.workflow_definition_id`, then delete that field.
- Remove stale `RunRecord.experiment_id` references.
- Add field descriptions marking `RunRecord.worker_team_json`,
  `evaluator_slug`, `sandbox_slug`, and `dependency_extras_json` as
  compatibility/display-only until later PRs remove reads.
- Decide the training surface:
  - either identify/add the production writer and move training DTOs to
    `views/training.py`;
  - or delete `TrainingSession`, `TrainingMetric`, `/runs/training/*`,
    generated contracts, and dashboard training UI together.
- Create `core/shared/rollout_status.py` and use it from
  `core/rl/rollout_types.py` and `RolloutBatch.status`.
- Move non-table legacy experiment/cohort helpers into
  `application/compat/*` only where needed for temporary callers.

## Plan

1. Add schema tests that fail on foreign keys pointing at missing columns.
2. Add source tests that fail on `RunRecord.experiment_id` references.
3. Delete reducer/drop-manifest persistence models and imports.
4. Update migration/schema creation imports so reducer tables are absent.
5. Change launch/run creation paths to write `RunRecord.definition_id`.
6. Change read paths to use `RunRecord.definition_id`.
7. Delete `workflow_definition_id` once no code reads or writes it.
8. Remove broken CLI run filtering that joins through `experiment_id`; leave
   experiment-tag filtering for PR 08/09.
9. Mark display-only run selection fields in model descriptions.
10. Resolve the training gate in one direction; do not leave a half-moved
    training surface.
11. Introduce `RolloutStatus` in `core/shared/rollout_status.py`.
12. Update rollout models and persistence validation to use the shared status.

## Acceptance Criteria

- `core/persistence/imports/` is gone.
- No schema field references a non-existent target column.
- No production code references `RunRecord.experiment_id`.
- `RunRecord.definition_id` is the canonical runtime definition id.
- `workflow_definition_id` is gone.
- Training is either explicitly retained with a writer and `views/training.py`,
  or deleted across backend/frontend/contracts.
- Rollout status vocabulary is shared, not persistence-local.

## Tests

```bash
pytest ergon_core/tests/unit/persistence -q
pytest ergon_core/tests/unit/architecture -q
pytest ergon_core/tests/unit/rl -q
pytest ergon_cli/tests -q
rg -n "workflow_definition_id|experiment_id|persistence/imports|RunReducer|RunDropsManifest" ergon_core ergon_cli
```

