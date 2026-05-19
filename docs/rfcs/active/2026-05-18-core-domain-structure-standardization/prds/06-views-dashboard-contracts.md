# PRD 06: Views And Dashboard Contracts

## Goal

Replace the loose `application/read_models` concept with a stricter view
boundary and move dashboard-facing contract assembly out of infrastructure and
jobs.

## Target State

View modules:

- read persistence rows;
- assemble API/dashboard DTOs;
- do not mutate runtime state;
- do not start jobs;
- do not own lifecycle decisions.

Dashboard event contracts and workflow tree assembly live in `views/`, not in
dashboard infrastructure or job modules.

Target structure:

```text
views/
  runs/
    models.py
    service.py
    snapshot.py
    graph_tasks.py
  experiments/
    models.py
    service.py
  resources.py
  training.py
  compat/
    cohorts.py
  dashboard_events/
    contracts.py
    graph_mutations.py
    context_events.py
    cohorts.py
```

## Required Moves

### View Package Split

- Split `application/read_models/models.py`; do not move the mixed module
  wholesale.
- Move run snapshot DTOs (`RunTaskDto`, `RunResourceDto`,
  `RunExecutionAttemptDto`, `RunTaskEvaluationDto`,
  `RunEvaluationCriterionDto`, `RunSandboxDto`, `RunContextEventDto`,
  `RunSnapshotDto`) to `views/runs/models.py`.
- Move `application/read_models/runs.py` to
  `views/runs/service.py`.
- Move `application/read_models/run_snapshot.py` to
  `views/runs/snapshot.py`.
- Move experiment DTOs and read service from `application/read_models/experiments.py`
  to `views/experiments/models.py` and
  `views/experiments/service.py`.
- Move `application/read_models/resources.py` to
  `views/resources.py`.
- Move `application/read_models/errors.py` to `views/errors.py`.
- Do not move `application/read_models/cohorts.py` into normal views;
  split it into `application/compat/cohorts.py` for writes/recompute and
  `views/compat/cohorts.py` for temporary read-only
  `CohortSummaryDto` / `CohortDetailDto` assembly until frontend deletion.
- If PRD 01 retains training observability, move `TrainingCurvePointDto`,
  `TrainingSessionDto`, and `TrainingMetricDto` to
  `views/training.py`.

### Dashboard Contract Source

- Move `core/infrastructure/dashboard/event_contracts.py` to
  `views/dashboard_events/contracts.py` as specified in PRD
  03.
- Update `scripts/export_contract_schemas.py::CONTRACTS_MODULE` to
  `ergon_core.core.views.dashboard_events.contracts`.
- Update tests importing the old contract module:
  `ergon_core/tests/unit/dashboard/test_event_contract_types.py`,
  `ergon_core/tests/unit/architecture/test_model_field_descriptions.py`,
  `ergon_core/tests/unit/runtime/test_context_event_contracts.py`, and
  `ergon_core/tests/unit/runtime/test_graph_mutation_contracts.py`.
- Update architecture tests that currently require the old infrastructure event
  contract location:
  `ergon_core/tests/unit/architecture/test_public_api_boundaries.py` and
  `ergon_core/tests/unit/architecture/test_core_schema_sources.py`.

### Workflow Tree And Snapshot Overlap

- Delete `WorkerRef`, `TaskTreeNode`, `_WORKER_SLUG_NS`,
  `_worker_ref_for_slug()`, and `_build_task_tree_for_run()`.
- Change `DashboardWorkflowStartedEvent` to carry `snapshot: RunSnapshotDto`
  instead of `task_tree: TaskTreeNode`.
- Update the frontend workflow-started handler to initialize run state from
  `RunSnapshotDto.tasks` and related maps instead of parsing a recursive
  `TaskTreeNode`.
- Delete the manual frontend `WorkerRefSchema`, `TaskTreeNodeSchema`, and
  `TaskTreeNode` type from `ergon-dashboard/src/lib/contracts/events.ts`.
- Extract the graph/task helper overlap between the deleted
  `_build_task_tree_for_run()` and `run_snapshot._build_task_map()` into
  `views/runs/graph_tasks.py` before deleting the old tree
  builder.
- `graph_tasks.py` should own helpers such as `build_children_by_parent()`,
  `build_depends_on_by_target()`, and `worker_by_binding()`.
- `start_workflow.py` should call `build_workflow_started_event(...)` from the
  view layer and pass the completed event to the dashboard publisher.

### Graph Mutations

- Move graph mutation row-to-event mapping from `DashboardEmitter` to
  `views/dashboard_events/graph_mutations.py`.
- Add `graph_mutation_record_from_row(row: RunGraphMutation) ->
  GraphMutationRecordDto`.
- Add `dashboard_graph_mutation_event_from_row(row: RunGraphMutation) ->
  DashboardGraphMutationEvent`.
- Update `RunReadService.list_mutations()` to use
  `graph_mutation_record_from_row()` so snapshot/API reads and live dashboard
  events share one mapper.

### Context Events

- Move context event mapping from `DashboardEmitter.on_context_event()` to
  `views/dashboard_events/context_events.py`.
- Add `context_event_to_dashboard_event(...)` and reuse the same task/execution
  mapping assumptions as `run_snapshot._context_events_by_task()`.

### Cohort Events

- Move cohort dashboard event assembly to
  `views/dashboard_events/cohorts.py::cohort_updated_event_from_summary`.
- Recompute and emission orchestration remain in `application/compat/cohorts.py`;
  the view module only turns read-only summary DTOs into
  `CohortUpdatedEvent`.

### Dashboard Transport

- Simplify `DashboardEmitter` to transport only, with a method shaped like
  `emit(event: InngestEventContract) -> None`.
- Delete event-specific DTO construction from infrastructure after the
  view builders above exist.

## Non-Goals

- Do not redesign the frontend event schema unless drift is discovered.
- Do not delete cohorts in this PRD; isolate them through the deprecated
  compatibility PRD.
- Do not turn views into command services.

## Acceptance Criteria

- Dashboard event schemas still generate and drift checks pass.
- `start_workflow` no longer builds dashboard tree DTOs inline.
- Dashboard infrastructure no longer imports view DTO dependencies beyond the
  event payloads it sends.
- View modules are read-only by architecture test.
- `rg -n "get_session\\(|session\\.add\\(|session\\.commit\\("
  ergon_core/ergon_core/core/views` returns no writes outside
  documented compatibility helpers.
- Existing run snapshot/dashboard tests pass.

## Evidence

- [`../audits/infrastructure-application-boundary-audit.md`](../audits/infrastructure-application-boundary-audit.md)
- [`../audits/schema-concept-debt-audit.md`](../audits/schema-concept-debt-audit.md)
