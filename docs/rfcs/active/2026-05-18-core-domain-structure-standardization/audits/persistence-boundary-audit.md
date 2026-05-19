# Persistence Boundary Audit

Date: 2026-05-18

Audited against PR 16 head in the main checkout.

## Summary

`core/persistence` earns its keep as a separate layer, but not as a product
domain. It should remain the storage schema and concrete data-access boundary:
SQLModel table models, database session setup, storage enums/types, migrations,
and low-level row validation belong here.

It should not become the owner of runtime/business behavior. Application should
own use cases, views, command models, and repository interfaces/semantics.
Persistence can implement concrete row access, but it should not quietly define
alternate business APIs beside application repositories.

The current split is close enough to preserve, but uneven:

- most persistence files are table definitions and JSON column accessors;
- `application/graph/repository.py`, `application/tasks/repository.py`, and
  `application/resources/repository.py` contain the real application-facing
  repository semantics;
- `persistence/telemetry/repository.py` is a second repository style; PRD 01
  deletes it and folds its two single-consumer methods into
  `EvaluationService`;
- `persistence/graph/status_conventions.py` contains runtime lifecycle
  vocabulary and helper functions, which is application/runtime policy rather
  than storage schema;
- `persistence/context/event_payloads.py` duplicates context-part aliases and
  already has a TODO saying to remove it;
- `persistence/telemetry/models.py` is a large mixed schema module covering
  runs, old benchmark definition records, cohorts, communication, training,
  rollout batches, resources, evaluations, and sandbox WAL rows.

## What Lives In Persistence Today

### `persistence/definitions`

This package stores immutable authored definition tables:

- `ExperimentDefinition`;
- `ExperimentDefinitionWorker`;
- `ExperimentDefinitionEvaluator`;
- `ExperimentDefinitionInstance`;
- `ExperimentDefinitionTask`;
- definition task dependencies, assignments, and evaluator bindings.

This is the right kind of persistence package. It is table/schema heavy, with
light JSON accessors for storage fields. The main architectural drift is
historical naming: v2 says `definition`, while table classes still carry
`ExperimentDefinition*`. That is not an immediate duplication bug, but it
should be reconciled with the planned `application/definitions` naming.

There is one known schema duplication: `ExperimentDefinitionTask` stores both
`task_payload_json` and full object-bound `task_json`. That mirrors the v2 stack
history. The audit does not propose deleting it in this RFC, but the ownership
should be explicit: if `task_json` is the canonical authored task snapshot,
payload-specific readers should not become a second authoring path.

### `persistence/graph`

This package stores run-tier graph tables:

- `RunGraphNode`;
- `RunGraphEdge`;
- `RunGraphAnnotation`;
- `RunGraphMutation`.

The SQLModel table definitions belong in persistence. The append-only mutation
and annotation rows are storage primitives that application graph services can
use for audit/replay.

The questionable file is `status_conventions.py`. It defines `PENDING`,
`READY`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `BLOCKED`,
`TERMINAL_STATUSES`, and helper functions such as
`is_terminal_node_status()`. Those names describe runtime lifecycle policy, not
database storage. Application services already import these conventions as
runtime vocabulary. PRD 01 moves them to
`application/runtime/status.py`, where runtime services and view schemas
can share one vocabulary without persistence owning lifecycle policy.

### `persistence/telemetry`

This is the broadest package. It currently contains:

- launch/provenance rows: `BenchmarkDefinitionRecord`, `RunRecord`;
- task execution rows: `RunTaskExecution`;
- resource rows: `RunResource`;
- evaluation rows: `RunTaskEvaluation`;
- deprecated cohort rows: `ExperimentCohort`, `ExperimentCohortStats`;
- communication rows: `Thread`, `ThreadMessage`;
- training and rollout rows: `TrainingSession`, `TrainingMetric`,
  `RolloutBatch`, `RolloutBatchRun`;
- sandbox observability rows: `SandboxCommandWalEntry`, `SandboxEvent`;
- `TelemetryRepository` for evaluation row reads/writes;
- `EvaluationSummary` JSON schema for `RunTaskEvaluation.summary_json`.

The table models belong in persistence, but the package is too semantically
wide to read as one coherent domain. It is really "run telemetry and auxiliary
run-adjacent tables." That is acceptable as a storage grouping, but application
should not treat `persistence.telemetry` as one product domain.

