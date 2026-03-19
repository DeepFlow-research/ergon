# Workflow Start Initialization Service

This document turns the `workflow_start.py` cleanup into an implementation-ready spec.

It follows the same rule as the previous cleanup wave:

- runner orchestrates
- service owns business logic
- event DTOs stay as orchestration contracts
- service DTOs become the internal API

## Goal

Refactor `h_arcane/core/_internal/task/inngest_functions/workflow_start.py` so that:

- the Inngest runner becomes orchestration-only
- workflow initialization semantics move into a `WorkflowInitializationService`
- dashboard follow-up emission remains runner-owned
- initial `TaskReadyEvent` fanout remains runner-owned

## Current Problem

`workflow_start.py` still mixes orchestration with workflow initialization semantics.

Today it:

- loads the experiment and task tree
- initializes all task-state event-log entries
- creates `TaskEvaluator` rows
- marks the run as executing
- computes initial ready tasks
- emits dashboard workflow-started and task pending/ready signals
- emits initial `TaskReadyEvent`s

The biggest issue is not that it uses Inngest.

The issue is that the runner still decides what "workflow initialization" means.

## Target Ownership

### Runner owns

- deserializing `WorkflowStartedEvent`
- calling the service in explicit durable steps
- dashboard workflow-started emission
- dashboard task pending/ready emission
- `TaskReadyEvent` emission for initial ready tasks

### `WorkflowInitializationService` owns

- loading and validating workflow initialization context
- parsing the task tree
- creating initial task-state records
- creating `TaskEvaluator` bindings
- marking the run as executing
- computing initial ready tasks
- returning structured metadata needed for orchestration follow-up

## Files

Primary runner:

- `h_arcane/core/_internal/task/inngest_functions/workflow_start.py`

New files:

- `h_arcane/core/_internal/task/services/workflow_initialization_service.py`
- `h_arcane/core/_internal/task/services/dto.py`

Likely touched existing files:

- `h_arcane/core/_internal/task/results.py`
- `h_arcane/core/_internal/task/schema.py`
- `h_arcane/core/_internal/task/propagation.py`

## DTOs To Add

Add these service DTOs to `h_arcane/core/_internal/task/services/dto.py`.

### `InitializeWorkflowCommand`

Purpose:

- input to the service

Fields:

- `run_id`
- `experiment_id`

### `TaskDescriptor`

Purpose:

- reusable task metadata for runner follow-up emissions

Fields:

- `task_id`
- `task_name`
- `parent_task_id`

### `InitializedWorkflow`

Purpose:

- result of service initialization

Fields:

- `run_id`
- `experiment_id`
- `workflow_name`
- `dependency_count`
- `evaluator_count`
- `total_tasks`
- `total_leaf_tasks`
- `pending_tasks`
- `initial_ready_tasks`

Suggested field shapes:

- `pending_tasks: list[TaskDescriptor]`
- `initial_ready_tasks: list[TaskDescriptor]`

This lets the runner emit dashboard pending and ready signals without re-querying the tree.

## Service Contract

Introduce:

- `WorkflowInitializationService.initialize(command: InitializeWorkflowCommand) -> InitializedWorkflow`

## Service Responsibilities In Detail

`WorkflowInitializationService.initialize(...)` should:

1. load the experiment
2. parse and validate the task tree
3. record initial `PENDING` state for every task
4. create `TaskEvaluator` rows from task-tree evaluator refs
5. mark the run as `EXECUTING`
6. compute the initial ready leaf tasks
7. mark those tasks as `READY`
8. return enough metadata for the runner to emit follow-up dashboard and event signals

Important:

- task-state writes stay grouped behind the service boundary
- evaluator creation stays grouped behind the service boundary
- the runner should not need to traverse the task tree to recover task names or parent IDs

## Recommended Implementation Shape

## Step 1: move initialization logic behind the service

Move the logic currently spread across:

- inline experiment/tree loading
- `_initialize_dag(...)`
- `_mark_run_executing(...)`
- `_get_and_mark_initial_tasks(...)`

into `WorkflowInitializationService.initialize(...)`.

Do not move:

- `_emit_dashboard_workflow_started(...)`
- the `TaskReadyEvent` fanout loop

Those are orchestration concerns and should remain runner-owned.

## Step 2: stop returning step-shaped DTOs from the service boundary

The current runner uses:

- `DagInitResult`
- `ReadyTaskIdsResult`

These are step-oriented result models.

For the new service boundary, prefer one service DTO:

- `InitializedWorkflow`

The runner can still return the public `WorkflowStartResult`.

## Step 3: make the runner consume service output only

The target runner flow should be:

1. parse `WorkflowStartedEvent`
2. `ctx.step.run("initialize-workflow", ...)` calling `WorkflowInitializationService.initialize(...)`
3. emit dashboard workflow-started
4. emit dashboard task pending/ready signals using returned descriptors
5. emit `TaskReadyEvent`s for `initial_ready_tasks`
6. return `WorkflowStartResult`

## Target Runner Flow

The intended post-refactor flow is:

1. parse `WorkflowStartedEvent`
2. call `WorkflowInitializationService.initialize(...)` in one durable step
3. emit dashboard workflow-started in one durable step
4. emit dashboard task pending/ready changes in one or more explicit durable steps
5. emit `TaskReadyEvent` for each ready task in parallel durable steps
6. return `WorkflowStartResult`

## Notes On Dashboard Emission Ownership

Keep dashboard emission runner-owned for this phase.

That means the service should return task descriptors, not call `dashboard_emitter` directly.

Reason:

- dashboard emission is orchestration-side observability
- we do not want the new service to become another runner-shaped service

## Suggested Code Split

### In `workflow_start.py`

Keep:

- event parsing
- runner decorator
- dashboard workflow-started emission helper
- event fanout helper(s)
- translation from `InitializedWorkflow` to `WorkflowStartResult`

Remove or collapse:

- inline experiment loading
- `_initialize_dag(...)`
- `_mark_run_executing(...)`
- `_get_and_mark_initial_tasks(...)`

### In `workflow_initialization_service.py`

Add:

- `WorkflowInitializationService`
- helper methods if useful:
  - `_load_tree(...)`
  - `_record_initial_pending_states(...)`
  - `_create_task_evaluators(...)`
  - `_mark_run_executing(...)`
  - `_compute_initial_ready_tasks(...)`

## Acceptance Criteria

This refactor is done when:

- `workflow_start.py` no longer owns task-tree traversal for initialization semantics
- `workflow_start.py` no longer creates task-state rows directly
- `workflow_start.py` no longer creates `TaskEvaluator` rows directly
- `workflow_start.py` no longer decides initial ready tasks directly
- runner still emits `TaskReadyEvent`s for all initial ready tasks
- dashboard still shows workflow started plus task pending/ready transitions
- returned `WorkflowStartResult` is unchanged in external behavior

## Edge Cases To Preserve

Preserve existing behavior for:

- experiment missing
- task tree missing
- workflow with no evaluators
- workflow with no initial ready tasks
- root composite workflow where all initial ready tasks are leaf descendants

## Validation

After implementation, verify:

- all tasks still get initial `PENDING` state recorded
- evaluator bindings are still created for all task-tree evaluators
- run status still moves to `EXECUTING`
- initial ready tasks are still marked `READY`
- dashboard still shows workflow-started and task ready signals
- `TaskReadyEvent` fanout still happens for the same tasks as before

## Recommended Follow-Up After This File

Once this lands, the next paired cleanup should be:

- `task_propagate.py` -> `TaskPropagationService`

These two runners are best cleaned up together because they form the workflow lifecycle edges:

- workflow start
- task completion propagation
