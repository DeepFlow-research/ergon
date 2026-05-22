# PR 11: Application Runtime Restructure

## What

Merge `application/tasks`, `application/workflows`, and `application/graph`
into `application/runtime`, removing duplicated lifecycle, traversal,
ready-dispatch, and run identity helpers.

## Why

Runtime behavior is the largest remaining source of duplication after the
outer boundaries are cleaned. A reviewer should not need to decide whether task
lifecycle belongs in `tasks`, `workflows`, or `graph`. This PR creates a single
runtime owner with docstrings that explain the invariant behind each service.

## How

- Move graph repository/traversal into
  `application/runtime/graph_repository.py` and
  `application/runtime/graph_traversal.py`.
- Move propagation/lifecycle behavior into
  `application/runtime/lifecycle.py`.
- Move workflow initialization/finalization and run creation/cancellation into
  `application/runtime/run_lifecycle.py`.
- Move task management, execution, inspection, cleanup, and execution
  repository into matching runtime modules.
- Move runtime DTOs/errors into `application/runtime/models.py` and
  `application/runtime/errors.py`.
- Move resource materialization methods into
  `application/runtime/resources.py`.
- Merge duplicate ready dispatch into
  `application/runtime/events.py::RuntimeEventDispatcher.dispatch_task_ready`.
- Merge duplicate definition lookup into
  `application/runtime/run_identity.py::definition_id_for_run`.
- Rename runtime public parameters from `node_id` to `task_id`.
- Delete slug-based dynamic task APIs after callers use
  `spawn_dynamic_task(Task)`.

## Plan

1. Add architecture tests preventing reintroduction of
   `application/tasks`, `application/workflows`, and `application/graph`.
2. Add characterization tests for dynamic task spawning, task completion
   propagation, failure propagation, restart/refine, and task inspection.
3. Add tests for `task_id` naming in public/runtime service APIs.
4. Create `application/runtime/` package and move graph repository/traversal.
5. Move task execution repository and execution service.
6. Move task management/inspection/cleanup.
7. Move workflow/run lifecycle.
8. Merge propagation and ready-dispatch helpers.
9. Merge definition-id lookup helpers.
10. Delete slug-based dynamic task APIs and update callers/tests.
11. Rename runtime API parameters from `node_id` to `task_id`.
12. Add module/class/function docstrings that explain ownership and invariants.
13. Delete empty old packages.

## Acceptance Criteria

- `application/runtime/*` is the only owner for run graph lifecycle, task
  lifecycle, propagation, execution row writes, dynamic task mutation, and
  runtime resource views.
- `application/tasks`, `application/workflows`, and `application/graph` are
  gone.
- No duplicate descendant traversal helper remains.
- No duplicate ready-dispatch helper remains.
- `task_id` is the public/runtime identity term.
- Slug-based dynamic task APIs are gone.
- Runtime smoke tests pass.

## Tests

```bash
pytest ergon_core/tests/unit/runtime -q
pytest ergon_core/tests/smoke -q
pytest ergon_core/tests/unit/architecture -q
rg -n "application\\.(tasks|workflows|graph)|node_id|add_subtask\\(|plan_subtasks\\(|WorkflowService\\.add_task|_dispatch_task_ready|_resolve_definition_id" ergon_core/ergon_core/core tests
```

