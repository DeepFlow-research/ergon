# Remaining Task Orchestration Cleanup

This document captures the current state of the remaining task/workflow Inngest runners after the rubric evaluation, criterion execution, and worker-execution cleanups.

It focuses on:

- where the remaining Inngest coupling still lives
- where we still have "0.5 step durability" risk
- which runners are healthy vs overly coupled
- what we should do next to finish the cleanup

## Confirmed Implementation Decisions

The following decisions have been explicitly chosen and should be treated as binding for the next implementation phase.

### `task_execute.py`

- the runner owns event emission and child invokes
- `TaskExecutionService` owns prepare/finalize business logic
- `TaskExecutionService` owns execution state writes

Interpretation:

- the runner remains the orchestration shell
- the service owns the semantics of creating/running/finalizing a task execution
- the runner invokes:
  - `sandbox_setup_fn`
  - `worker_execute_fn`
  - `persist_outputs_fn`
- the runner emits:
  - dashboard task-running / task-completed / task-failed signals
  - `TaskCompletedEvent`
  - `TaskFailedEvent`

### `check_evaluators.py`

- the runner owns evaluator status transitions
- the service should compute dispatch decisions and evaluation inputs only

Interpretation:

- `EvaluatorDispatchService` should not mutate evaluator records directly
- the runner continues to:
  - `mark_failed`
  - `mark_running`
  - `mark_completed`

### `workflow_complete.py`

- `WorkflowFinalizationService` should own all finalization and persistence
- the runner should only emit dashboard and cleanup follow-up events

Interpretation:

- the service is responsible for:
  - building the final `ExecutionResult`
  - building `RunCompletionData`
  - completing the run
  - persisting run-level `Evaluation`

### DTO policy

- event DTOs and service DTOs should be separated now, not deferred

Interpretation:

- event payloads stay as orchestration contracts
- service-layer commands/results should be introduced as part of these extractions
- do not continue using event models as the default internal service API

## What "0.5 Step Durability" Means

By "0.5 step durable," we mean code where:

- part of the logical unit is inside `ctx.step.run(...)` or `ctx.step.invoke(...)`
- part of the same logical unit is outside those boundaries
- correctness depends on the seam between them
- retries/replays would be difficult to reason about cleanly

This is not exactly the same as "uses Inngest too much."

Some Inngest usage is healthy:

- parsing event payloads
- pure reads
- orchestration decisions
- invoking child orchestration functions
- emitting events in explicit durable steps

The unhealthy pattern is when:

- runners become the application service
- business logic is split across multiple ad hoc step boundaries
- retry semantics are only partially aligned with the true logical transaction

## Current State Summary

### Already improved

The following areas are now in much better shape:

- rubric APIs no longer depend on `inngest.Context`
- rubric implementations no longer orchestrate criterion fanout directly
- criterion execution uses a framework-agnostic runtime
- worker execution no longer depends on ambient Inngest step context

That means the remaining cleanup is mostly on the workflow/task orchestration side.

## Remaining Runners: Health Assessment

## 1. `task_execute.py`

Path:

- `h_arcane/core/_internal/task/inngest_functions/task_execute.py`

### Current role

This is the central task orchestrator.

It currently:

1. loads run / experiment / task context
2. validates that the node is a leaf
3. loads input resources
4. creates a task execution record
5. emits running state
6. invokes:
   - `sandbox_setup_fn`
   - `worker_execute_fn`
   - `persist_outputs_fn`
7. finalizes success or failure

### Current health

- orchestration shape: good
- separation of concerns: not good enough
- durability shape: mixed
- overall: the biggest remaining offender

### Why it is still problematic

It is still both:

- an Inngest orchestrator
- an application service for "what task execution means"

The logical task execution unit is split across:

- inline context loading
- one step for execution creation
- three child invokes
- a finalization step
- a failure-handling step

That is workable, but still has the "0.5 step durable" feel because the runner owns too much of the business flow.

### Assessment

- healthy enough to work: yes
- healthy as final architecture: no
- overly coupled to Inngest: yes
- urgency: highest

### Refactor plan

Extract a `TaskExecutionService`.

The service should own:

- task preparation
- task execution state transitions
- finalization inputs/outputs
- error classification where appropriate

