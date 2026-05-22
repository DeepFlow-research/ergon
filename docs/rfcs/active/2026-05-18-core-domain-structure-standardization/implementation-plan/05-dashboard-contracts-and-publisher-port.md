# PR 05: Dashboard Contracts And Publisher Port

## What

Move dashboard event contracts and dashboard DTO construction out of
infrastructure, replace direct application imports of `DashboardEmitter` with a
publisher port, and delete duplicate workflow tree schemas.

## Why

Dashboard infrastructure should transport events, not build application DTOs.
The current workflow-started tree duplicates run snapshot logic through
`WorkerRef`, `TaskTreeNode`, and frontend-only recursive schemas. This PR makes
dashboard contracts part of `views/` and makes infrastructure a publisher
implementation.

## How

- Move `core/infrastructure/dashboard/event_contracts.py` to
  `core/views/dashboard_events/contracts.py`.
- Create `core/application/ports/dashboard.py` with
  `DashboardEventPublisher`.
- Simplify `DashboardEmitter` to `publish(event: InngestEventContract)`.
- Extract graph mutation mapping to
  `views/dashboard_events/graph_mutations.py`.
- Extract context event mapping to
  `views/dashboard_events/context_events.py`.
- Extract cohort dashboard event shape to
  `views/dashboard_events/cohorts.py`, but keep emission orchestration in
  compatibility code until PR 08/09.
- Delete `WorkerRef`, `TaskTreeNode`, `_WORKER_SLUG_NS`,
  `_worker_ref_for_slug()`, and `_build_task_tree_for_run()`.
- Change `DashboardWorkflowStartedEvent` to carry `snapshot: RunSnapshotDto`.
- Update frontend event parsing to consume the generated snapshot contract.

## Plan

1. Add tests for dashboard event contract import location.
2. Add a run snapshot based workflow-started contract test.
3. Add tests for graph mutation row-to-DTO mapping shared by live events and
   `RunReadService.list_mutations()`.
4. Move dashboard contracts into `views/dashboard_events/contracts.py`.
5. Update `scripts/export_contract_schemas.py::CONTRACTS_MODULE`.
6. Create `DashboardEventPublisher` protocol.
7. Narrow `DashboardEmitter` to transport-only publishing.
8. Move graph mutation and context event mappers into views.
9. Replace workflow tree assembly with snapshot event construction.
10. Update frontend contract parser/types to delete manual
    `WorkerRefSchema` and `TaskTreeNodeSchema`.
11. Regenerate dashboard contracts.
12. Delete old dashboard contract module and old workflow tree helpers.

## Acceptance Criteria

- Dashboard event contracts live in `core/views/dashboard_events/contracts.py`.
- `core/infrastructure/dashboard/event_contracts.py` is gone.
- Application services do not import concrete `DashboardEmitter`.
- `DashboardWorkflowStartedEvent` uses `snapshot: RunSnapshotDto`.
- `WorkerRef` and `TaskTreeNode` are gone in backend and frontend.
- Graph mutation DTO mapping is shared between snapshot/API reads and live
  dashboard events.

## Tests

```bash
pytest ergon_core/tests/unit/dashboard -q
pytest ergon_core/tests/unit/runtime/test_graph_mutation_contracts.py -q
pytest ergon_core/tests/unit/runtime/test_context_event_contracts.py -q
pytest ergon_core/tests/unit/architecture -q
rg -n "WorkerRef|TaskTreeNode|_build_task_tree_for_run|infrastructure\\.dashboard\\.event_contracts|DashboardEmitter" ergon_core ergon-dashboard/src
```

