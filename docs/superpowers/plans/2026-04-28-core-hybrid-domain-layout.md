# Core Hybrid Domain Layout

This documents the implemented hybrid layout for `ergon_core.core`: hard
technical layers stay visible (`rest_api`, `persistence`, `infrastructure`),
while product/application concepts live in explicit clusters under
`core/application`.

The goal is not "everything is domain-first". The goal is that a new contributor
can answer three questions quickly:

1. Where do use cases live?
2. Where do SQL/storage rows live?
3. Where do transport/infrastructure adapters live?

## Implemented Top-Level Shape

```text
ergon_core/ergon_core/core/
  __init__.py

  rest_api/
    # FastAPI / HTTP transport only.
    # Named rest_api to avoid confusion with the public authoring API
    # under ergon_core.api.
    # Should import application services and read models, not own domain logic.
    __init__.py
    app.py
    cohorts.py
    experiments.py
    rollouts.py
    runs.py
    test_harness.py

  application/
    # Product use cases and domain-aware repositories.
    # This replaces the current "runtime as second root" feeling.

    experiments/
      # Define experiments, persist authored definitions, launch experiment runs.
      # Implemented from:
      # - core/definitions/service.py
      # - core/definitions/persistence.py
      # - core/definitions/repository.py
      # - core/definitions/schemas.py
      # - runtime/workflows/launch.py
      __init__.py
      service.py
      models.py
      repository.py
      definition_writer.py
      launch.py

    workflows/
      # Run/workflow lifecycle after a definition exists.
      # Implemented from:
      # - runtime/workflows/service.py
      # - runtime/workflows/orchestration.py
      # - runtime/workflows/runs.py
      # - runtime/workflows/models.py
      # - runtime/workflows/errors.py
      service.py
      orchestration.py
      runs.py
      models.py
      errors.py

    graph/
      # Runtime graph mutations, traversal, lookup, and propagation.
      # Implemented from:
      # - runtime/graph/*
      repository.py
      propagation.py
      traversal.py
      lookup.py
      models.py
      errors.py

    tasks/
      # Task execution lifecycle and task execution repository.
      # Implemented from:
      # - runtime/tasks/*
      __init__.py
      service.py
      execution.py
      management.py
      inspection.py
      cleanup.py
      repository.py
      models.py
      errors.py

    evaluation/
      # Evaluation dispatch, criterion runtime, scoring, persistence use cases.
      # Implemented from:
      # - runtime/evaluation/*
      service.py
      executors.py
      inngest_executor.py
      criterion_runtime.py
      scoring.py
      protocols.py
      models.py
      errors.py

    read_models/
      # Query-side DTO assembly for UI/API surfaces.
      # Implemented from:
      # - runtime/read_models/runs.py
      # - runtime/read_models/run_snapshot.py
      # - runtime/read_models/experiments.py
      # - runtime/read_models/cohorts.py
      # - runtime/read_models/resources.py
      # - runtime/read_models/models.py
      # - runtime/read_models/errors.py
      __init__.py
      runs.py
      run_snapshot.py
      experiments.py
      cohorts.py
      resources.py
      models.py
      errors.py

    communication/
      # Agent-to-agent communication is its own product domain.
      # Do not fold this into run read models.
      # Implemented from:
      # - runtime/read_models/communication.py
      # - relevant communication DTOs currently in runtime/read_models/models.py
      __init__.py
      service.py
      models.py
      errors.py

    context/
      # Worker context event stream and output extraction.
      # Implemented from:
      # - runtime/context_events.py
      # - runtime/output_extraction.py
      __init__.py
      events.py
      output_extraction.py

    jobs/
      # Core semantic workflows currently implemented inside Inngest handlers.
      # These are background job use cases. Inngest should call them, not own
      # their branching, persistence, and orchestration rules.
      # Implemented from:
      # - runtime/inngest/{handler files}.py, after extracting adapter details.
      cancel_orphan_subtasks.py
      check_evaluators.py
      cleanup_cancelled_task.py
      complete_workflow.py
      evaluate_task_run.py
      execute_task.py
      fail_workflow.py
      persist_outputs.py
      propagate_execution.py
      run_cleanup.py
      sandbox_setup.py
      start_workflow.py
      worker_execute.py
      models.py

    resources/
      # Run resource append/query use cases that are not just API presentation.
      # Implemented from:
      # - runtime/resources.py
      # - sandbox/resource_publisher.py may depend on repository here
      __init__.py
      repository.py
      models.py

    events/
      # Product/application event contracts used by jobs, adapters, and
      # dashboard emission. The adapter layer may send these through Inngest,
      # but it should not own their semantic schemas.
      # Implemented from:
      # - runtime/events/*
      __init__.py
      base.py
      task_events.py
      infrastructure_events.py

  domain/
    # Pure-ish domain objects that should not know about DB sessions,
    # Inngest, FastAPI, or dashboard emission.

    experiments/
      # Authoring/composition objects.
      # Implemented from:
      # - core/composition/*
      __init__.py
      experiment.py
      handles.py
      worker_spec.py
      validation.py

    generation/
      # Context stream and generation transcript primitives.
      # Implemented from:
      # - core/generation.py
      context_parts.py

  persistence/
    # SQLModel rows, DB/session helpers, and storage-only repositories.
    # Should not own product workflows or read-model assembly.

    shared/
      db.py
      enums.py
      ids.py
      types.py

    definitions/
      models.py

    telemetry/
      models.py
      repositories.py
      evaluation_summary.py

    graph/
      models.py
      status_conventions.py

    context/
      models.py
      event_payloads.py

    saved_specs/
      models.py

  infrastructure/
    # External adapters and operational plumbing.
    # Infrastructure calls application services; application should not import
    # concrete infrastructure except through deliberate adapter seams.

    inngest/
      # Inngest client, contracts, registry, and thin function adapters.
      # Implemented from:
      # - runtime/inngest/client.py
      # - runtime/inngest/registry.py
      # - runtime/inngest/contracts.py
      # - runtime/inngest/errors.py
      # - runtime/inngest/{handler files}.py after semantic logic moves to
      #   application/jobs.
      client.py
      registry.py
      contracts.py
      errors.py

      handlers/
        cancel_orphan_subtasks.py
        check_evaluators.py
        cleanup_cancelled_task.py
        complete_workflow.py
        evaluate_task_run.py
        execute_task.py
        fail_workflow.py
        persist_outputs.py
        propagate_execution.py
        run_cleanup.py
        sandbox_setup.py
        start_workflow.py
        worker_execute.py

    sandbox/
      # E2B/local sandbox managers and sandbox instrumentation.
      # Implemented from:
      # - core/sandbox/*
      __init__.py
      manager.py
      lifecycle.py
      resource_publisher.py
      instrumentation.py
      event_sink.py
      errors.py
      utils.py

    dashboard/
      # Dashboard event emission/integration.
      # Implemented from:
      # - core/dashboard/*
      __init__.py
      emitter.py
      provider.py
      event_contracts.py

    tracing/
      # Tracing/OpenTelemetry adapters and sinks.
      # Implemented from:
      # - runtime/tracing/*
      __init__.py
      attributes.py
      contexts.py
      ids.py
      noop.py
      otel.py
      sinks.py
      types.py

    dependencies.py

  rl/
    # Keep as a separate bounded context for now.
    # Rollouts, rewards, extraction, checkpointing, and vLLM management cut
    # across product use cases and are closer to training/research machinery
    # than ordinary application services.
    __init__.py
    rollout_service.py
    eval_runner.py
    extraction.py
    rewards.py
    checkpoint.py
    rollout_types.py
    vllm_manager.py

  shared/
    # Small cross-cutting primitives. Keep this boring and sparse.
    json_types.py
    settings.py
    utils.py
```

