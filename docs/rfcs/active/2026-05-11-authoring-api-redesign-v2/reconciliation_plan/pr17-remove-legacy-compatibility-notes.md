# PR 17 Remove Legacy Compatibility Notes

Date: 2026-05-18

## Why

PR 16 removed the last broad bridge/debt structures, but several active source
paths still preserved pre-v2 compatibility semantics. The most confusing parts
were public variables named `experiment_id` even though the value was now the
canonical v2 definition id, plus read-model and test-harness paths that used
`BenchmarkDefinitionRecord` as a compatibility row beside
`ExperimentDefinition`.

This PR makes the v2 contract explicit: active runtime, API, CLI, test, and
dashboard code speaks in terms of definition identity. There are no source/test
references to old compatibility paths, and no active read model falls back from
`ExperimentDefinition` to the older benchmark-definition row.

## How

- Added architecture guards for active source/test references to compatibility
  language and for `experiment_id` / `experimentId` naming.
- Removed small public API aliases and fallback fields:
  `Task.evaluator_binding_keys`, `Criterion.validate_deps()`, and
  `ResearchRubricsJudgeCriterion(model=...)` / `.model`.
- Renamed active REST/event/dashboard DTO identity fields from experiment
  vocabulary to `definition_id` / `definitionId` where they represent
  definition identity.
- Removed `BenchmarkDefinitionRecord` read-model and test-harness
  compatibility writes. Cohort/display metadata for harness-created
  definitions now lives in `ExperimentDefinition.metadata_json`.
- Updated cohort/run read models, workflow completion/failure tracing, CLI
  filters, RL rollout creation, and integration fixtures to use canonical
  definition rows directly.
- Regenerated dashboard event schemas, OpenAPI, and generated REST/event Zod
  contracts from the backend after the rename.

## Gotchas

- The `experiments` REST route and UI route names still exist as product
  language, but the route parameter and payload identity fields are
  `definition_id` / `definitionId`.
- Cohort membership no longer comes from `BenchmarkDefinitionRecord.cohort_id`.
  New test-harness cohorts stamp `ExperimentDefinition.metadata_json["cohort_id"]`.
  This avoids a schema migration in PR 17 while removing the compatibility row.
- `BenchmarkDefinitionRecord` still exists as a persistence model because
  deleting the table/model is schema work. This PR removes active compatibility
  reads/writes from source paths covered by the guards.
- Dashboard generated files were regenerated after writing
  `ergon-dashboard/src/generated/rest/openapi.json` from `app.openapi()`.
  Review generated diffs together with the backend DTO changes.