The duplicated repository shape is `TelemetryRepository`. Application already
has domain-specific repositories:

- `application/graph/repository.py`;
- `application/tasks/repository.py`;
- `application/resources/repository.py`.

Evaluation persistence should not create another repository for two
single-consumer methods. PRD 01 deletes `TelemetryRepository`, folds
`get_task_evaluations()` and `create_task_evaluation()` into private
`EvaluationService` helpers, and keeps only table models under persistence.

`CreateTaskEvaluation` is also an application command object living inside a
persistence model module. PRD 01 deletes it because it only exists to shuttle
arguments into the single-consumer repository. Persistence table modules may
expose row constructors or JSON validators, but command DTOs do not belong
there.

`EvaluationSummary` is a harder call. It is the canonical JSON schema for a
persisted evaluation summary, but it imports public API criterion evidence.
That makes persistence depend upward into the public API. A better target is:

```text
application/evaluation/summary.py
```

or, if it must be shared by API, persistence, views, and dashboard:

```text
core/shared/evaluation_summary.py
```

Persistence can then validate `summary_json` against that shared/application
schema without owning evaluation semantics.

### `persistence/context`

This stores context stream rows:

- `RunContextEvent`;
- context event payload aliases.

`RunContextEvent` belongs in persistence as a SQLModel table. But
`event_payloads.py` duplicates aliases over `ContextPartChunkLog`, and the file
already says it should be killed. Once `core/domain/generation/context_parts.py`
moves to `core/shared/context_parts.py`, this package should import that shared
contract directly. `ContextEventPayload` should not survive the move; consumers
should annotate payloads as `ContextPartChunkLog`.

### `persistence/imports`

This package contains reducer/drop-manifest storage:

- `RunReducer`;
- `RunReducerFootprint`;
- `RunDropsManifest`.

These look like storage rows for imported/public rollout cards and reducer
provenance, but no production writer/reader remains in v2 and
`RunReducer.node_id` points at a non-existent graph column. PRD 01 deletes the
package rather than renaming it.

### `persistence/shared`

This package owns database/session helpers and storage-level shared types:

- `db.py`;
- `enums.py`;
- `ids.py`;
- `types.py`.

This is useful, but `enums.py` mixes storage enums with product/runtime enums:
`RunStatus`, `TaskExecutionStatus`, `TrainingStatus`, and `RunResourceKind`.
Some of these are persisted values and therefore need stable storage names.
However, when application services use them as lifecycle policy, the source of
truth should move to application/shared contracts and persistence should import
the storage-safe enum rather than own the product concept by default.

## Where Duplication Exists

### Repository Ownership

There are two repository styles:

1. persistence-level `TelemetryRepository`;
2. application-level repositories for graph, task execution, worker output, and
   resources.

The application-level style is the better target. It gives the repository a
business-facing name and lets the service own invariants. Persistence should
provide row models and perhaps low-level storage adapters, not a generic
telemetry repository with command DTOs.

Recommendation resolved in PRD 01: delete
`persistence/telemetry/repository.py`, inline its two methods as private
`EvaluationService` helpers, delete `CreateTaskEvaluation`, and keep
`RunTaskEvaluation` as the storage table.

### Direct SQL In Application Services

Many application services and views directly import SQLModel rows and run
queries. That is not automatically wrong in this codebase: views need
query composition, and repository extraction has not been standardized yet.
But it means persistence is already not the sole data-access domain.

The target should be pragmatic:

- command-side mutations should go through application repositories/services;
- views may run direct optimized reads if they remain read-only and
  contract-focused;
- infrastructure should not run product queries when an application
  service/view already exists.

This matches the earlier infrastructure rule: do not duplicate application
operations in adapters.

### Status And Lifecycle Vocabulary

`persistence/graph/status_conventions.py` is used as runtime status vocabulary.
That keeps constants near the table but makes persistence look like it owns
lifecycle semantics. The runtime merge/refactor should move these constants to
the application runtime domain or a narrow shared runtime contract.

Until that happens, do not create another status vocabulary elsewhere. The bug
would be having both `persistence.graph.status_conventions` and
`application.runtime.status` diverge. Move once, then update imports.

### Evaluation Summary Schema

