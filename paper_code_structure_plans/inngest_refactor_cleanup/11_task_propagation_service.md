# Task Propagation Service

This document turns the `task_propagate.py` cleanup into an implementation-ready spec.

It is the companion to:

- `10_workflow_start_initialization_service.md`

Together, these two files should finish slimming the remaining thick runners in the main workflow path.

## Goal

Refactor `h_arcane/core/_internal/task/inngest_functions/task_propagate.py` so that:

- the runner becomes orchestration-only
- propagation and terminal-state decisions move into a `TaskPropagationService`
- event emission stays runner-owned
- dashboard ready / workflow-failed emissions stay runner-owned

## Current Problem

`task_propagate.py` still mixes orchestration with workflow progress semantics.

Today it:

- loads run / experiment / task tree context for task metadata
- calls `on_task_completed(...)`
- computes workflow terminal state with `is_workflow_complete(...)` and `is_workflow_failed(...)`
- emits `TaskReadyEvent`s
- emits dashboard ready state changes
- emits `WorkflowCompletedEvent` or `WorkflowFailedEvent`

The underlying propagation helpers are useful, but the runner still owns too much of the overall meaning of "advance the workflow after a task completes."

## Target Ownership

### Runner owns

- deserializing `TaskCompletedEvent`
- calling the service in explicit durable steps
- emitting `TaskReadyEvent`s
- emitting dashboard ready signals
- emitting `WorkflowCompletedEvent` or `WorkflowFailedEvent`
- emitting dashboard workflow failed signal

### `TaskPropagationService` owns

- propagation after task completion
- marking completion-driven state transitions
- determining which tasks are newly ready
- loading task metadata needed for follow-up orchestration
- determining whether the workflow is complete or failed
- returning a structured result for the runner to act on

## Files

Primary runner:

- `h_arcane/core/_internal/task/inngest_functions/task_propagate.py`

New files:

- `h_arcane/core/_internal/task/services/task_propagation_service.py`
- `h_arcane/core/_internal/task/services/dto.py`

Likely touched existing files:

- `h_arcane/core/_internal/task/propagation.py`
- `h_arcane/core/_internal/task/results.py`

## DTOs To Add

Add these service DTOs to `h_arcane/core/_internal/task/services/dto.py`.

### `PropagateTaskCompletionCommand`

Purpose:

- input to the service

Fields:

- `run_id`
- `experiment_id`
- `task_id`
- `execution_id`

### `ReadyTaskDescriptor`

Purpose:

- task metadata for ready follow-up emissions

Fields:

- `task_id`
- `task_name`
- `parent_task_id`

### `WorkflowTerminalState`

Purpose:

- explicit workflow terminal classification

Suggested shape:

- enum or literal-like field with values:
  - `none`
  - `completed`
  - `failed`

### `PropagationResult`

Purpose:

- full result returned to the runner

Fields:

- `run_id`
- `experiment_id`
- `completed_task_id`
- `ready_tasks`
- `workflow_terminal_state`

Suggested field shapes:

- `ready_tasks: list[ReadyTaskDescriptor]`
- `workflow_terminal_state: WorkflowTerminalState`

## Service Contract

Introduce:

- `TaskPropagationService.propagate(command: PropagateTaskCompletionCommand) -> PropagationResult`

## Service Responsibilities In Detail

`TaskPropagationService.propagate(...)` should:

1. mark the completed task as completed in the event log
2. compute newly unblocked tasks
3. mark those tasks as ready
4. propagate composite-parent completion if applicable
5. determine whether the workflow is now complete
6. determine whether the workflow is now failed
7. load task metadata for ready follow-up emissions
8. return an explicit result to the runner

Important:

- the runner should not need to load the task tree just to get names and parents
- the runner should not directly call low-level propagation helpers after this extraction

## Recommended Implementation Shape

## Step 1: wrap propagation semantics in the service

Move orchestration-relevant semantics currently spread across:

- inline tree loading
- `_propagate(...)`
- `is_workflow_complete(...)`
- `is_workflow_failed(...)`

behind one service call.

The low-level helpers in `propagation.py` can remain as implementation details for now.

This phase does not need to redesign the underlying propagation module.

## Step 2: return ready-task descriptors, not just task IDs

The current runner has to re-load task metadata and define helper closures:

- `get_task_name(...)`
- `get_parent_id(...)`

That logic should disappear from the runner.

The service should return `ReadyTaskDescriptor` entries instead.

## Step 3: make terminal-state selection explicit

Do not return two booleans if we can avoid it at the service boundary.

Prefer one explicit terminal-state field:

- `none`
- `completed`
- `failed`

The public runner result can still expose:

- `workflow_complete: bool`
- `workflow_failed: bool`

for compatibility with `TaskPropagateResult`.

## Target Runner Flow

The intended post-refactor flow is:

1. parse `TaskCompletedEvent`
2. call `TaskPropagationService.propagate(...)` in one durable step
3. emit `TaskReadyEvent`s for `ready_tasks`
4. emit dashboard ready state changes for `ready_tasks`
5. if terminal state is `completed`, emit `WorkflowCompletedEvent`
6. if terminal state is `failed`, emit `WorkflowFailedEvent` and dashboard workflow-failed signal
7. return `TaskPropagateResult`

## Notes On Failure Emission

Keep workflow-failed dashboard emission runner-owned for this phase.

Reason:

- this is observability and follow-up orchestration
- the service should classify the workflow state, not perform the side effects

## Suggested Code Split

### In `task_propagate.py`

Keep:

- event parsing
- runner decorator
- ready-event fanout helper(s)
- workflow-completed / workflow-failed event emission helper(s)
- translation from `PropagationResult` to `TaskPropagateResult`

Remove or collapse:

- inline tree loading
- `get_task_name(...)`
- `get_parent_id(...)`
- `_propagate(...)`
- direct terminal-state checks in the runner

### In `task_propagation_service.py`

Add:

- `TaskPropagationService`
- helper methods if useful:
  - `_run_propagation(...)`
  - `_classify_terminal_state(...)`
  - `_load_ready_task_descriptors(...)`

## Acceptance Criteria

This refactor is done when:

- `task_propagate.py` no longer traverses the task tree to recover names and parents
- `task_propagate.py` no longer directly calls low-level propagation functions
- `task_propagate.py` no longer directly decides workflow terminal state
- runner still emits `TaskReadyEvent`s for newly ready tasks
- dashboard still shows newly ready task transitions
- workflow completed/failed follow-up events are still emitted correctly
- returned `TaskPropagateResult` preserves external behavior

## Edge Cases To Preserve

Preserve existing behavior for:

- no newly ready tasks
- a task completion that causes parent composite completion but no new leaf readiness
- workflow completion after the last leaf completes
- workflow failure after any failed task exists
- missing run / experiment / task tree cases remaining non-terminal and non-crashing where that is current behavior

## Validation

After implementation, verify:

- completed task is still marked completed in task state history
- newly unblocked tasks are still marked ready
- `TaskReadyEvent` fanout still targets the same tasks as before
- dashboard ready emissions still contain the correct task names and parent IDs
- workflow-completed and workflow-failed emissions still happen under the same conditions as before

## Recommended Follow-Up After This File

After `workflow_start.py` and `task_propagate.py` are cleaned up, the main workflow lifecycle should be in good shape.

At that point the remaining architectural decision is mostly:

- whether `benchmark_run_start.py` should remain accepted bootstrap glue
- or whether it deserves a separate worker/bootstrap redesign
