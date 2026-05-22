# Runtime Domain Merge Audit

## Why This Needs Attention

The current split between:

```text
application/tasks/
application/workflows/
application/graph/
```

is one of the larger remaining sources of duplication in core. The split made
sense while the team was still churning on the mental model of "definition",
"run graph", "task", and "workflow". After PRs 11-17, that model should be
stable enough to pay down the structure.

The issue is not only file location. The issue is that lifecycle concepts are
spread across three packages, so readers have to infer the "why" from the "how"
of the code:

- graph code sometimes owns lifecycle policy;
- workflow code sometimes owns task/query/resource behavior;
- task management code sometimes owns graph traversal and propagation-adjacent
  invalidation;
- multiple modules know how to resolve run definition identity and dispatch
  `task/ready` events.

That makes the code harder to review and increases the chance that future
changes add another partial lifecycle path instead of extending the canonical
one.

## What Lives In The Three Domains Today

### `application/graph`

Current responsibilities:

- `repository.py`: structural run graph writes, node/edge queries,
  definition-to-run copying, task snapshot inflation, and graph mutation WAL.
- `propagation.py`: readiness calculation, task status updates, edge
  satisfaction/invalidation, blocking downstream successors, reactivating
  dynamic children, and workflow terminal-state detection.
- `traversal.py`: containment-descendant traversal.
- `lookup.py`: task/node lookup helper.
- `models.py`: graph DTOs and mutation payloads.

Tension:

`repository.py` is a good structural graph boundary. `propagation.py` is not
just graph structure; it is runtime lifecycle policy. It decides what happens
after completion/failure and when downstream work becomes eligible.

### `application/tasks`

Current responsibilities:

- `management.py`: worker/manager task mutations, dynamic task spawning,
  cancellation, orphan cancellation, descendant blocking, refinement, restart,
  downstream invalidation, edge reset, ready-event dispatch, and cancelled-event
  dispatch.
- `execution.py`: task execution application service and status event emission.
- `inspection.py`: task inspection helpers.
- `cleanup.py`: task cleanup and cancellation cleanup result semantics.
- `repository.py`: task execution/output repository helpers.
- `models.py`: command/result DTOs for task management and cleanup.

Tension:

`management.py` is the real command-side lifecycle service for task operations,
but it also owns pieces that look like graph lifecycle policy: downstream
invalidation, edge reset, descendant traversal, terminal-status rules, and
ready-event dispatch.

### `application/workflows`

Current responsibilities:

- `service.py`: run initialization/finalization, propagation wrappers, task and
  dependency inspection, resource visibility/materialization, CLI-style graph
  mutation previews, blocker/next-action DTOs, node/resource lookup helpers,
  ready-event dispatch, and sandbox upload path construction.
- `runs.py`: run creation/cancellation/latest-run helpers.
- `orchestration.py`: workflow command/result DTOs.
- `models.py`: workflow/task/resource/dependency read and mutation DTOs.

Tension:

`WorkflowService` is doing too much. It is partly run lifecycle, partly runtime
inspection, partly resource service, partly CLI mutation adapter, and partly
propagation facade. It overlaps with both `tasks` and `graph`.

## Duplication And Friction To Investigate

### Status And Lifecycle Policy

The same conceptual rules appear in multiple places:

- terminal vs non-terminal task states;
- readiness;
- edge pending/satisfied/invalidated semantics;
- completion/failure propagation;
- cancellation and restart invalidation;
- when a task may move from terminal back to pending;
- when cancelled dynamic children may reactivate.

The most obvious overlap is:

- `WorkflowService.propagate()` sets a task completed, then calls
  `graph.propagation.on_task_completed_or_failed()`;
- `WorkflowService.propagate_failure()` sets a task failed, then calls the same
  propagation helper;
- `TaskManagementService.restart_task()` implements a separate but related
  downstream invalidation and edge-reset model.

This looks like one lifecycle domain split across three packages.

### Run Definition Identity Resolution