`persistence/telemetry/evaluation_summary.py` is intentionally the canonical
schema for persisted evaluation summaries, but it is not purely persistence.
It describes evaluator/criterion output semantics and imports
`ergon_core.api.criterion.CriterionEvidence`.

Recommendation: make evaluation summary a shared/application evaluation
contract, then have persistence table models validate against it. Do not leave
the canonical evaluator result schema hidden in a storage package if dashboard,
API, and evaluator services all depend on it.

### Context Payload Aliases

`persistence/context/event_payloads.py` duplicates context stream type aliases
over `ContextPartChunkLog`. PRD 02 deletes the alias file, moves
`ContextEventType` to `core/shared/context_parts.py`, and updates consumers to
use `ContextPartChunkLog` directly.

### Deprecated Cohorts And Legacy Definition Records

`BenchmarkDefinitionRecord`, `ExperimentCohort`, and `ExperimentCohortStats`
are still table models. They should remain in persistence while rows exist and
dashboard compatibility needs them. But application should mark their services
as deprecated compatibility, not let telemetry persistence imply they are
first-class v2 domains.

## Does Persistence Earn Its Keep?

Yes, as a layer. No, as an independent product domain.

It earns its keep because:

- the storage schema is large and materially different from application DTOs;
- SQLModel table definitions, foreign keys, JSON columns, and timestamp/default
  mechanics need one obvious home;
- migrations and final schema audits need a stable package to inspect;
- storage-level row validation should be close to the row definitions.

It should remain separate from application because application code should not
be cluttered with table declarations and SQLAlchemy column mechanics.

But it should be kept intentionally narrow:

- persistence owns tables, storage enums/types, low-level row validation, and
  database setup;
- application owns command models, use-case services, lifecycle policy,
  view assembly, and application-facing repositories;
- infrastructure owns external adapters and implements application-declared
  ports;
- rest/api/dashboard should consume application services and views, not
  persistence rows directly except in explicit view modules.

## Recommended Target Shape

```text
persistence/
  definitions/
    models.py
  graph/
    models.py
  telemetry/
    models.py          # or split into run/models.py, evaluation/models.py, etc. later
  context/
    models.py
  shared/
    db.py
    ids.py
    types.py

application/
  definitions/
    repository.py
  runtime/
    status.py          # moved from persistence.graph.status_conventions
    graph_repository.py
  evaluation/
    repository.py      # replaces persistence.telemetry.repository
    summary.py         # or shared/evaluation_summary.py
  resources/
    repository.py
  communication/
    repository.py      # if communication service keeps growing direct SQL
  views/
    ...
```

This does not require an immediate large move. The first useful cleanup is to
set the rule and stop adding new repositories or command DTOs under
`persistence`.

## Suggested PR Slices

### PR A: Persistence Ownership Tests

Add import-boundary tests that encode the intended split:

- `persistence/*/models.py` may import `shared` and storage-safe schemas;
- persistence table modules should not import concrete infrastructure;
- persistence should not define new application command DTOs;
- infrastructure should not query persistence rows directly when application
  services and views exist.

This PR can also delete the empty/stale `persistence/components` package if it
is tracked and unused.

### PR B: Evaluation Repository And Summary Boundary

Delete `TelemetryRepository` and `CreateTaskEvaluation`. Move `EvaluationSummary`,
`CriterionOutcomeEntry`, and `EvalCriterionStatus` to
`application/evaluation/summary.py`, and delete
`RunTaskEvaluation.parsed_summary()` so persistence no longer imports the
semantic evaluation schema.

### PR C: Runtime Status Boundary

Move `persistence/graph/status_conventions.py` to
`application/runtime/status.py`. Update imports in graph services, task
services, jobs, views, dashboard contracts, fixtures, and tests in one
slice.

### PR D: Context Payload Alias Deletion

After context parts move to `core/shared/context_parts.py`, remove
`persistence/context/event_payloads.py` unless a DB-specific event payload type
is still needed. Update dashboard contracts and read models to import the
shared context stream contracts directly.

### PR E: Telemetry Model Split Or Documentation

Do not split `persistence/telemetry/models.py` just for tidiness. First decide
whether cohorts, training, rollout batches, sandbox WAL, communication, and
run/task/evaluation/resource tables are all still active v2 storage. If they
are, either document `telemetry` as "run-adjacent storage" or split it into
subpackages by storage family. If some are deprecated, mark those rows and their
application services as compatibility-only until deleted.
