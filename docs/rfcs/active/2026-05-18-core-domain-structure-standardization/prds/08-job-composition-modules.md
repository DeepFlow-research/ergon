# PRD 08: Job Composition Modules

## Goal

Merge the split `application/jobs/*` and `infrastructure/inngest/handlers/*`
shape into job-local composition modules with better locality of behavior.

One job/event should be understandable from one folder. That folder may contain
both the framework adapter and the application composition function, but the
internal file boundaries still enforce dependency direction.

## Problem

The current event path is spread across several unrelated-looking places:

```text
application/jobs/start_workflow.py
application/jobs/models.py
application/events/task_events.py
infrastructure/inngest/handlers/start_workflow.py
```

That split hides the real unit of behavior. `start_workflow` is not just an
application function and not just an Inngest handler; it is a runtime job that:

- receives a stable event payload;
- composes application services and views;
- uses infrastructure implementations through ports;
- exposes an Inngest registration wrapper.

Today a reader has to chase the event contract, result DTO, job logic, and
handler registration across multiple packages. The result is low locality and
weak ownership for event-specific models.

## Target State

Create a composition boundary for runtime jobs:

```text
core/jobs/
```

`core/jobs` is neither pure application nor pure infrastructure. It is the edge
where an event-specific use case composes application logic with injected
infrastructure implementations.

Each job lives in a semantic package:

```text
core/jobs/
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

## Module Roles

### `contract.py`

Owns the event wire contract and local job result DTOs.

Allowed imports:

- `application/events/base.py` for `InngestEventContract`;
- `shared/*`;
- Pydantic/typing/stdlib.

Forbidden imports:

- concrete infrastructure;
- SQLModel sessions/table queries;
- runtime services/repositories;
- dashboard emitters;
- sandbox managers.

This file replaces both scattered event definitions and the shared
`application/jobs/models.py` catch-all.

### `job.py`

Owns the event-specific composition logic.

Allowed imports:

- application services, runtime services, views, and ports;
- persistence row models when the current application pattern requires direct
  session reads/writes;
- shared types;
- this job's `contract.py`.

Forbidden imports:

- concrete infrastructure implementations such as `DashboardEmitter`, E2B
  managers, Inngest clients, blob writers, or concrete tracing exporters.

`job.py` may accept infrastructure behavior through application ports:

```python
async def run_start_workflow_job(
    event: WorkflowStartedEvent,
    *,
    dashboard: DashboardEventPublisher,
) -> WorkflowStartResult:
    ...
```

### `inngest.py`

Owns framework registration and adapter wiring.

Allowed imports:

- Inngest framework/client helpers;
- this job's `contract.py`;
- this job's `job.py`;
- concrete infrastructure implementations needed to satisfy ports.

Forbidden behavior:

- direct SQL queries;
- graph/runtime lifecycle decisions;
- dashboard DTO construction;
- sandbox/blob/resource persistence policy.

`inngest.py` should read as a thin adapter:

```python
@inngest_client.create_function(...)
async def start_workflow_fn(ctx: inngest.Context) -> WorkflowStartResult:
    return await run_start_workflow_job(
        WorkflowStartedEvent.model_validate(ctx.event.data),
        dashboard=get_dashboard_publisher(),
    )
```

## Required Moves

### Replace The Split Job/Handler Shape

- Move `application/jobs/start_workflow.py` and
  `infrastructure/inngest/handlers/start_workflow.py` into
  `core/jobs/workflow/start/job.py` and `core/jobs/workflow/start/inngest.py`.
- Move `application/jobs/complete_workflow.py` and
  `infrastructure/inngest/handlers/complete_workflow.py` into
  `core/jobs/workflow/complete/`.
- Move `application/jobs/fail_workflow.py` and
  `infrastructure/inngest/handlers/fail_workflow.py` into
  `core/jobs/workflow/fail/`.
- Move `application/jobs/execute_task.py` and
  `infrastructure/inngest/handlers/execute_task.py` into
  `core/jobs/task/execute/`.
- Move `application/jobs/propagate_execution.py` and
  `infrastructure/inngest/handlers/propagate_execution.py` into
  `core/jobs/task/propagate/`.
- Move `application/jobs/evaluate_task_run.py` and
  `infrastructure/inngest/handlers/evaluate_task_run.py` into
  `core/jobs/task/evaluate/`.
- Move `application/jobs/cleanup_cancelled_task.py` and
  `infrastructure/inngest/handlers/cleanup_cancelled_task.py` into
  `core/jobs/task/cleanup_cancelled/`.
- Move `application/jobs/cancel_orphan_subtasks.py` and
  `infrastructure/inngest/handlers/cancel_orphan_subtasks.py` into
  `core/jobs/task/cancel_orphans/`.
- Move `application/jobs/sandbox_setup.py` and
  `infrastructure/inngest/handlers/sandbox_setup.py` into
  `core/jobs/sandbox/setup/`.
- Move `application/jobs/sandbox_cleanup.py` and
  `infrastructure/inngest/handlers/sandbox_cleanup.py` into
  `core/jobs/sandbox/cleanup/`.
- Move `application/jobs/persist_outputs.py` and
  `infrastructure/inngest/handlers/persist_outputs.py` into
  `core/jobs/resources/persist_outputs/`.
- Move `application/jobs/run_cleanup.py` and
  `infrastructure/inngest/handlers/run_cleanup.py` into
  `core/jobs/run/cleanup/`.

### Split Job Contracts

- Delete `application/jobs/models.py`.
- Move each request/result model from `application/jobs/models.py` into the
  matching job package `contract.py`.
- Move job-specific event contracts from `application/events/task_events.py`
  into the matching job package `contract.py`.
- Move run cleanup/cancellation event contracts from
  `application/events/infrastructure_events.py` into the matching job package
  `contract.py`.
- Keep `application/events/base.py` only if it remains the shared
  `InngestEventContract` base. If the base is used only by jobs after this
  refactor, move it to `core/jobs/base.py`.
- Do not create a new shared `core/jobs/models.py` or `core/jobs/events.py`.

### Preserve External Contracts

- Keep Inngest event names stable.
- Keep Inngest function ids stable.
- Keep retry and cancellation settings stable.
- Update handler registry imports to point at the new `core/jobs/**/inngest.py`
  modules.

### Composition Rules

- Replace direct application imports of concrete infrastructure with job-level
  injection where the job is the natural composition point.
- Keep pure application services below the job layer. Runtime services should
  not import `core/jobs`.
- Keep concrete infrastructure adapters below `infrastructure/*`. They may
  implement ports, but they should not import job packages except from
  `core/jobs/**/inngest.py` wrappers.

## Non-Goals

- Do not create a generic job framework, decorator DSL, or registry abstraction.
- Do not change event names, function ids, retries, or cancellation semantics.
- Do not move dashboard view logic into `inngest.py`.
- Do not move runtime lifecycle logic into `inngest.py`.
- Do not make `core/jobs` a dumping ground for reusable services; reusable
  behavior still belongs in application services, views, or ports.

## Acceptance Criteria

- A reader can inspect one `core/jobs/<domain>/<job>/` folder and find the
  event contract, result DTO, job composition logic, and Inngest wrapper.
- `application/jobs/` is gone.
- `infrastructure/inngest/handlers/` is gone or reduced to one-release import
  shims with deletion tasks in the same stack.
- `application/jobs/models.py` is gone.
- Job contracts are local to their owning job package.
- Architecture tests enforce:
  - `contract.py` has no infrastructure/persistence/service imports;
  - `job.py` has no concrete infrastructure imports;
  - `inngest.py` has no SQLModel table queries or business logic;
  - runtime/application services do not import `core/jobs`.
- Existing Inngest event names, function ids, retries, cancellation rules, and
  end-to-end runtime behavior remain stable.

## Evidence

- Current flat application job files under `core/application/jobs/`.
- Current mirrored handler files under `core/infrastructure/inngest/handlers/`.
- [`03-infrastructure-adapter-boundary.md`](03-infrastructure-adapter-boundary.md)
  for the application-port/infrastructure-implementation rule.