Both task management and workflow service resolve a run's definition id from
`RunRecord.workflow_definition_id`. Jobs also carry definition ids through
payloads.

This should probably be a single runtime helper or service boundary so all
runtime code answers "what definition does this run belong to?" the same way.

### Descendant Traversal

Descendant logic exists in several forms:

- `application/graph/traversal.py`;
- `WorkflowGraphRepository.descendants_by_parent()`;
- `TaskManagementService._count_non_terminal_descendants()`;
- `TaskManagementService._invalidate_downstream()`;
- `WorkflowService._descendant_ids()` for resource scopes.

Some of these are containment traversal; some are dependency-edge traversal.
The code would be easier to reason about if those two graph concepts were named
and separated explicitly:

- containment descendants: parent/child hierarchy;
- dependency descendants: downstream through dependency edges.

### Node/Task DTO Vocabulary

Multiple DTO families describe overlapping concepts:

- `GraphNodeDto`;
- `RunGraphNodeView`;
- `WorkflowTaskRef`;
- `TaskDescriptor`;
- `WorkflowMutationRef`;
- graph mutation payload DTOs.

These may all be justified, but their roles should be documented:

- structural graph DTO;
- hydrated runtime task view;
- CLI/view task reference;
- job orchestration descriptor;
- mutation/audit payload.

Without that explanation, the duplication looks accidental.

### Ready/Cancellation Event Dispatch

`TaskReadyEvent` and `TaskCancelledEvent` dispatch decisions appear close to
task management, workflow service, and jobs. Dispatch should have one clear
owner:

- lifecycle service decides the domain event should happen;
- job/adapter layer sends it to Inngest after commit;
- or the service is explicitly allowed to dispatch after commit.

The current shape mixes those ideas.

### Resource Visibility And Materialization

`WorkflowService` owns resource listing, resource reads, workspace inspection,
resource-copy naming, sandbox destination validation, and sandbox upload. That
is a lot of resource behavior for a workflow service.

This may want its own runtime resource service so workflow/run lifecycle is not
responsible for file visibility and sandbox copy policy.

## Merge Target: `application/runtime`

One possible target is:

```text
application/runtime/
  __init__.py
  errors.py
  models.py
  graph_repository.py
  graph_traversal.py
  lifecycle.py
  task_management.py
  run_lifecycle.py
  inspection.py
  resources.py
```

The important part is not the exact filenames. The important part is the
ownership split.

### `graph_repository.py`

Owns structural graph persistence and WAL:

- copy definition graph into run graph;
- add nodes and edges;
- update node/edge fields;
- enforce structural graph invariants such as referential integrity and cycles;
- append graph mutation records;
- hydrate a run-tier task snapshot.

Does not own:

- task status transition policy;
- run lifecycle;
- user authorization/containment permissions;
- event dispatch.

### `lifecycle.py`

Owns runtime state-transition policy:

- initial readiness;
- task completion/failure propagation;
- edge satisfaction/invalidation;
- downstream blocking;
- terminal run detection;
- cancellation/restart transition rules that are graph-wide rather than a
  single command's input validation.

This is where the "why" should live. A reader should be able to understand the
state machine by reading this module's class and method docstrings.

### `task_management.py`

Owns command-side task mutations:

- spawn dynamic object-bound tasks;
- cancel a task;
- refine a task;
- restart a task;
- cancel or block descendants in response to lifecycle decisions.

This service should call lifecycle/graph services for graph-wide policy instead
of reimplementing propagation concepts locally.

### `run_lifecycle.py`

Owns run-level lifecycle:

- initialize a run graph from a definition;
- mark run executing;
- finalize run score/status;
- fail/cancel run;
- locate latest run for a definition if that remains core behavior.

This should stay distinct from task-level lifecycle.

### `inspection.py`

Owns view runtime inspection for tasks/dependencies/blockers/next actions:

- list/get tasks;
- list dependencies;
- compute blockers;
- compute suggested next actions;
- return task workspace summaries if resources remain separate.

This should not mutate graph state.

