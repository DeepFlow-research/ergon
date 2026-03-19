# Post-Cleanup Status And Next Wave

This document captures where the Inngest cleanup stands after the recent extractions of:

- `EvaluatorDispatchService`
- `TaskExecutionService`
- `WorkflowFinalizationService`

It is meant to answer two questions:

1. how healthy is the current Inngest coupling now?
2. what should the next cleanup wave be if we want to keep pushing toward the target architecture?

## Executive Summary

The codebase is in a meaningfully better state than before.

The most important shift is:

- core worker execution is no longer polluted by ambient Inngest context
- rubric interfaces and criterion runtime are no longer directly coupled to `inngest.Context`
- the biggest task/evaluation runners are now substantially thinner and delegate business logic to services

That means the architecture is no longer primarily suffering from "execution code wearing orchestration clothes."

The remaining issues are now narrower:

- a few runners are still too thick
- some orchestration modules still bundle business decisions with event emission
- bootstrap and propagation paths still need cleanup if we want the boundary to be consistently clean

So the current assessment is:

- overall coupling health: much improved
- core architectural direction: correct
- fully cleaned up: not yet
- next work: slim the remaining thick runners

## What Is Now In Good Shape

### `check_evaluators.py`

Path:

- `h_arcane/core/_internal/evaluation/inngest_functions/check_evaluators.py`

Current status:

- runner owns orchestration and evaluator status transitions
- `EvaluatorDispatchService` owns evaluator preparation
- event DTOs are no longer being used as the de facto service API for this path

Assessment:

- healthy enough as a runner: yes
- still overly coupled to Inngest: no
- follow-up needed: low

### `task_execute.py`

Path:

- `h_arcane/core/_internal/task/inngest_functions/task_execute.py`

Current status:

- runner owns child invokes and event emission
- `TaskExecutionService` owns prepare/finalize business logic
- execution state writes now live behind the service boundary

Assessment:

- healthy enough as a runner: yes
- previous major coupling issue addressed: yes
- follow-up needed: low to medium

Remaining note:

- this runner still coordinates a large orchestration flow, but the unhealthy service-orchestrator mixing is no longer the main problem

### `workflow_complete.py`

Path:

- `h_arcane/core/_internal/task/inngest_functions/workflow_complete.py`

Current status:

- runner deserializes `WorkflowCompletedEvent`
- runner calls one finalization service step
- `WorkflowFinalizationService` owns aggregation and persistence
- runner emits dashboard completion and cleanup follow-up events

Assessment:

- healthy enough as a runner: yes
- overly coupled to Inngest: no
- follow-up needed: low

### Worker Execution Internals

Relevant paths:

- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
- `h_arcane/benchmarks/common/workers/react_worker.py`

Current status:

- worker internals no longer depend on ambient step injection
- worker execution logic does not require `inngest.Context`
- the remaining Inngest usage is localized to the worker-execution runner itself

Assessment:

- this was previously one of the clearest architectural violations
- that violation is now materially addressed

## Remaining Coupling Hotspots

The remaining issues are no longer "Inngest leaks everywhere."

They are now concentrated in a few orchestration modules.

## 1. `workflow_start.py`

Path:

- `h_arcane/core/_internal/task/inngest_functions/workflow_start.py`

### Why it still stands out

This runner still owns too much of the meaning of "starting a workflow."

It currently performs:

- experiment loading
- task tree parsing
- initial task state creation
- evaluator record creation
- run status transition to executing
- initial ready-task identification
- dashboard pending/ready state emission
- `TaskReadyEvent` emission

This is workable, but it is still a thick orchestration module that also acts like an application service.

### Current health

- works today: yes
- final architecture quality: not good enough
- overly coupled to Inngest: somewhat
- urgency: medium-high

### What should happen next

Extract a `WorkflowInitializationService`.

The service should own:

- loading/validating the workflow initialization context
- initializing task state records
- creating evaluator bindings
- computing initial ready tasks
- returning structured data needed by the runner

The runner should own:

- deserializing `WorkflowStartedEvent`
- calling the service inside durable steps
- emitting dashboard started/pending/ready events
- emitting `TaskReadyEvent` for initial tasks

### Suggested DTOs

- `InitializeWorkflowCommand`
- `InitializedWorkflow`
- `InitialReadyTasks`

Suggested service outputs should include:

- dependency count
- evaluator count
- workflow display metadata needed by dashboard emission
- initial ready task IDs
- task name/parent metadata for ready events

## 2. `task_propagate.py`

Path:

- `h_arcane/core/_internal/task/inngest_functions/task_propagate.py`

### Why it still stands out

This runner still owns too much of the meaning of "a task finished, now advance the workflow."

It currently performs:

- task tree lookup for names and parents
- propagation via `on_task_completed(...)`
- workflow terminal checks
- `TaskReadyEvent` emission
- dashboard ready emission
- workflow terminal event branching

The propagation logic itself already lives in a domain-ish helper, but the runner still bundles too much coordination logic.