The runner should own:

- deserializing `TaskReadyEvent`
- calling the service in durable boundaries
- invoking child orchestrators
- emitting follow-up events

### Target shape

1. parse `TaskReadyEvent`
2. call `TaskExecutionService.prepare(...)`
3. invoke child runners
4. call `TaskExecutionService.finalize_success(...)`
5. or call `TaskExecutionService.finalize_failure(...)`
6. emit events in explicit durable steps

### Suggested extraction

New files:

- `h_arcane/core/_internal/task/services/task_execution_service.py`
- `h_arcane/core/_internal/task/services/dto.py`

Potential DTOs:

- `PrepareTaskExecutionCommand`
- `PreparedTaskExecution`
- `FinalizeTaskExecutionCommand`
- `FailTaskExecutionCommand`

### Implementation-ready boundary

#### Runner owns

- parse `TaskReadyEvent`
- call service methods inside explicit durable boundaries
- invoke child orchestrators
- emit dashboard task lifecycle events
- emit `TaskCompletedEvent` / `TaskFailedEvent`
- translate uncaught failures into `NonRetriableError`

#### `TaskExecutionService` owns

- validating the task node for execution
- deciding whether the node is a leaf or should be skipped
- loading/deriving execution inputs needed for child invokes
- creating the task execution record and marking running
- final success persistence
- final failure persistence

#### New DTOs to introduce now

- `PrepareTaskExecutionCommand`
- `PreparedTaskExecution`
- `FinalizeTaskExecutionCommand`
- `FailTaskExecutionCommand`

Suggested shape:

- `PrepareTaskExecutionCommand`
  - `run_id`
  - `experiment_id`
  - `task_id`

- `PreparedTaskExecution`
  - `run_id`
  - `experiment_id`
  - `task_id`
  - `execution_id`
  - `benchmark_name`
  - `task_name`
  - `task_description`
  - `parent_task_id`
  - `input_resource_ids`
  - `skip_execution`
  - `skip_reason`

- `FinalizeTaskExecutionCommand`
  - `run_id`
  - `experiment_id`
  - `task_id`
  - `execution_id`
  - `output_text`
  - `output_resource_ids`

- `FailTaskExecutionCommand`
  - `run_id`
  - `experiment_id`
  - `task_id`
  - `execution_id`
  - `error_message`

#### Target runner flow

1. deserialize `TaskReadyEvent`
2. `ctx.step.run("prepare-task-execution", service.prepare, output_type=PreparedTaskExecution)`
3. if `skip_execution`, return `TaskExecuteResult(skipped=True, ...)`
4. `ctx.step.run("emit-dashboard-task-running", ...)`
5. `ctx.step.invoke("invoke-sandbox-setup", sandbox_setup_fn, ...)`
6. `ctx.step.invoke("invoke-worker-execute", worker_execute_fn, ...)`
7. `ctx.step.invoke("invoke-persist-outputs", persist_outputs_fn, ...)`
8. `ctx.step.run("finalize-success", service.finalize_success, ...)`
9. `ctx.step.run("emit-task-completed", ...)`
10. on failure:
   - `ctx.step.run("finalize-failure", service.finalize_failure, ...)`
   - `ctx.step.run("emit-task-failed", ...)`
   - raise `inngest.NonRetriableError(...)`

#### Important implementation note

Because the service owns execution state writes, the current helpers:

- `_create_running_execution(...)`
- `_complete_and_emit(...)`
- `_fail_and_emit(...)`

should be split so that:

- persistence moves into the service
- event emission stays in the runner

## 2. `workflow_start.py`

Path:

- `h_arcane/core/_internal/task/inngest_functions/workflow_start.py`

### Current role

This initializes DAG execution:

1. load experiment / task tree
2. initialize task states
3. create task evaluator records
4. mark the run executing
5. find initial ready tasks
6. emit `task/ready`

### Current health

- orchestration shape: fairly healthy
- separation of concerns: a bit mixed
- durability shape: mostly okay
- overall: acceptable, but not ideal

### What is healthy here

The high-level orchestration is a good fit for Inngest.

The function:

- responds to a workflow-start event
- performs one-time setup
- emits follow-up task-ready events

That is valid orchestration work.

