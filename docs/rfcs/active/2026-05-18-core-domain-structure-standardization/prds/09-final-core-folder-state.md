# PRD 09: Final Core Folder State

## Goal

Define the intended `ergon_core.core` package layout after the core refactor so
the implementation stack has a concrete architectural acceptance target.

This document is not another refactor slice. It is the final-state map that
PRDs 01-08 should converge on.

## Final Top-Level Shape

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

Deleted top-level packages:

- `domain/`

Top-level packages that must not exist after the refactor:

- `application/jobs/`
- `application/read_models/`
- `application/graph/`
- `application/tasks/`
- `application/workflows/`
- `infrastructure/inngest/handlers/`
- `rest_api/`

## Final Package Responsibilities

### `application/`

Owns business use cases, runtime services, ports, and compatibility modules.

```text
application/
  communication/
  compat/
    cohorts.py
    legacy_experiments.py
  context/
  evaluation/
    dto_mapping.py
    models.py
    scoring.py
    service.py
    summary.py
  experiments/
  ports/
    dashboard.py
    resources.py
    sandbox.py
  resources/
    errors.py
    models.py
    publishing.py
    repository.py
  runtime/
    errors.py
    events.py
    graph_repository.py
    graph_traversal.py
    lifecycle.py
    models.py
    resources.py
    run_identity.py
    run_lifecycle.py
    status.py
    task_cleanup.py
    task_execution.py
    task_execution_repository.py
    task_inspection.py
    task_management.py
```

Deleted from `application/`:

- `jobs/`
- `read_models/`
- `graph/`
- `tasks/`
- `workflows/`

Rules:

- `application/runtime/*` owns run graph lifecycle, task lifecycle, propagation,
  dynamic task mutation, execution row writes, and runtime resource views.
- `application/ports/*` declares external effects needed by application or
  jobs; it does not import concrete infrastructure.
- `application/compat/*` is explicitly temporary and may reference deprecated
  tables while PRD 07 is open.
- `application/evaluation/*` owns evaluation semantics and summary DTO mapping.

### `views/`

Owns read-only contract builders for REST/dashboard/API consumers.

```text
views/
  errors.py
  resources.py
  compat/
    cohorts.py
  dashboard_events/
    contracts.py
    context_events.py
    graph_mutations.py
    cohorts.py
  experiments/
    models.py
    service.py
  runs/
    graph_tasks.py
    models.py
    service.py
    snapshot.py
  training.py
```

Rules:

- View modules may read persistence rows.
- View modules must not mutate runtime state.
- View modules must not start jobs.
- `views/compat/cohorts.py` exists only while frontend cohort surfaces
  remain.
- `views/training.py` exists only if PRD 01 keeps training observability
  and identifies/adds a real writer.

### `jobs/`

Owns event-local composition modules.

```text
jobs/
  base.py
  workflow/
    start/
      contract.py
      job.py
      inngest.py
    complete/
      contract.py
      job.py
      inngest.py
    fail/
      contract.py
      job.py
      inngest.py
  task/
    execute/
      contract.py
      job.py
      inngest.py
    propagate/
      contract.py
      job.py
      inngest.py
    evaluate/
      contract.py
      job.py
      inngest.py
    cleanup_cancelled/
      contract.py
      job.py
      inngest.py
    cancel_orphans/
      contract.py
      job.py
      inngest.py
  sandbox/
    setup/
      contract.py
      job.py
      inngest.py
    cleanup/
      contract.py
      job.py
      inngest.py
  resources/
    persist_outputs/
      contract.py
      job.py
      inngest.py
  run/
    cleanup/
      contract.py
      job.py
      inngest.py
```

Rules:

- `contract.py` contains event wire contracts and local result DTOs only.
- `job.py` composes application services, views, and ports and must not import
  concrete infrastructure.
- `inngest.py` registers the Inngest function and wires concrete
  infrastructure implementations into `job.py`.
- Runtime/application services must not import `core.jobs`.

### `infrastructure/`

Owns external/framework adapters and process/bootstrap wiring.

```text
infrastructure/
  dashboard/
    emitter.py
    provider.py
  http/
    app.py
    routes/
      experiments.py
      rollouts.py
      runs.py
      test_harness.py
  inngest/
    client.py
    registry.py
  sandbox/
    blob_store.py
    event_sink.py
    file_reader.py
    manager.py
  tracing/
    contexts.py
    ids.py
    otel.py
    sink.py
    types.py
```

