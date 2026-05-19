# PR 09: Legacy Cohort And Experiment Deletion

## What

Delete deprecated cohort surfaces and legacy experiment-record compatibility
after PR 08 has isolated them.

## Why

PR 08 makes the compatibility debt explicit. This PR removes it, including the
frontend/dashboard surfaces, generated contracts, backend routes, compatibility
services, and persistence tables. Without this deletion PR, the stack would
leave v1 grouping concepts preserved under cleaner names.

## How

- Delete dashboard cohort pages, hooks, server-data helpers, and API proxy
  routes.
- Replace dashboard grouping with `RunRecord.experiment`.
- Delete generated cohort dashboard event contracts and REST entries.
- Delete backend cohort HTTP route.
- Delete `ExperimentCohort`, `ExperimentCohortStats`, and related status
  types.
- Delete `BenchmarkDefinitionRecord` after all CLI/RL/test/dashboard callers
  use v2 definitions and run grouping.
- Delete compatibility modules once no production code imports them.

## Plan

1. Add frontend tests or route checks for the replacement run grouping surface.
2. Add backend tests proving run grouping uses `RunRecord.experiment`.
3. Delete dashboard cohort pages and hooks.
4. Delete frontend API proxy route for cohorts.
5. Regenerate frontend/backend contracts without cohort events/routes.
6. Delete backend cohort HTTP route.
7. Delete cohort compatibility service and view modules.
8. Delete cohort tables and schema references.
9. Delete `BenchmarkDefinitionRecord` and its compatibility module once no
   production references remain.
10. Remove smoke/e2e navigation through cohort pages.

## Acceptance Criteria

- No production code references `ExperimentCohort`,
  `ExperimentCohortStats`, or `ExperimentCohortStatus`.
- No production code references `BenchmarkDefinitionRecord`.
- Dashboard has no cohort pages, hooks, generated event contracts, or REST
  proxy routes.
- CLI and dashboard grouping use `RunRecord.experiment`.
- Compatibility modules from PR 08 are deleted or test-only.

## Tests

```bash
pytest ergon_core/tests/unit/persistence -q
pytest ergon_core/tests/unit/rest_api -q
pytest ergon_cli/tests -q
pytest ergon_core/tests/unit/architecture -q
pnpm --dir ergon-dashboard test
rg -n "BenchmarkDefinitionRecord|ExperimentCohort|CohortUpdatedEvent|cohorts" ergon_core ergon_cli ergon-dashboard/src
```

