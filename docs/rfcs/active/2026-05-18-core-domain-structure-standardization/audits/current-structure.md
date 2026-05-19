# Current Core Structure

Date audited: 2026-05-18

Branch audited: `origin/codex/v2-pr-16-core-debt-sweep`

## Summary

`ergon_core.core` currently uses a layered split:

```text
core/
  application/
  domain/
  infrastructure/
  persistence/
  rest_api/
  rl/
  shared/
```

This is a good high-level frame. The unevenness is inside the layers:

- `application/` contains most real domain behavior.
- `domain/` is almost empty.
- `jobs/` is a cross-domain orchestration folder.
- `tasks`, `workflows`, and `graph` have overlapping runtime lifecycle
  responsibilities.
- `read_models` is a query-side contract layer, but it lives beside command
  services without a naming distinction.

## Top-Level Layers

### `application/`

This is the active core of the system. It owns use cases, orchestration,
runtime services, job payload handlers, read models, and most business rules.

Current subdomains:

```text
application/
  communication/
  context/
  evaluation/
  events/
  experiments/
  graph/
  jobs/
  read_models/
  resources/
  tasks/
  workflows/
```

Observed pattern: each subdomain uses a loose mix of `models.py`, `errors.py`,
`service.py`, and more specific files. The pattern is useful but not consistent
enough to make ownership obvious without reading code.

### `domain/`

This is currently very thin. The visible source is mostly:

```text
domain/
  generation/
    context_parts.py
```

There are also stale cache-only directories from deleted domain experiments
code. As of this audit, `domain/` is not where most runtime invariants live.
Those invariants live in application services.

`context_parts.py` is also not a domain model in the usual sense. It defines
worker/context stream payload contracts used by worker APIs, persistence,
dashboard views, replay, tests, and RL extraction. The better home is:

```text
shared/
  context_parts.py
```

That move keeps the import boundary that motivated the original placement:
persistence can import the schemas without importing `ergon_core.api`. It also
lets the codebase delete `domain/` instead of preserving an anemic one-file
layer.

### `persistence/`

This owns SQLModel tables, repository primitives, database setup, and DB-adjacent
types.

Current subdomains:

```text
persistence/
  context/
  definitions/
  graph/
  imports/
  shared/
  telemetry/
```

This layer is comparatively coherent. It mirrors the v2 persistence model:
definition tables, run graph tables, context event tables, import metadata, and
telemetry rows.

There are stale or cache-only remnants under:

```text
persistence/components/
persistence/saved_specs/
```

These should be deleted from the working tree if they are only generated cache
artifacts or empty packages left behind by PR 11/16 cleanup.

### `infrastructure/`

This owns adapters and framework glue.

Current subdomains:

```text
infrastructure/
  dashboard/
  inngest/
  sandbox/
  tracing/
  dependencies.py
```

This is a good shape. The main boundary concern is that Inngest jobs live in
`application/jobs`, while Inngest registration lives in
`infrastructure/inngest`. That split is defensible, but the job functions should
remain thin entrypoints into application services.

### `rest_api/`

This owns FastAPI routers and HTTP translation:

```text
rest_api/
  app.py
  cohorts.py
  experiments.py
  rollouts.py
  runs.py
  test_harness.py
```

The desirable invariant is that these modules call application services and
read models, not persistence or infrastructure directly except for boundary
composition.

### `rl/`

This is a separate RL-specific subsystem:

```text
rl/
  checkpoint.py
  eval_runner.py
  extraction.py
  rewards.py
  rollout_service.py
  rollout_types.py
  vllm_manager.py
```

It currently sits top-level inside core. That may be right if RL is a first-class
core capability. If it is optional or adapter-like, this is a future boundary to
review.

### `shared/`

Small shared support:

```text
shared/
  context_parts.py
  json_types.py
  settings.py
  utils.py
```

This is acceptable, but `shared` should stay small. New business concepts should
not land here just because they are used by two modules.