### What is still too coupled

`_initialize_dag(...)` still contains real business logic:

- create task state records
- create task evaluator records
- emit dashboard state changes

This is application service logic living in a runner helper.

### Assessment

- healthy enough: yes
- highest priority: no
- overly coupled: mildly
- urgency: medium-low

### Refactor plan

Extract a `WorkflowStartService` responsible for:

- initializing task states
- creating evaluator records
- computing initial ready task metadata

Keep the runner responsible for:

- parsing event payload
- calling the service in durable boundaries
- emitting ready events

### Suggested extraction

New file:

- `h_arcane/core/_internal/task/services/workflow_start_service.py`

## 3. `task_propagate.py`

Path:

- `h_arcane/core/_internal/task/inngest_functions/task_propagate.py`

### Current role

This reacts to a completed task and propagates the DAG:

1. update dependency state
2. compute newly ready tasks
3. emit new `task/ready` events
4. determine workflow terminal state
5. emit workflow complete or failed event if needed

### Current health

- orchestration shape: good
- separation of concerns: decent, not complete
- durability shape: acceptable
- overall: healthier than `task_execute`

### What is healthy here

This file is closer to a real orchestrator than `task_execute`.

It mostly:

- reacts to an event
- calls propagation logic
- emits follow-up events

That is the right general shape.

### What is still somewhat coupled

The runner still owns:

- task metadata lookup helpers
- ready event + dashboard emission pairing
- terminal workflow event decision logic

This is not catastrophic, but there is still room to separate service logic from orchestration.

### Assessment

- healthy enough: mostly yes
- overly coupled: a bit
- urgency: medium-low

### Refactor plan

Extract a `TaskPropagationService` that returns:

- newly ready tasks
- terminal-state decision
- optional task metadata needed by the runner

Keep the runner responsible for:

- event deserialization
- event emission
- durable boundaries

### Suggested extraction

New file:

- `h_arcane/core/_internal/task/services/task_propagation_service.py`

## 3A. `check_evaluators.py`

Path:

- `h_arcane/core/_internal/evaluation/inngest_functions/check_evaluators.py`

### Current role

This reacts to `TaskCompletedEvent` and dispatches task-level rubric evaluation.

It currently:

1. loads evaluator records
2. loads task execution outputs and experiment context
3. parses rubric/evaluator configs
4. marks invalid evaluators failed
5. marks valid evaluators running
6. invokes `evaluate_task_run`
7. marks evaluators completed with returned scores

### Current health

- orchestration shape: decent
- separation of concerns: not good enough
- durability shape: mixed
- overall: one of the highest-value remaining cleanup targets

### What is still too coupled

The runner still owns:

- evaluator discovery
- evaluator/rubric parsing
- evaluation input construction
- dispatch strategy
- evaluator status transitions

We have decided that status transitions remain in the runner, but the rest should move into a service.

### Refactor plan

Extract an `EvaluatorDispatchService`.

#### Runner owns

- parse `TaskCompletedEvent`
- mark invalid evaluators failed
- mark valid evaluators running
- invoke `evaluate_task_run`
- mark evaluators completed

#### `EvaluatorDispatchService` owns

- loading task execution context
- loading outputs and task input
- parsing evaluator/rubric configs
- returning:
  - invalid evaluator IDs
  - valid evaluator dispatch payloads

#### New DTOs to introduce now

- `DispatchEvaluatorsCommand`
- `PreparedEvaluatorDispatch`
- `PreparedSingleEvaluator`

Suggested shape:

- `DispatchEvaluatorsCommand`
  - `run_id`
  - `task_id`

- `PreparedSingleEvaluator`
  - `evaluator_id`
  - `rubric`
  - `task_input`
  - `agent_reasoning`
  - `agent_outputs`

- `PreparedEvaluatorDispatch`
  - `task_id`
  - `invalid_evaluator_ids`
  - `valid_evaluators`

#### Target runner flow

1. deserialize `TaskCompletedEvent`
2. `ctx.step.run("prepare-evaluator-dispatch", service.prepare_dispatch, output_type=PreparedEvaluatorDispatch)`
3. mark `invalid_evaluator_ids` failed
4. mark valid evaluator IDs running
5. invoke `evaluate_task_run` in parallel using the prepared payloads
6. mark evaluator IDs completed with returned scores
7. return `EvaluatorsResult`