Deleted from `infrastructure/`:

- `inngest/handlers/`
- `dashboard/event_contracts.py`

Rules:

- Infrastructure may implement application ports.
- Infrastructure must not own view builders, business rules, runtime lifecycle,
  cohort recomputation, or resource append/dedup policy.
- Inngest registration lives in `core/jobs/**/inngest.py`, not in
  `infrastructure/inngest/handlers`.
- `infrastructure/http/` owns REST translation and FastAPI composition; it
  must call application services and views instead of defining product logic.

### `persistence/`

Owns SQLModel tables, database setup, migrations-facing models, storage-safe
enums/types, and low-level JSON validation.

```text
persistence/
  context/
    models.py
  definitions/
    models.py
  graph/
    models.py
  shared/
    db.py
    enums.py
    ids.py
    types.py
  telemetry/
    models.py
```

Deleted from `persistence/`:

- `components/`
- `imports/`
- `saved_specs/`
- `context/event_payloads.py`
- `graph/status_conventions.py`
- `telemetry/repository.py`
- `telemetry/evaluation_summary.py`

Rules:

- Persistence must not define application command DTOs.
- Persistence must not define runtime lifecycle policy.
- Persistence must not import concrete infrastructure.
- Persistence must not own compatibility services.

### `shared/`

Owns narrow cross-cutting contracts and utilities.

```text
shared/
  context_parts.py
  json_types.py
  rollout_status.py
  settings.py
  utils.py
```

Rules:

- Shared is not a junk drawer.
- Shared schemas must be used by multiple real layers.
- `ContextEventPayload` and `WorkerYield` do not exist; consumers use
  `ContextPartChunkLog` and `ContextPartChunk` directly.

### `rl/`

Owns RL/rollout control-plane logic that is not general runtime application
behavior.

```text
rl/
  eval_runner.py
  extraction.py
  rollout_service.py
  rollout_types.py
  vllm_manager.py
```

Rules:

- RL rollout provenance uses `RolloutBatch` and canonical `RunRecord.definition_id`.
- RL must not write `BenchmarkDefinitionRecord`.
- RL may read shared context/evaluation contracts through their final homes.

## Architecture Test Acceptance Criteria

Add or update tests that assert:

- `core/domain` does not exist.
- `core/application/jobs`, `core/application/read_models`,
  `core/application/graph`, `core/application/tasks`, and
  `core/application/workflows` do not exist.
- `core/infrastructure/inngest/handlers` does not exist.
- `core/infrastructure/dashboard/event_contracts.py` does not exist.
- `core/rest_api` does not exist.
- `core/infrastructure/http/app.py` exists as the FastAPI composition root.
- `core/infrastructure/http/routes/*` imports application services and views,
  but not SQLModel table models directly.
- `core/persistence/imports`, `core/persistence/components`,
  `core/persistence/saved_specs`, `core/persistence/context/event_payloads.py`,
  `core/persistence/graph/status_conventions.py`,
  `core/persistence/telemetry/repository.py`, and
  `core/persistence/telemetry/evaluation_summary.py` do not exist.
- `core/jobs/**/contract.py` does not import infrastructure, persistence
  sessions, SQLModel table models, or application services.
- `core/jobs/**/job.py` does not import concrete infrastructure.
- `core/jobs/**/inngest.py` does not query SQLModel tables or import runtime
  repositories directly.
- `core/application/runtime`, `core/application/evaluation`, and
  `core/views` do not import `core.jobs`.
- `core/infrastructure` does not import `core.persistence.telemetry.models`
  except in explicitly approved bootstrap/test helpers.
- `core/persistence` does not import `core.application`, `core.infrastructure`,
  `core.jobs`, or `core.views`.
- `rg -n "ContextEventPayload|WorkerYield|TelemetryRepository|CreateTaskEvaluation"`
  returns no production references.
- `rg -n "BenchmarkDefinitionRecord" ergon_core/ergon_core/core` returns only
  `application/compat/*`, persistence table definitions while the compatibility
  window is open, and tests. After PRD 07, it returns no production references.

## Evidence

- PRDs 01-08 define the source moves/deletions that produce this final state.
- [`../audits/current-structure.md`](../audits/current-structure.md) records
  the current pre-refactor folder shape.
