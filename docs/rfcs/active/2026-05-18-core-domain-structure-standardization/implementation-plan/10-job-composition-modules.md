# PR 10: Job Composition Modules

## What

Merge split `application/jobs/*` and `infrastructure/inngest/handlers/*` into
job-local `core/jobs/<domain>/<job>/` modules with `contract.py`, `job.py`, and
`inngest.py`.

## Why

Each event job is currently spread across application functions, shared model
catch-alls, event contract files, and Inngest handler files. That hides the
unit of behavior and weakens dependency direction. A job-local module gives a
reader the wire contract, composition logic, and framework wrapper in one
folder while still keeping business services below the job layer.

## How

- Create `core/jobs/`.
- Move each application job and matching Inngest handler into the semantic job
  package listed in PRD 08.
- Split `application/jobs/models.py` into local job `contract.py` files.
- Move job-specific event contracts out of
  `application/events/task_events.py` and
  `application/events/infrastructure_events.py`.
- Keep event names, function ids, retry config, and cancellation rules stable.
- Make `job.py` accept concrete infrastructure through ports or explicit
  adapter parameters.
- Make `inngest.py` the only place in the job package that imports Inngest and
  concrete infrastructure implementations.

## Plan

1. Add architecture tests for `core/jobs/**/contract.py`,
   `core/jobs/**/job.py`, and `core/jobs/**/inngest.py`.
2. Add a registry test that all previous Inngest function ids and event names
   are still registered.
3. Move one low-risk job first, such as `run_cleanup`, to prove the pattern.
4. Move workflow jobs: start, complete, fail.
5. Move task jobs: execute, propagate, evaluate, cleanup cancelled, cancel
   orphans.
6. Move sandbox jobs: setup and cleanup.
7. Move resource persist-output job.
8. Split job models into local contracts as each job moves.
9. Update registry imports.
10. Delete `application/jobs/`, `application/jobs/models.py`, and
    `infrastructure/inngest/handlers/`.

## Acceptance Criteria

- Each job folder contains `contract.py`, `job.py`, and `inngest.py`.
- `application/jobs/` is gone.
- `infrastructure/inngest/handlers/` is gone.
- `application/jobs/models.py` is gone.
- Event names, function ids, retries, and cancellation semantics are stable.
- `contract.py` files have no infrastructure/persistence/service imports.
- `job.py` files have no concrete infrastructure imports.
- `inngest.py` files contain no SQLModel queries or business decisions.

## Tests

```bash
pytest ergon_core/tests/unit/inngest -q
pytest ergon_core/tests/unit/runtime -q
pytest ergon_core/tests/smoke -q
pytest ergon_core/tests/unit/architecture -q
rg -n "core\\.application\\.jobs|application/jobs|infrastructure/inngest/handlers|application\\.events\\.task_events|application\\.events\\.infrastructure_events" ergon_core tests
```

