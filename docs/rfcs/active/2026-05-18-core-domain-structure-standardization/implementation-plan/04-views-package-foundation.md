# PR 04: Views Package Foundation

## What

Replace `application/read_models` with a top-level `core/views` package for
read-only DTO builders and API/dashboard view services.

## Why

`read_models` does not earn a home under `application` because it is neither
command-side use case logic nor persistence. It builds read-only contracts for
REST, dashboard, CLI, and tests. Pulling it into `views/` gives dashboard,
REST, and job composition a stable target before those packages move.

## How

- Create `core/views/`.
- Split `application/read_models/models.py` instead of moving it wholesale.
- Move run snapshot DTOs to `views/runs/models.py`.
- Move `application/read_models/runs.py` to `views/runs/service.py`.
- Move `application/read_models/run_snapshot.py` to
  `views/runs/snapshot.py`.
- Move experiment DTOs/service to `views/experiments/models.py` and
  `views/experiments/service.py`.
- Move `application/read_models/resources.py` to `views/resources.py`.
- Move `application/read_models/errors.py` to `views/errors.py`.
- Leave cohort compatibility split for PR 08 unless needed to unblock imports.
- Move training DTOs only if PR 02 kept training observability.

## Plan

1. Add architecture tests for `core/views`:
   - views may read persistence rows;
   - views must not call `session.add`, `session.commit`, or start jobs;
   - views must not import concrete infrastructure.
2. Create `core/views/__init__.py`, `views/runs/`, and
   `views/experiments/`.
3. Move run DTOs and update imports in REST routes, dashboard code, and tests.
4. Move run read service and snapshot builder.
5. Move experiment DTOs and read service.
6. Move resource DTO/read helpers.
7. Move read-model errors.
8. Update import-boundary tests and model field description tests.
9. Delete `application/read_models` files that are fully migrated.
10. Leave an explicit failure if `application/read_models` still contains only
    cohort compatibility that PR 08 owns.

## Acceptance Criteria

- Normal run, experiment, resource, and error views import from `core.views`.
- `application/read_models/models.py`, `runs.py`, `run_snapshot.py`,
  `experiments.py`, `resources.py`, and `errors.py` are gone.
- View modules are read-only by architecture test.
- REST/dashboard consumers use the new imports.
- Cohort compatibility is either still clearly isolated for PR 08 or already
  moved into `views/compat` and `application/compat`.

## Tests

```bash
pytest ergon_core/tests/unit/read_models -q
pytest ergon_core/tests/unit/runtime -q
pytest ergon_core/tests/unit/dashboard -q
pytest ergon_core/tests/unit/architecture -q
rg -n "application\\.read_models\\.(models|runs|run_snapshot|experiments|resources|errors)" ergon_core tests
rg -n "session\\.add\\(|session\\.commit\\(" ergon_core/ergon_core/core/views
```

