---
status: active
opened: 2026-05-18
author: charlie + agent
architecture_refs:
  - ../../../architecture/01_public_api.md
  - ../../../architecture/02_runtime_lifecycle.md
  - ../../../architecture/04_persistence.md
supersedes: []
superseded_by: null
---

# RFC: Core Domain Structure Standardization

## Purpose

This RFC records the target architecture for cleaning up
`ergon_core.core` after the v2 authoring/runtime stack landed.

Earlier versions of this folder included speculative option documents. Those
have been replaced with concrete PRDs plus audit evidence. The implementation
direction is now settled enough that the next step should be writing executable
PR plans from these PRDs.

## Problem

`ergon_core.core` has the right high-level layers, but the boundaries are
currently uneven:

- `persistence/` contains table models, but also some application command DTOs,
  repositories, lifecycle vocabulary, and compatibility schemas.
- `domain/` is nominal and does not contain real domain behavior.
- `infrastructure/` sometimes owns application behavior such as dashboard
  view assembly, cohort recomputation, and resource append policy.
- REST should be a thin inbound adapter under `infrastructure/http/`, but
  needs boundary enforcement.
- `application/` contains most real behavior, but runtime logic is split across
  `tasks`, `workflows`, and `graph`; view-building logic is mixed with
  command-side services and deprecated cohort compatibility.

## Target Direction

Use a layered, port-and-adapter shape:

```text
inbound adapters -> application use cases / views
application use cases -> application ports -> infrastructure implementations
```

Ownership rules:

- Application services own use cases and invariants.
- Application should not depend on concrete infrastructure. Where a use case
  needs an external system, application declares a narrow port/protocol and the
  composition root injects an implementation.
- Persistence owns SQLModel tables, database/session setup, storage-safe types,
  and low-level row validation.
- Persistence should not define application command DTOs, domain repositories,
  runtime lifecycle policy, or compatibility services.
- Infrastructure owns external adapters and framework glue. It may implement
  application ports, but it should not own business rules, views, or
  persistence semantics that already exist in application.
- HTTP adapters own REST translation only.
- Inngest handlers are thin framework adapters into application jobs/use cases.
- Views own read-only contract builders and must not mutate runtime state.
- If a duplicate operation appears outside application, first check whether
  application already owns that operation shape. Reuse or extract that logic
  instead of reimplementing it under a tidier path.

## PRDs

The PRDs are ordered by recommended implementation sequence.

0. [`prds/00-move-vs-delete-decisions.md`](prds/00-move-vs-delete-decisions.md)
   records the scrutiny pass for moved schemas/repositories: which ones are
   real contracts, which ones should be merged, and which ones should die.
1. [`prds/01-persistence-schema-boundary.md`](prds/01-persistence-schema-boundary.md)
   makes persistence a true storage-definition layer and fixes schema concept
   debt.
2. [`prds/02-shared-context-contract.md`](prds/02-shared-context-contract.md)
   deletes the anemic `domain/` package by moving context stream schemas to
   `core/shared/context_parts.py`.
3. [`prds/03-infrastructure-adapter-boundary.md`](prds/03-infrastructure-adapter-boundary.md)
   makes dashboard, sandbox, Inngest, and tracing true adapters.
4. [`prds/04-rest-inbound-adapter-boundary.md`](prds/04-rest-inbound-adapter-boundary.md)
   moves REST under `infrastructure/http/` as a thin inbound adapter instead
   of application logic.
5. [`prds/05-application-runtime-restructure.md`](prds/05-application-runtime-restructure.md)
   consolidates duplicated runtime lifecycle behavior across tasks, workflows,
   and graph.
6. [`prds/06-views-dashboard-contracts.md`](prds/06-views-dashboard-contracts.md)
   replaces loose read models with a stricter view/dashboard-contract
   boundary.
7. [`prds/07-deprecated-cohorts-legacy-experiments.md`](prds/07-deprecated-cohorts-legacy-experiments.md)
   isolates and removes cohort and legacy experiment-record compatibility.
8. [`prds/08-job-composition-modules.md`](prds/08-job-composition-modules.md)
   promotes jobs into semantic composition modules so Inngest handlers stay
   thin and application use cases can receive infrastructure implementations
   through ports.
9. [`prds/09-final-core-folder-state.md`](prds/09-final-core-folder-state.md)
   defines the final `ergon_core.core` package layout and architecture-test
   acceptance criteria for the full refactor.
10. [`prds/10-application-domain-layout-convention.md`](prds/10-application-domain-layout-convention.md)
    defines the post-stack convention for application domain folders, public
    facades, temporary characterization tests, and permanent import-boundary
    tests.

## Implementation Plan

The engineering PR stack lives in
[`implementation-plan/00-program.md`](implementation-plan/00-program.md).
Each PR plan is intentionally separate from the PRDs and includes the "what",
"why", "how", planned implementation steps, acceptance criteria, and test gates
for that slice.

## Evidence

The audit documents are evidence for the PRDs. They are not implementation
plans and should not be treated as competing options.

- [`audits/current-structure.md`](audits/current-structure.md): current package
  map and boundary overview.
- [`audits/runtime-domain-merge-audit.md`](audits/runtime-domain-merge-audit.md):
  evidence for merging or standardizing runtime domains.
- [`audits/infrastructure-application-boundary-audit.md`](audits/infrastructure-application-boundary-audit.md):
  dashboard/sandbox/Inngest/tracing duplication audit.
- [`audits/persistence-boundary-audit.md`](audits/persistence-boundary-audit.md):
  persistence-layer ownership audit.
- [`audits/schema-concept-debt-audit.md`](audits/schema-concept-debt-audit.md):
  deprecated tables, duplicated identity fields, stale columns, and schema
  concept debt.

## Recommended Order Of Operations

### 1. Persistence And Schema Concepts

Clean persistence first because it is the foundation for every other boundary:

- move application concepts out of persistence;
- fix stale schema references;
- route compatibility-only tables through named `application/compat/*` modules;
- enforce the boundary with tests.

### 2. Shared Context Contract

Delete `domain/` as a quick win by moving the context stream schemas to
`core/shared/context_parts.py`.

### 3. Infrastructure Adapters

Clean up dashboard, sandbox, Inngest, and tracing after persistence and shared
contracts are clearer.

### 4. REST Inbound Adapter

Move REST route modules under `infrastructure/http/` as thin translators into
application services and views. Do not move route logic into application
packages.

### 5. Application Restructure

Only after the outer boundaries stop leaking, bite off the larger application
deduplication work: runtime domain consolidation, views, dashboard
contracts, job composition modules, and deprecated cohort/legacy experiment
removal.

## Implementation Notes

- Each PRD should become one or more small implementation plans before code
  changes begin.
- Every implementation plan should include characterization tests before moves,
  import-boundary tests after moves, and explicit grep checks for deleted
  compatibility paths.
- Behavior changes should be isolated from mechanical package moves whenever
  possible.
- Compatibility-only concepts must be named as such in code while they remain.

## On Acceptance

When this RFC is accepted:

- write executable PR plans for the PRDs in order;
- update `docs/architecture/*` with the accepted ownership rules;
- add or update architecture tests that enforce the new package boundaries.