### Current health

- works today: yes
- final architecture quality: not good enough
- overly coupled to Inngest: somewhat
- urgency: high

### What should happen next

Extract a `TaskPropagationService` or `WorkflowProgressService`.

The service should own:

- running propagation after task completion
- loading task metadata needed for follow-up orchestration
- deciding whether the workflow is complete or failed
- returning explicit follow-up instructions/results

The runner should own:

- deserializing `TaskCompletedEvent`
- calling the service in durable steps
- emitting newly-ready `TaskReadyEvent`s
- emitting dashboard ready changes
- emitting `WorkflowCompletedEvent` or `WorkflowFailedEvent`

### Suggested DTOs

- `PropagateTaskCompletionCommand`
- `PropagationResult`
- `ReadyTaskDescriptor`
- `WorkflowTerminalState`

Suggested service outputs should include:

- newly ready task IDs
- ready-task display metadata
- workflow terminal status
- enough metadata for the runner to emit follow-up events without re-querying

## 3. `benchmark_run_start.py`

Path:

- `h_arcane/core/_internal/task/inngest_functions/benchmark_run_start.py`

### Why it is different

This file is not primarily a classic "business logic mixed into runner" problem.

Instead, it is a bootstrap/infrastructure path that still has unusual coupling because:

- it reconstructs workers inside the Inngest container
- it stores workers in process memory
- it persists workflow state
- it kicks off the standard workflow-start path

This is not necessarily wrong, but it is still a special-case operational boundary.

### Current health

- acceptable as a bootstrap path: mostly yes
- architecturally elegant: no
- same urgency as `workflow_start.py` / `task_propagate.py`: no
- urgency: medium

### What should happen next

Treat this as a separate architecture track:

- either accept it as infrastructure bootstrap glue
- or design a more explicit worker/bootstrap registry boundary so this function does not need to mix reconstruction, persistence, and orchestration kickoff in one place

This should not block cleanup of the remaining thick workflow/task runners.

## 4. `task_run.py`

Path:

- `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`

### Why it is mostly okay

This runner is much better than before.

It now:

- creates a framework-local `InngestCriterionExecutor`
- delegates rubric evaluation to `RubricEvaluationService`
- persists criterion and task-evaluation records in explicit steps

This is no longer a major architectural smell.

### Remaining question

If we want very strict consistency, we could move persistence behind a service as well.

But compared with the remaining issues in `workflow_start.py` and `task_propagate.py`, this is lower priority.

### Current health

- healthy enough: yes
- primary cleanup target: no
- urgency: low

## Recommended Next Wave

If we continue the cleanup, the best next wave is:

1. extract `WorkflowInitializationService` from `workflow_start.py`
2. extract `TaskPropagationService` from `task_propagate.py`
3. decide whether `benchmark_run_start.py` should remain accepted infrastructure glue or get its own bootstrap redesign

This order is recommended because:

- `workflow_start.py` and `task_propagate.py` are now the clearest remaining thick runners in the main workflow path
- cleaning them up would make the workflow lifecycle consistently runner-thin
- `benchmark_run_start.py` is important, but it is a separate kind of problem

## Suggested Boundaries For The Next Wave

## `WorkflowInitializationService`

### Runner owns

- parse `WorkflowStartedEvent`
- call service in explicit durable steps
- emit dashboard workflow-started signal
- emit initial `TaskReadyEvent`s
- emit dashboard pending/ready signals if they remain runner-owned

### Service owns

- loading experiment / task tree
- initializing task-state event log
- creating `TaskEvaluator` records
- computing initial ready tasks
- returning task metadata needed for orchestration follow-up

## `TaskPropagationService`

### Runner owns

- parse `TaskCompletedEvent`
- call service in explicit durable steps
- emit task-ready events
- emit dashboard ready signals
- emit workflow terminal events

### Service owns

- propagation after completion
- workflow terminal checks
- task metadata lookups needed by the runner
- follow-up planning result returned as DTOs

## What "Done" Would Look Like After The Next Wave

If the next wave lands successfully, the main workflow path would look like this:

- `workflow_start.py`
  - orchestration only
- `task_execute.py`
  - orchestration only
- `task_propagate.py`
  - orchestration only
- `check_evaluators.py`
  - orchestration plus evaluator status mutation only
- `workflow_complete.py`
  - orchestration only

At that point, the remaining Inngest coupling would be mostly where it should be:

- function triggers
- durable step boundaries
- child invokes
- event emission
- infrastructure adapters like `InngestCriterionExecutor`

That would be much closer to the target rule:

- runners orchestrate
- services execute business logic
- domain interfaces remain framework-agnostic

## Recommendation

The current state is good enough that we should not treat Inngest coupling as an emergency anymore.

But if we want the cleanup to feel finished rather than partially improved, the next two files to attack are clearly:

1. `workflow_start.py`
2. `task_propagate.py`

Those are now the main places where orchestration and service responsibilities are still too blended.
