# PR 12: Final Folder State And Architecture Gates

## What

Enforce the final `ergon_core.core` package layout with architecture tests,
delete remaining shims, and update architecture/RFC documentation to match the
landed code.

## Why

The prior PRs do the actual cleanup. The final PR prevents quiet regression:
old package roots should not come back, shared contracts should not become a
junk drawer, persistence should not regain application semantics, and jobs
should not absorb reusable business logic.

## How

- Add final folder-state tests from PRD 09.
- Delete any temporary import shims left by earlier PRs.
- Update `docs/architecture/*` to describe the accepted ownership rules.
- Update this RFC to mark the implementation-plan stack as landed.
- Add source checks for deleted aliases, repositories, and compatibility types.

## Plan

1. Add or update tests asserting these packages do not exist:
   - `core/domain`
   - `core/rest_api`
   - `core/application/jobs`
   - `core/application/read_models`
   - `core/application/graph`
   - `core/application/tasks`
   - `core/application/workflows`
   - `core/infrastructure/inngest/handlers`
2. Add tests asserting these final homes exist:
   - `core/application/runtime`
   - `core/views`
   - `core/jobs`
   - `core/infrastructure/http`
   - `core/shared/context_parts.py`
3. Add import-boundary tests:
   - persistence does not import application, infrastructure, jobs, or views;
   - runtime/evaluation/views do not import jobs;
   - job contracts do not import services, persistence sessions, or
     infrastructure;
   - job wrappers do not run direct SQLModel queries;
   - infrastructure does not own view builders or resource append policy.
4. Add source checks for:
   - `ContextEventPayload`
   - `WorkerYield`
   - `TelemetryRepository`
   - `CreateTaskEvaluation`
   - `BenchmarkDefinitionRecord`
   - `ExperimentCohort`
5. Delete remaining import shims.
6. Update architecture docs and RFC status text.

## Acceptance Criteria

- The final top-level shape is exactly:
  `application`, `infrastructure`, `jobs`, `persistence`, `views`, `rl`,
  `shared`.
- Deleted package roots cannot be reintroduced without failing tests.
- Deleted compatibility names have no production references.
- Architecture docs describe the implemented layout.
- Full unit/smoke architecture gates pass.

## Tests

```bash
pytest ergon_core/tests/unit/architecture -q
pytest ergon_core/tests/unit/runtime -q
pytest ergon_core/tests/unit/dashboard -q
pytest ergon_core/tests/unit/persistence -q
pytest ergon_core/tests/smoke -q
rg -n "ContextEventPayload|WorkerYield|TelemetryRepository|CreateTaskEvaluation|BenchmarkDefinitionRecord|ExperimentCohort" ergon_core/ergon_core
find ergon_core/ergon_core/core -maxdepth 2 -type d | sort
```