`context_parts.py` is an acceptable shared module because it is a genuine
cross-cutting schema contract. It should remain narrow: context stream payload
schemas only, not event builders, persistence models, dashboard-only DTOs, or
worker execution logic.

## Application Subdomains

### `application/experiments`

Current role:

- persist benchmark/experiment definitions;
- launch runs from definitions;
- model experiment run requests/results;
- expose experiment handles.

Tension:

- The v2 system often uses "definition" as the precise concept, while this
  folder is named "experiments".
- It sits close to `persistence/definitions` and `application/workflows`, so
  new code can be unsure whether definition launch belongs here or in workflows.

### `application/workflows`

Current role:

- workflow orchestration service;
- run lifecycle commands;
- run creation helpers;
- workflow-level errors/models.

Tension:

- Some task lifecycle behavior historically lived here and later moved toward
  `tasks`.
- It overlaps with `graph` whenever the operation is "advance this run graph".

### `application/tasks`

Current role:

- task execution service;
- task management operations such as cancel/refine/restart/spawn;
- task inspection and cleanup;
- task command/result models.

Tension:

- It owns user/task-facing lifecycle operations, but these operations often
  need graph traversal and workflow dispatch.
- This folder is the natural owner of public worker-context task operations,
  but not necessarily the owner of graph propagation.

### `application/graph`

Current role:

- run graph lookup;
- traversal;
- propagation;
- graph repository interface;
- graph command/data models.

Tension:

- Some files look like pure graph utilities.
- Some files are workflow lifecycle policies in graph clothing.
- Persistence graph tables live in `persistence/graph`, so the application
  graph package must avoid becoming a second persistence layer.

### `application/jobs`

Current role:

- Inngest job entrypoints and payload handlers;
- workflow start/complete/fail;
- task execute/worker/evaluate;
- sandbox setup/cleanup;
- output persistence;
- propagation.

Tension:

- This folder is organized by execution mechanism, not by domain.
- It cuts across workflows, tasks, evaluation, sandbox, resources, and graph.
- That is fine if job functions stay thin. It becomes hard to reason about if
  job functions own business rules.

### `application/evaluation`

Current role:

- evaluator/criterion execution service;
- scoring and result models;
- evaluation errors.

Tension:

- It is one of the cleaner domains after PR 13.
- It still touches persistence telemetry and task/evaluator definition metadata,
  so tests should keep guarding the runtime path.

### `application/read_models`

Current role:

- query-side DTOs for runs, cohorts, experiments, resources, and run snapshots;
- dashboard/API-facing aggregation from persistence rows.

Tension:

- This is not command-side application logic. It is a contract-building layer.
- It is close to frontend generated contracts and should be treated as such.
- Deleting remaining compatibility around `BenchmarkDefinitionRecord` will
  leave `views` as the read-only contract-building boundary.

### `application/resources`

Current role:

- resource DTOs and repository-facing application logic.

Tension:

- Some resource publication behavior also lives in jobs and sandbox
  infrastructure. The ownership split should stay explicit:
  jobs trigger publication, infrastructure adapts external files, resources
  owns persisted resource semantics.

### `application/context`

Current role:

- context event models.

Tension:

- Very small package. It may belong with context persistence/read models unless
  more application behavior lands here.

### `application/communication`

Current role:

- message/communication models, service, and errors.

Tension:

- Appears self-contained, but should be reviewed for whether it is core runtime
  behavior or an adapter-facing support domain.

### `application/events`

Current role:

- internal application event payloads for task/runtime/infrastructure events.

Tension:

- Similar to `jobs`, this is cross-domain by nature. It may be best kept as a
  shared application boundary rather than merged into a single domain.

## Non-Source Artifacts Found

The audited tree includes generated/local artifacts:

```text
__pycache__/
.DS_Store
```

There are also cache-only/stale-looking directories:

```text
application/components/
domain/experiments/
persistence/components/
persistence/saved_specs/
```

Some architecture tests already assert that deleted v2 paths such as
`saved_specs` and component catalog files should be absent. These artifacts
should be cleaned up as a hygiene PR or as part of PR17/PR18 if they are still
present in the working tree.
