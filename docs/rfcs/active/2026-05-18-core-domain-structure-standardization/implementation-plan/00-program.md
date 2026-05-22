# Core Refactor PR Stack

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement each PR plan task-by-task.

## Goal

Turn the core-domain-structure-standardization PRDs into an ordered engineering
stack with reviewable PR boundaries.

## Source PRDs

- `../prds/00-move-vs-delete-decisions.md`
- `../prds/01-persistence-schema-boundary.md`
- `../prds/02-shared-context-contract.md`
- `../prds/03-infrastructure-adapter-boundary.md`
- `../prds/04-rest-inbound-adapter-boundary.md`
- `../prds/05-application-runtime-restructure.md`
- `../prds/06-views-dashboard-contracts.md`
- `../prds/07-deprecated-cohorts-legacy-experiments.md`
- `../prds/08-job-composition-modules.md`
- `../prds/09-final-core-folder-state.md`

## Stack Order

1. [`01-persistence-evaluation-and-status.md`](01-persistence-evaluation-and-status.md)
2. [`02-persistence-schema-concept-cleanup.md`](02-persistence-schema-concept-cleanup.md)
3. [`03-shared-context-and-domain-deletion.md`](03-shared-context-and-domain-deletion.md)
4. [`04-views-package-foundation.md`](04-views-package-foundation.md)
5. [`05-dashboard-contracts-and-publisher-port.md`](05-dashboard-contracts-and-publisher-port.md)
6. [`06-rest-http-adapter-boundary.md`](06-rest-http-adapter-boundary.md)
7. [`07-sandbox-resource-publishing-boundary.md`](07-sandbox-resource-publishing-boundary.md)
8. [`08-legacy-experiment-and-cohort-isolation.md`](08-legacy-experiment-and-cohort-isolation.md)
9. [`09-legacy-cohort-and-experiment-deletion.md`](09-legacy-cohort-and-experiment-deletion.md)
10. [`10-job-composition-modules.md`](10-job-composition-modules.md)
11. [`11-application-runtime-restructure.md`](11-application-runtime-restructure.md)
12. [`12-final-folder-state-and-architecture-gates.md`](12-final-folder-state-and-architecture-gates.md)

## Coverage Matrix

| PR | Primary PRDs Covered | Notes |
| --- | --- | --- |
| PR 01 | PRD 00, PRD 01, PRD 09 | Evaluation repository deletion, evaluation summary move, runtime status move. |
| PR 02 | PRD 00, PRD 01, PRD 07 | Dead import tables, run identity, training gate, rollout status, compatibility table isolation foundations. |
| PR 03 | PRD 00, PRD 02, PRD 09 | Shared context contract, alias deletion, `domain/` deletion. |
| PR 04 | PRD 06, PRD 09 | `views/` foundation and `application/read_models` split. |
| PR 05 | PRD 03, PRD 06 | Dashboard contracts, dashboard publisher port, workflow-started snapshot contract. |
| PR 06 | PRD 04, PRD 09 | REST moves under `infrastructure/http`. |
| PR 07 | PRD 03 | Sandbox resource publishing boundary. |
| PR 08 | PRD 07, PRD 01 | Compatibility isolation for cohorts and legacy experiment records. |
| PR 09 | PRD 07, PRD 09 | Cohort and legacy experiment deletion after frontend/CLI/RL replacements. |
| PR 10 | PRD 08, PRD 03, PRD 09 | Job-local composition modules and Inngest handler deletion. |
| PR 11 | PRD 05, PRD 09 | Runtime consolidation under `application/runtime`. |
| PR 12 | PRD 09 | Final architecture gates, docs, and shim deletion. |

## Why This Order

The stack pays down foundations before high-motion package moves. Persistence
cleanup comes first because stale schemas and command DTOs leak into almost
every other boundary. The shared context move comes next because it deletes the
nominal `domain/` package and removes alias debt used by views, dashboard, RL,
and persistence. The `views/` package is then created before dashboard and REST
move toward it. Job composition waits until the ports, views, and HTTP adapter
boundaries exist. The large runtime consolidation comes late, after outer-layer
duplication has stopped pulling runtime code in several directions.

## Stack-Wide Rules

- Each PR should preserve behavior unless its plan explicitly says otherwise.
- Each PR must add or update architecture tests before deleting old homes.
- Compatibility concepts must be named `compat` or `deprecated` while they
  remain.
- Do not leave import shims unless the PR plan explicitly permits a temporary
  shim and names the later PR that deletes it.
- Do not move a schema only because its folder is wrong. First check whether an
  existing view or DTO already expresses the same contract.

## Stack-Wide Test Gates

Run the narrow tests named in each PR plan. Before merging the stack, run:

```bash
pytest ergon_core/tests/unit/architecture -q
pytest ergon_core/tests/unit/runtime -q
pytest ergon_core/tests/unit/dashboard -q
pytest ergon_core/tests/unit/persistence -q
pytest ergon_core/tests/smoke -q
```

If the dashboard contract generator is available in the branch, also run the
schema export/drift check after PRs 05, 06, 09, and 12.

## Final Shape

The stack should converge on:

```text
ergon_core/core/
  application/
  infrastructure/
  jobs/
  persistence/
  views/
  rl/
  shared/
```

No final PR should leave these packages:

- `core/domain`
- `core/rest_api`
- `core/application/jobs`
- `core/application/read_models`
- `core/application/graph`
- `core/application/tasks`
- `core/application/workflows`
- `core/infrastructure/inngest/handlers`
