# PRD 05: Application Runtime Restructure

## Goal

After outer boundaries are cleaned up, consolidate duplicated runtime lifecycle
logic across `application/tasks`, `application/workflows`, and
`application/graph`.

## Target State

Runtime application code has one obvious home for:

- run graph repository/traversal;
- task lifecycle mutations;
- workflow initialization/finalization;
- propagation and invalidation;
- task inspection;
- ready-event dispatch;
- run definition identity lookup;
- resource materialization from a task/run perspective.

Merge `application/tasks`, `application/workflows`, and `application/graph`
into:

```text
application/runtime/
  graph_repository.py
  graph_traversal.py
  lifecycle.py
  task_management.py
  task_execution.py
  task_inspection.py
  propagation.py
  run_lifecycle.py
  resources.py
  models.py
  errors.py
```

Lifecycle ownership must not remain split across three competing domains.

## Required Moves

### File Moves

| Source | Target | Notes |
| --- | --- | --- |
| `application/graph/repository.py::WorkflowGraphRepository` | `application/runtime/graph_repository.py::RuntimeGraphRepository` | Keep persistence-facing graph row operations here. |
| `application/graph/traversal.py` | `application/runtime/graph_traversal.py` | Merge `descendants()` and `descendant_ids()` here. |
| `WorkflowGraphRepository.descendants_by_parent()` | `application/runtime/graph_traversal.py` | Delete the repository helper after `TaskInspectionService` uses the traversal module. |
| `application/graph/propagation.py` | `application/runtime/lifecycle.py::RuntimeLifecycleService` | Move `get_initial_ready_tasks()`, `on_task_completed_or_failed()`, `_block_successors_bfs()`, and terminal checks here. |
| `application/workflows/service.py::initialize()` and `finalize()` | `application/runtime/run_lifecycle.py` | Own workflow initialization/finalization and run terminal state. |
| `application/workflows/runs.py` | `application/runtime/run_lifecycle.py` | Move `create_run()`, `cancel_run()`, and `latest_run_for_definition()`. |
| `application/tasks/management.py::TaskManagementService` | `application/runtime/task_management.py` | Keep object-bound dynamic task mutation here. |
| `application/tasks/execution.py::TaskExecutionService` | `application/runtime/task_execution.py` | Move `_emit_task_status()` with the service. |
| `application/tasks/inspection.py::TaskInspectionService` | `application/runtime/task_inspection.py` | Use `runtime/graph_traversal.py` for descendants. |
| `application/tasks/repository.py::TaskExecutionRepository` | `application/runtime/task_execution_repository.py` | Keep execution row writes here. |
| `application/tasks/cleanup.py` | `application/runtime/task_cleanup.py` | Keep cleanup policy with runtime task lifecycle. |
| `application/workflows/orchestration.py` | `application/runtime/models.py` | Move runtime command/result DTOs here. |
| `application/tasks/models.py`, runtime-only DTOs from `application/graph/models.py`, runtime-only DTOs from `application/workflows/models.py` | `application/runtime/models.py` | Keep public view/event DTOs out of runtime. |
| `application/graph/errors.py`, `application/tasks/errors.py`, `application/workflows/errors.py` | `application/runtime/errors.py` | Merge runtime errors into one module. |
| `application/workflows/service.py` resource methods | `application/runtime/resources.py::RuntimeResourceService` | Move `materialize_resource()`, `list_resources()`, `read_resource_bytes()`, and workspace helpers; reuse `application/resources/RunResourceRepository`. |

`GraphMutationRecordDto` is not runtime-only. It is used by REST mutation reads
and dashboard event contracts, so keep it in a graph/view contract module
instead of burying it in `application/runtime/models.py`.

### Deletions And Merges

- Delete slug-based dynamic task APIs after callers/tests use
  `spawn_dynamic_task(Task)`: `TaskManagementService.add_subtask()`,
  `TaskManagementService.plan_subtasks()`, and `WorkflowService.add_task()`.
- Merge duplicate ready dispatch helpers into
  `application/runtime/events.py::RuntimeEventDispatcher.dispatch_task_ready`.
  Delete `_dispatch_task_ready()` from `TaskManagementService` and
  `WorkflowService`.
- Merge duplicate definition lookup helpers into
  `application/runtime/run_identity.py::definition_id_for_run`. Delete
  `_resolve_definition_id()` from `TaskManagementService` and
  `WorkflowService`.
- Move runtime status vocabulary to `application/runtime/status.py` as created
  by PRD 01.

### Identity Cleanup

- Rename runtime parameters from `node_id` to `task_id` in
  `RuntimeGraphRepository.update_node_status()`, `update_node_field()`,
  `get_node()`, `get_incoming_edges()`, `get_outgoing_edges()`,
  `_get_node_row()`, and `_require_node_exists()`.
- Delete `GraphNodeLookup.node_id()` after propagation callers pass
  `task_id` directly.
- Remove the runtime read of `RunRecord.sandbox_slug` in
  `application/jobs/execute_task.py` only after sandbox identity is present in
  the object-bound `Task.sandbox` snapshot for every launch path.

### Documentation In Code

- Add module docstrings to each `application/runtime/*` module explaining the
  operation it owns and why the behavior lives there.
- Add class/function docstrings to `RuntimeLifecycleService`,
  `RuntimeGraphRepository`, `RuntimeResourceService`, and
  `TaskManagementService.spawn_dynamic_task()` that describe the invariant they
  enforce, not just the mechanics.

## Non-Goals

- Do not start this before persistence, shared-contract, infrastructure, and
  REST boundaries are under control.
- Do not change external worker/public API behavior as part of file moves.
- Do not delete dashboard/cohort compatibility here unless already migrated.

## Acceptance Criteria

- A reviewer can identify the owner for runtime lifecycle changes without
  choosing between `tasks`, `workflows`, and `graph`.
- No duplicate descendant traversal or ready-dispatch helper remains.
- `task_id` is the public/runtime identity term.
- Runtime tests and walkthrough smoke tests pass.
- Architecture tests prevent reintroducing parallel runtime lifecycle paths.

## Evidence

- [`../audits/runtime-domain-merge-audit.md`](../audits/runtime-domain-merge-audit.md)
- [`../audits/current-structure.md`](../audits/current-structure.md)
