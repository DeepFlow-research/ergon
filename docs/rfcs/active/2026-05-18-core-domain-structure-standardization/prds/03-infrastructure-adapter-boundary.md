# PRD 03: Infrastructure Adapter Boundary

## Goal

Make infrastructure a set of external/framework adapters. Infrastructure should
implement application-declared ports and should not reimplement application
business operations.

## Target State

Dependency direction is:

```text
inbound adapters -> application use cases / views
application use cases -> application ports -> infrastructure implementations
```

Infrastructure owns:

- Inngest function registration and transport details;
- dashboard event transport;
- E2B sandbox/file/command adapters;
- blob-store implementations;
- tracing sinks and id helpers;
- process startup wiring.

Infrastructure does not own:

- graph view assembly;
- cohort recomputation;
- resource append/dedup policy;
- runtime lifecycle policy;
- application DTO construction when a view exists.

## Required Moves

### Dashboard Contracts And Publishing

- Move `core/infrastructure/dashboard/event_contracts.py` to
  `core/views/dashboard_events/contracts.py`.
- Move every `Dashboard*Event` contract with that file.
- Do not move `WorkerRef` and `TaskTreeNode` as durable schemas. PRD 06
  replaces `workflow.started.task_tree` with the existing `RunSnapshotDto`
  view, which deletes both helper schemas and the frontend's manual
  recursive Zod mirror.
- Create `core/application/ports/dashboard.py` with a
  `DashboardEventPublisher` protocol that publishes already-built dashboard
  event contracts.
- Keep `core/infrastructure/dashboard/emitter.py`, but narrow it to a concrete
  implementation of that protocol. It should expose one transport method such
  as `publish(event: InngestEventContract)` and send
  `inngest.Event(name=event.name, data=event.model_dump(mode="json"))`.
- Remove event-construction methods from `DashboardEmitter`. Application jobs
  and services should call view builders, then pass the completed event
  to the dashboard publisher port.
- Replace direct application imports of concrete `DashboardEmitter` in
  `application/tasks/management.py`, `application/communication/service.py`,
  `application/tasks/execution.py`, `application/jobs/worker_execute.py`,
  `application/jobs/evaluate_task_run.py`,
  `application/jobs/cleanup_cancelled_task.py`,
  `application/jobs/start_workflow.py`, and
  `application/jobs/complete_workflow.py` with the dashboard publisher port or
  composition-provided helper.

### Dashboard View Helpers

- Delete `_WORKER_SLUG_NS`, `_worker_ref_for_slug()`, and
  `_build_task_tree_for_run()` from `application/jobs/start_workflow.py` after
  PRD 06 changes workflow-started events to carry `RunSnapshotDto`.
- Replace the inline workflow-started tree assembly in `start_workflow.py`
  with a call to the run snapshot view.
- Move context-event payload assembly from `DashboardEmitter.on_context_event()`
  into `views/dashboard_events/context_events.py`.
- Move graph mutation row-to-event assembly from `DashboardEmitter` into
  `views/dashboard_events/graph_mutations.py`.
- Merge the graph mutation row-to-DTO logic used by
  `DashboardEmitter.graph_mutation()` and
  `RunReadService.list_mutations()` so both call the same view mapper.

### Deprecated Cohort Emission

- Move module-level `emit_cohort_updated_for_run()` from
  `core/infrastructure/dashboard/emitter.py` to
  `core/application/compat/cohorts.py` as
  `emit_deprecated_cohort_updated_for_run(...)`.
- That compatibility function should recompute/build `CohortUpdatedEvent |
  None` and publish through `DashboardEventPublisher`.
- Delete the infrastructure import of `experiment_cohort_service`.

### Sandbox Resource Publishing

- Split `core/infrastructure/sandbox/resource_publisher.py`.
- Keep filesystem/blob adapter methods in infrastructure:
  `_list_sandbox_dir()`, `_read_sandbox_file()`, `_write_blob()`, and
  `_blob_path()`.
- Move DB/resource semantics from `SandboxResourcePublisher.sync()` and
  `SandboxResourcePublisher.publish_value()` into
  `core/application/resources/publishing.py::RunResourcePublishService`.
- Move the `RunResource` append/dedup writes currently inside infrastructure
  into that application service.
- Update `application/jobs/persist_outputs.py` to call
  `RunResourcePublishService`, injecting sandbox reader/blob writer ports from
  infrastructure composition.

### Inngest And Tracing

- Delete the stale TODO in
  `core/infrastructure/inngest/handlers/cancel_orphan_subtasks.py`; the handler
  already delegates to application jobs.
- Clarify the docstring in
  `core/infrastructure/inngest/handlers/sandbox_cleanup.py`: the handler
  registers terminal-event adapters, while
  `application/jobs/sandbox_cleanup.py` owns cleanup sequencing.
- Keep `core/infrastructure/tracing/contexts.py` in infrastructure. Add an
  architecture test that it imports only tracing id/type helpers and standard
  UUID utilities; it must not import application, persistence, sessions,
  settings, or clocks.

## Non-Goals

- Do not remove dashboard or Inngest.
- Do not change event names or frontend contracts without the dashboard
  view PRD.
- Do not redesign sandbox public APIs in this slice.

## Acceptance Criteria

- Application services no longer import concrete `DashboardEmitter` except via
  explicit composition/bootstrap paths.
- Dashboard infrastructure does not import cohort services.
- Sandbox infrastructure does not append `RunResource` rows directly after the
  resource service split.
- Inngest handlers remain adapters around application jobs/use cases.
- Architecture tests encode the allowed import direction.

## Evidence

- [`../audits/infrastructure-application-boundary-audit.md`](../audits/infrastructure-application-boundary-audit.md)
