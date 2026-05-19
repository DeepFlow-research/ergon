# PR 06: REST HTTP Adapter Boundary

## What

Move top-level `core/rest_api` into `core/infrastructure/http` and keep route
modules as thin HTTP adapters over application services and views.

## Why

REST is framework glue, not a core domain. Keeping it top-level makes it look
like application logic and lets route-local test harness and cohort behavior
leak into product concepts. This PR makes HTTP routing an infrastructure
adapter while preserving public REST paths.

## How

- Move:
  - `core/rest_api/app.py` -> `core/infrastructure/http/app.py`
  - `core/rest_api/runs.py` -> `core/infrastructure/http/routes/runs.py`
  - `core/rest_api/experiments.py` ->
    `core/infrastructure/http/routes/experiments.py`
  - `core/rest_api/rollouts.py` ->
    `core/infrastructure/http/routes/rollouts.py`
  - `core/rest_api/test_harness.py` ->
    `core/infrastructure/http/routes/test_harness.py`
  - `core/rest_api/cohorts.py` ->
    `core/infrastructure/http/routes/cohorts.py` temporarily for PR 08/09.
- Keep route-local `Test*Dto` classes in the test harness route module.
- Move reusable test writes into
  `core/application/testing/test_harness_service.py`.
- Move legacy cohort marker writes into
  `core/application/compat/cohorts.py`.
- Update imports in app startup, tests, scripts, and dashboard proxy tests.

## Plan

1. Add an architecture test that final route modules may import FastAPI,
   shared settings, application services, and views, but not SQLModel table
   classes directly.
2. Add an architecture test that `core/rest_api` does not exist.
3. Add a bootstrap exception test/docstring for
   `core/infrastructure/http/app.py`.
4. Move app and route modules.
5. Update import paths in tests and startup wiring.
6. Split reusable test harness write behavior into application testing service.
7. Route cohort marker writes through compatibility helpers.
8. Fix the `slug_by_node_id` typo in test harness read-state mapping while the
   file is touched.
9. Delete top-level `core/rest_api`.

## Acceptance Criteria

- No top-level `core/rest_api` package remains.
- Public REST paths do not change.
- Route modules are thin translation code.
- Route modules depend on application services and views, not low-level table
  models.
- Test harness DTOs remain route-local.
- Reusable test writes live in application testing/compat helpers.

## Tests

```bash
pytest ergon_core/tests/unit/rest_api -q
pytest ergon_core/tests/unit/architecture -q
pytest ergon-dashboard/tests -q
rg -n "core\\.rest_api|ergon_core\\.core\\.rest_api" ergon_core ergon-dashboard tests
```