## Clusters And Ownership Rules

### `core/application`

Application packages own use cases. They can import:

- `core/domain`
- `core/persistence`
- `core/shared`

They should not import:

- `core/rest_api`
- Inngest function modules
- FastAPI router modules

`application` is where the former `runtime` domains landed. The important rename
is conceptual: the old `runtime` package mixed use cases, adapters, and
operational helpers, while `application` now means "use cases over the persisted
product model."

### `core/domain`

Domain packages own objects that should be understandable without infrastructure:

- experiment composition
- worker specs
- definition handles
- context/generation primitives

These modules should not create DB sessions, emit dashboard events, or know about
Inngest. They may validate invariants and expose plain objects.

### `core/persistence`

Persistence owns rows and storage helpers. It should not own product decisions.

Examples that should stay here:

- SQLModel row classes
- session helpers
- enum/storage types
- storage-only repositories

Examples that should not live here:

- query-bag application workflows
- evaluation summary refresh orchestration
- context event sequencing logic
- run snapshot assembly

### `core/infrastructure`

Infrastructure owns adapters:

- Inngest client, registry, contracts, and thin function adapters
- sandbox manager/resource publisher
- dashboard emitter
- tracing adapters
- package dependency probes

Infrastructure modules can call application services. They should not become
the canonical home for business rules. Inngest handlers are split so core
semantic logic lives in `application/jobs`, while the Inngest-decorated shell
remains under `infrastructure/inngest/handlers`.

### `core/rest_api`

`core/rest_api` is the HTTP layer. The explicit name keeps it visually separate
from `ergon_core.api`, which is the public authoring/types API for builtins,
CLI, and students. It should be thin:

- validate/deserialize transport requests
- call application services/read models
- map missing resources to HTTP errors

It should not define reusable domain DTOs just because the frontend consumes
them. Those belong in `application/read_models` or the relevant application
domain.

## Implemented Move Map

```text
core/definitions/service.py
  -> core/application/experiments/service.py

core/definitions/schemas.py
  -> core/application/experiments/models.py

core/definitions/repository.py
  -> core/application/experiments/repository.py

core/definitions/persistence.py
  -> core/application/experiments/definition_writer.py

core/composition/*
  -> core/domain/experiments/*

core/runtime/workflows/*
  -> core/application/workflows/*
  except runtime/workflows/launch.py
  -> core/application/experiments/launch.py

core/runtime/graph/*
  -> core/application/graph/*

core/runtime/tasks/*
  -> core/application/tasks/*

core/runtime/evaluation/*
  -> core/application/evaluation/*

core/runtime/read_models/runs.py
core/runtime/read_models/run_snapshot.py
core/runtime/read_models/experiments.py
core/runtime/read_models/cohorts.py
core/runtime/read_models/resources.py
core/runtime/read_models/errors.py
core/runtime/read_models/models.py
  -> core/application/read_models/*

core/runtime/read_models/communication.py
  -> core/application/communication/service.py

communication DTOs from core/runtime/read_models/models.py
  -> core/application/communication/models.py

core/runtime/context_events.py
  -> core/application/context/events.py

core/runtime/output_extraction.py
  -> core/application/context/output_extraction.py

core/runtime/resources.py
  -> core/application/resources/models.py
  -> core/application/resources/repository.py

core/runtime/events/*
  -> core/application/events/*

core/rl/*
  -> core/rl/*
  # Keep in place for now as a separate bounded context.

core/runtime/inngest/client.py
core/runtime/inngest/registry.py
core/runtime/inngest/contracts.py
core/runtime/inngest/errors.py
  -> core/infrastructure/inngest/*

core/runtime/inngest/{handler files}.py
  -> core/application/jobs/{handler files}.py
  -> core/infrastructure/inngest/handlers/{handler files}.py
  # Split each handler: semantic background job into application/jobs,
  # Inngest decorator/event adapter into infrastructure/inngest/handlers.

core/sandbox/*
  -> core/infrastructure/sandbox/*

core/dashboard/*
  -> core/infrastructure/dashboard/*

core/runtime/tracing/*
  -> core/infrastructure/tracing/*

core/runtime/dependencies.py
  -> core/infrastructure/dependencies.py

core/generation.py
  -> core/domain/generation/context_parts.py

core/json_types.py
core/settings.py
core/utils.py
  -> core/shared/*
```

## Deleted Legacy Paths

```text
core/runtime/
  # Deleted after all subpackages moved.

core/definitions/
  # Deleted after experiment lifecycle files moved to application/experiments.

core/composition/
  # Deleted after pure domain objects moved to domain/experiments.

core/sandbox/
core/dashboard/
  # Deleted after infrastructure moved.

core/generation.py
core/json_types.py
core/settings.py
core/utils.py
  # Deleted after shared/domain moves.
```

## Import Direction Guardrails

```text
api -> application -> domain
api -> application -> persistence
api -> shared

infrastructure -> application
infrastructure -> domain
infrastructure -> persistence
infrastructure -> shared

application -> domain
application -> persistence
application -> shared

persistence -> shared
persistence -> domain/generation only if row payload parsing requires typed context parts

domain -> shared
```

Forbidden directions:

```text
domain -> application
domain -> persistence
domain -> infrastructure
domain -> rest_api

persistence -> application
persistence -> infrastructure
persistence -> rest_api

application -> rest_api
application -> infrastructure/inngest/handlers
```

## Resolved Decisions

1. This intentionally keeps `communication` separate from run read models. It is
   a product domain for agents communicating with each other.
2. `read_models` stays as a query-side application cluster instead of being
   split into every domain. That reduces churn while keeping REST
   routers thin.
3. `application/jobs` keeps the core semantics of externally-triggered
   background workflows visible. `infrastructure/inngest/handlers` should be
   thin wrappers around those use cases.
4. `persistence` remains a visible top-level layer because hiding SQL rows
   inside product domains would make storage contracts harder to
   audit.
5. Old-path compatibility aliases are intentionally avoided. Bulk import renames
   keep the finalized package structure explicit.
6. `domain/generation/context_parts.py` remains the name for generation context
   primitives.
7. Dashboard emission stays under `infrastructure/dashboard`, while product
   event contracts live under `application/events`.
8. `core/rl` remains its own bounded context instead of being renamed to
   `core/learning`.
