# Violation E: `step.run(...)` Is Shaping Service APIs

## Problem

Several handlers are structured around Inngest durability boundaries instead of around reusable application service boundaries.

Using `step.run(...)` inside handlers is not itself a problem. The problem is when it becomes the reason the internal API looks the way it does.

## Trace Of The Violation

### Files most affected

- `h_arcane/core/_internal/task/inngest_functions/task_execute.py`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/check_evaluators.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`
- `h_arcane/core/_internal/agents/step_outputs.py`
- `h_arcane/core/_internal/evaluation/step_outputs.py`

### Symptoms

- business logic is inline in handlers
- comments are written in terms of step mechanics rather than service responsibilities
- step output wrapper models exist because the orchestration layer is also acting as the service layer

## Why This Is Bad

- Runners become thick and hard to reason about.
- Core logic is harder to call outside Inngest.
- The boundary between orchestration and business logic becomes blurry.
- Durable boundaries start dictating function decomposition rather than wrapping it.

## Proposed Fix

Extract explicit application services.

Then let Inngest handlers wrap those services in durable boundaries.

The guiding pattern should be:

- parse event
- build service command
- call service inside `step.run(...)` where needed
- emit next event(s)

## Specific Code Changes

### File: `h_arcane/core/_internal/task/inngest_functions/task_execute.py`

#### Change

- extract preparation/finalization logic into a `TaskExecutionService`
- keep `step.invoke(...)` for orchestration of child runners
- stop using the handler as the main service implementation

#### Diff sketch

```diff
+ from h_arcane.core._internal.task.services.task_execution_service import (
+     TaskExecutionService,
+ )
+ from h_arcane.core._internal.task.services.dto import (
+     PrepareTaskExecutionCommand,
+     PreparedTaskExecution,
+ )

 async def task_execute(ctx: inngest.Context) -> TaskExecuteResult:
     payload = TaskReadyEvent.model_validate(ctx.event.data)
-    # loads context, parses tree, loads resources, creates execution,
-    # emits status, invokes children, handles success/failure inline
+
+    service = TaskExecutionService()
+    command = PrepareTaskExecutionCommand(
+        run_id=UUID(payload.run_id),
+        experiment_id=UUID(payload.experiment_id),
+        task_id=UUID(payload.task_id),
+    )
+
+    prep = await ctx.step.run(
+        "prepare-task-execution",
+        lambda: service.prepare(command),
+        output_type=PreparedTaskExecution,
+    )
+
+    sandbox_result = await ctx.step.invoke(...)
+    worker_result = await ctx.step.invoke(...)
+    persist_result = await ctx.step.invoke(...)
+
+    return await ctx.step.run(
+        "finalize-task-execution",
+        lambda: service.finalize(prep, worker_result, persist_result),
+        output_type=TaskExecuteResult,
+    )
```

### File: `h_arcane/core/_internal/evaluation/inngest_functions/check_evaluators.py`

#### Change

- extract evaluator discovery/dispatch logic into a service

#### Diff sketch

```diff
+ from h_arcane.core._internal.evaluation.services.evaluator_dispatch_service import (
+     EvaluatorDispatchService,
+ )

 async def check_and_run_evaluators(ctx: inngest.Context) -> EvaluatorsResult:
     payload = TaskCompletedEvent.model_validate(ctx.event.data)
-    # load evaluators, filter, mutate statuses, invoke task evaluators inline
+    service = EvaluatorDispatchService(task_evaluation_invoker=InngestTaskEvaluationInvoker(ctx))
+    return await ctx.step.run(
+        "dispatch-evaluators",
+        lambda: service.dispatch(payload),
+        output_type=EvaluatorsResult,
+    )
```

### File: `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`

#### Change

- let the handler orchestrate and persist
- let a service own evaluation business flow

#### Diff sketch

```diff
+ from h_arcane.core._internal.evaluation.services.task_evaluation_service import (
+     TaskEvaluationService,
+ )

 async def evaluate_task_run(ctx: inngest.Context) -> TaskEvaluationResult:
     payload = TaskEvaluationEvent.model_validate(ctx.event.data)
     context = TaskEvaluationContext(...)
-    result = await payload.rubric.compute_scores(context, ctx)
+    service = TaskEvaluationService(criterion_executor=InngestCriterionExecutor(ctx))
+    result = await ctx.step.run(
+        "evaluate-task",
+        lambda: service.evaluate(context, payload.rubric),
+        output_type=TaskEvaluationResult,
+    )
```

## What To Do With `step_outputs.py`

### Files

- `h_arcane/core/_internal/agents/step_outputs.py`
- `h_arcane/core/_internal/evaluation/step_outputs.py`

These files are hints that internal service contracts are being defined from the perspective of step mechanics.

### Proposed direction

- do not immediately delete them
- replace them gradually with service-layer DTOs
- once service extraction is done, delete wrappers that only exist for `step.run(...)`

## Acceptance Criteria

- handlers are visibly thinner
- business logic is callable without an Inngest context
- `step.run(...)` wraps service calls rather than defining service structure
- service DTOs exist outside step-specific helper files

## Notes

This file is mostly about code organization discipline. It is less flashy than the worker/rubric changes, but it is what makes those changes stick.