#### Why this boundary

This preserves the chosen policy:

- status transitions stay orchestration-owned
- payload preparation and evaluator interpretation become service-owned

## 4. `workflow_complete.py`

Path:

- `h_arcane/core/_internal/task/inngest_functions/workflow_complete.py`

### Current role

This finalizes the workflow after all tasks complete:

1. aggregate evaluator scores
2. aggregate costs
3. build task results
4. build final `ExecutionResult`
5. complete the run
6. persist a run-level evaluation record
7. emit dashboard complete
8. emit cleanup

### Current health

- orchestration shape: actually pretty good
- separation of concerns: not good enough
- durability shape: solid
- overall: too coupled, but less scary than `task_execute`

### What is healthy here

Most of the heavy work is already grouped into one durable step:

- `finalize-run`

That means the durability shape is pretty reasonable.

### What is still too coupled

`_finalize_run(...)` is basically a `WorkflowFinalizationService` already, just embedded inside the runner file.

It owns significant business logic:

- score aggregation
- cost aggregation
- task result assembly
- output resource assembly
- execution result assembly
- evaluation persistence

### Assessment

- durability shape: good
- architecture cleanliness: not good enough
- urgency: medium-high

### Refactor plan

Extract a `WorkflowFinalizationService`.

The runner should become:

1. parse `WorkflowCompletedEvent`
2. call `WorkflowFinalizationService.finalize(...)`
3. emit dashboard event
4. emit cleanup event

### Suggested extraction

New file:

- `h_arcane/core/_internal/task/services/workflow_finalization_service.py`

### Implementation-ready boundary

#### Runner owns

- parse `WorkflowCompletedEvent`
- call `WorkflowFinalizationService.finalize(...)`
- emit dashboard workflow completed event
- emit cleanup event

#### `WorkflowFinalizationService` owns

- loading run + experiment
- evaluator score aggregation
- total cost aggregation
- task result assembly
- output resource assembly
- final `ExecutionResult` assembly
- `RunCompletionData` creation
- completing the run
- creating the run-level `Evaluation`

#### New DTOs to introduce now

- `FinalizeWorkflowCommand`
- `FinalizedWorkflowResult`

Suggested shape:

- `FinalizeWorkflowCommand`
  - `run_id`

- `FinalizedWorkflowResult`
  - `run_id`
  - `final_score`
  - `normalized_score`
  - `evaluators_count`

#### Target runner flow

1. deserialize `WorkflowCompletedEvent`
2. `ctx.step.run("finalize-run", service.finalize, output_type=FinalizedWorkflowResult)`
3. `ctx.step.run("emit-dashboard-workflow-completed", ...)`
4. `ctx.step.run("emit-cleanup", ...)`
5. return `WorkflowCompleteResult`

#### Important implementation note

The current `_finalize_run(...)` is already very close to the target service body.

This should be treated as a service extraction rather than a conceptual redesign.

## 5. `workflow_failed.py`

Path:

- `h_arcane/core/_internal/task/inngest_functions/workflow_failed.py`

### Current role

This handles terminal workflow failure:

1. build failed `ExecutionResult`
2. mark the run failed
3. emit cleanup
4. emit dashboard failed state

### Current health

- orchestration shape: good enough
- separation of concerns: still mixed
- durability shape: acceptable
- overall: simpler version of `workflow_complete`

### Assessment

- healthy enough for now: yes
- overly coupled: yes, but less severe
- urgency: low-medium

### Refactor plan

Extract a `WorkflowFailureService` so the runner only:

- parses event payload
- calls the service
- emits follow-up signals

### Suggested extraction

New file:

- `h_arcane/core/_internal/task/services/workflow_failure_service.py`

## 6. `benchmark_run_start.py`

Path:

- `h_arcane/core/_internal/task/inngest_functions/benchmark_run_start.py`

### Current role

This bridges CLI-triggered benchmark runs into server-side orchestration:

1. parse benchmark request
2. resolve worker config
3. create worker
4. create workflow from benchmark factory
5. validate DAG
6. store workers in process memory
7. persist workflow
8. emit `workflow/started`

### Current health

