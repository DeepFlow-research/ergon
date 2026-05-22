# PRD 04: REST As Thin Inbound Adapter

## Goal

Move REST routes under `infrastructure/http/` and keep them as thin inbound
adapters that call application services and views. REST should not become
application logic.

## Target State

`infrastructure/http/` owns:

- HTTP route registration;
- request parsing and validation;
- mapping application errors to HTTP errors;
- response model selection;
- FastAPI app lifespan and HTTP composition wiring.

`infrastructure/http/` does not own:

- runtime lifecycle policy;
- persistence queries when an application view/service exists;
- cohort compatibility behavior;
- dashboard-specific contract assembly;
- business DTO transformations that should be shared by CLI/dashboard/API.

The current top-level `core/rest_api/` package is temporary. The final home is
`core/infrastructure/http/`, not `application`, because route modules are
framework adapters rather than business use cases.

## Required Moves

### Route Decisions

| Route file | Decision |
| --- | --- |
| `core/rest_api/runs.py` -> `core/infrastructure/http/routes/runs.py` | Move. It already calls `RunReadService`; update imports when PRD 06 moves read models to views. |
| `core/rest_api/experiments.py` -> `core/infrastructure/http/routes/experiments.py` | Move. It already calls `ExperimentReadService` and `run_experiment`; update imports when view/service modules move. |
| `core/rest_api/cohorts.py` -> `core/infrastructure/http/routes/cohorts.py` | Move only as deprecated compatibility until PRD 07. Route it through `core/application/compat/cohorts.py`, then delete it with the frontend cohort cleanup. |
| `core/rest_api/rollouts.py` -> `core/infrastructure/http/routes/rollouts.py` | Move. It is a transport wrapper around `RolloutService`/`VLLMManager`, not route-owned query logic. |
| `core/rest_api/app.py` -> `core/infrastructure/http/app.py` | Move as the HTTP composition/bootstrap module. Add a docstring naming its persistence/infrastructure imports as bootstrap exceptions. |
| `core/rest_api/test_harness.py` -> `core/infrastructure/http/routes/test_harness.py` | Move route-local DTOs. Split only the reusable write/query behavior; do not promote Playwright-only DTOs into application views. |

### Test Harness Split

- Keep `TestGraphNodeDto`, `TestEvaluationDto`, `TestGraphMutationDto`,
  `TestExecutionDto`, `TestRunStateDto`, `TestCohortRunDto`, and
  `TestCohortIdDto` in `core/infrastructure/http/routes/test_harness.py`.
  They are used only as Playwright/test-harness wire shapes; moving them to
  application would create a fake product view.
- Move the read/query construction behind `read_run_state`,
  `read_cohort_id`, and `read_cohort_runs` only if another test harness or
  dashboard utility reuses it. Otherwise keep it route-local and document the
  whole module as a test-only adapter exception.
- Move generic test write behavior behind `seed_run` and `reset_test_rows` into
  `core/application/testing/test_harness_service.py`.
- Keep `submit_cohort` as a REST test-harness entry point, but delegate its
  legacy cohort and `BenchmarkDefinitionRecord` marker writes to
  `core/application/compat/cohorts.py`.
- Move legacy cohort marker writes from the test harness into
  `core/application/compat/cohorts.py::write_legacy_cohort_marker`.
- Fix the existing `slug_by_node_id` typo while moving `read_run_state`: the
  local map is named `slug_by_task_id`, and graph mutation/evaluation/execution
  mapping should use task ids consistently.
- Leave `core/infrastructure/http/routes/test_harness.py` as HTTP translation
  over those application services and views.

### Route Boundary Tests

- Add an architecture test that route modules may import application services,
  application views, FastAPI, and shared settings, but not SQLModel table
  classes directly.
- Exempt `core/infrastructure/http/app.py` from that import rule and document
  it as the REST bootstrap/composition root.
- Add an architecture test that top-level `core/rest_api` does not exist after
  the move.

## Non-Goals

- Do not change public REST paths in this slice.
- Do not remove cohort endpoints until the cohort deprecation PRD lands.
- Do not merge REST routes into application packages.

## Acceptance Criteria

- REST route functions are thin enough to read as translation code.
- Route modules depend on application services and views, not low-level
  table models.
- No top-level `core/rest_api` package remains.
- HTTP tests continue to pass without behavior changes.
- Architecture tests distinguish REST inbound adapters from application logic.

## Evidence

- [`../audits/infrastructure-application-boundary-audit.md`](../audits/infrastructure-application-boundary-audit.md)
- [`../audits/schema-concept-debt-audit.md`](../audits/schema-concept-debt-audit.md)