### `resources.py`

Owns runtime resource visibility and materialization policy:

- list resources by scope;
- resolve resource producer;
- read resource bytes;
- compute safe sandbox destination paths;
- materialize/copy resource into sandbox;
- persist import resource records.

This removes file/sandbox resource policy from `WorkflowService`.

## Documentation Standard If We Merge

The new modules should not repeat the current pattern where readers infer
purpose by reading implementation details. Each major class/function should
carry a short "what and why" docstring.

### Module Docstrings

Each runtime module should start with:

```python
"""Runtime lifecycle policy for run graph execution.

This module owns state-transition decisions for run graph nodes and edges:
which tasks are initially ready, how completion satisfies dependencies, how
failure blocks downstream work, and when a run is terminal.

It deliberately does not own structural graph persistence or Inngest event
delivery. Structural writes go through RuntimeGraphRepository; job modules turn
returned domain events into Inngest sends after commit.
"""
```

The docstring should state:

- what the module owns;
- what it deliberately does not own;
- why the boundary exists.

### Class Docstrings

Each service class should explain the domain role, not merely list methods.

Example:

```python
class RuntimeLifecycleService:
    """State machine for run graph execution.

    The service translates task terminal events into graph consequences:
    satisfied or invalidated edges, newly ready tasks, blocked successors, and
    run terminal-state decisions. Keeping this policy here prevents task
    management, workflow jobs, and graph persistence from each inventing their
    own propagation rules.
    """
```

### Function Docstrings

Public methods should answer:

1. What state transition or query does this perform?
2. Why does this rule exist?
3. What side effects occur?
4. What does the caller still own?

Example:

```python
async def propagate_completion(...):
    """Apply the graph consequences of one task completing successfully.

    Completion satisfies all outgoing dependency edges from the completed task.
    A downstream task becomes ready only when every upstream source task is
    currently completed. Dependency-free dynamic children are also activated
    here because they are intentionally created after their parent begins
    running and therefore cannot be discovered during initial run setup.

    Returns the task ids that should receive `task/ready` events. The caller
    owns transaction commit and event delivery.
    """
```

This is the standard we want because the hard part of this subsystem is not the
SQL. The hard part is the lifecycle reasoning.

## Suggested Audit Before Implementation

Before writing the implementation plan, audit these exact questions:

1. Which `WorkflowService` methods are command/mutation methods versus read-only
   inspection methods?
2. Which `TaskManagementService` helpers are actually lifecycle policy?
3. Which `graph.propagation` helpers still read definition-tier tables and can
   now be run-tier only?
4. Which traversal helpers are containment traversal versus dependency-edge
   traversal?
5. Which methods dispatch Inngest events directly, and should they instead
   return domain events?
6. Which DTOs are structural, view, job orchestration, or audit payloads?
7. Which tests cover restart invalidation, failure blocking, cancelled-child
   reactivation, and resource-scope traversal?

## Possible Implementation Order

1. Add characterization tests for lifecycle behavior before moving files.
2. Extract a `RuntimeLifecycleService` from `graph/propagation.py`.
3. Move terminal run detection into that lifecycle service.
4. Move restart downstream invalidation from `TaskManagementService` into the
   lifecycle service, while keeping the `restart_task` command in task
   management.
5. Split `WorkflowService` read-only inspection methods into a runtime
   inspection service.
6. Split resource visibility/materialization into a runtime resource service.
7. Rename or re-export old imports only if needed for one PR; remove shims in
   the follow-up.

Each step should be behavior-preserving.

## Acceptance Criteria For The Merge

- There is one owner for lifecycle state-transition policy.
- There is one owner for structural graph persistence and graph mutation WAL.
- There is one owner for task-management commands.
- There is one owner for run-level lifecycle.
- Resource materialization no longer lives in a general workflow service.
- Module/class/function docstrings explain the ownership and "why", not only
  the mechanics.
- Architecture tests prevent job handlers, REST handlers, or persistence code
  from growing new lifecycle policy.