- useful orchestration role: yes
- thin runner: no
- durability shape: mixed
- overall: still too thick

### Why it is still somewhat risky

There is still a lot of meaningful setup work outside the durable persistence step:

- config resolution
- worker creation
- workflow construction
- validation
- in-memory worker storage

This is not necessarily wrong, but it is still runner-heavy and somewhat awkward from a replay/retry perspective.

### Assessment

- healthy enough to keep working: yes
- healthy final architecture: no
- urgency: medium

### Refactor plan

Extract a `BenchmarkRunInitializationService` that owns:

- request interpretation
- worker / workflow construction
- DAG validation
- worker registration

Keep the runner responsible for:

- event deserialization
- durable persistence step
- workflow-start emission

### Suggested extraction

New file:

- `h_arcane/core/_internal/task/services/benchmark_run_initialization_service.py`

## What Still Feels Overly Connected To Inngest

These are the remaining runner files that still feel overly connected:

- `task_execute.py`
- `workflow_complete.py`
- `benchmark_run_start.py`
- `check_evaluators.py`

These are not all equally unhealthy, but these are the main places where business logic is still embedded in orchestration code.

## Relative Priority

### Highest priority

1. `task_execute.py`
2. `check_evaluators.py`

### Medium priority

3. `workflow_complete.py`
4. `benchmark_run_start.py`

### Lower priority cleanup

5. `workflow_start.py`
6. `task_propagate.py`
7. `workflow_failed.py`

## Recommended Sequence To Rectify

## Phase 1: Finish the obvious service extractions

### 1. Extract evaluator dispatch

Target:

- `check_evaluators.py`

Add:

- `EvaluatorDispatchService`

Why first:

- completes the evaluation cleanup story
- likely smaller and lower-risk than `task_execute`
- now has an explicit service/runner boundary defined in this document

### 2. Extract task execution service

Target:

- `task_execute.py`

Add:

- `TaskExecutionService`
- service DTOs

Why second:

- this is the biggest remaining "0.5 step durable" runner
- highest leverage cleanup on the task side
- now has an explicit ownership split defined in this document

## Phase 2: Finalization cleanup

### 3. Extract workflow finalization

Target:

- `workflow_complete.py`

Add:

- `WorkflowFinalizationService`

Why third:

- `_finalize_run(...)` already maps cleanly to a service extraction
- durability shape is already good, so this is primarily a boundary cleanup

### 4. Extract workflow failure handling

Target:

- `workflow_failed.py`

Add:

- `WorkflowFailureService`

## Phase 3: Startup / propagation cleanup

### 5. Extract workflow start service

Target:

- `workflow_start.py`

Add:

- `WorkflowStartService`

### 6. Extract task propagation service

Target:

- `task_propagate.py`

Add:

- `TaskPropagationService`

## Phase 4: Benchmark entrypoint cleanup

### 7. Extract benchmark initialization service

Target:

- `benchmark_run_start.py`

Add:

- `BenchmarkRunInitializationService`

## Desired End State

At the end of this cleanup:

- Inngest runners parse events, call services, and emit follow-up events
- business logic lives in services
- step boundaries wrap coherent service calls
- event DTOs stop doubling as the main internal service contracts
- task/workflow orchestration remains event-driven, but no longer framework-shaped internally

## Short Answer

### Are these healthy today?

- `workflow_start.py`: mostly healthy
- `task_propagate.py`: mostly healthy
- `workflow_complete.py`: durability-healthy, architecturally too coupled
- `workflow_failed.py`: acceptable, still coupled
- `benchmark_run_start.py`: useful but too thick
- `task_execute.py`: not healthy enough yet

### What still needs fixing?

The big remaining cleanup is:

- extract application services out of the remaining thick task/workflow runners
- especially `task_execute.py`, `check_evaluators.py`, and `workflow_complete.py`

## Ready-To-Implement Status

This document should now be considered implementation-ready for the next three refactors:

1. `check_evaluators.py`
2. `task_execute.py`
3. `workflow_complete.py`

The document is still roadmap-level for:

- `workflow_start.py`
- `task_propagate.py`
- `workflow_failed.py`
- `benchmark_run_start.py`

Those still may need a second pass of spec detail before implementation.
