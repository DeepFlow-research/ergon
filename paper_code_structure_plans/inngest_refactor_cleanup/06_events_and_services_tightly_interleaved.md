# Violation F: Event DTOs And Service Responsibilities Are Interleaved

## Problem

Event payloads, service commands, and handler internals are currently too tightly mixed together.

The result is that event schemas are doing double duty as internal service APIs, and handlers are doing too much translation and execution work at once.

## Trace Of The Violation

### Task-side examples

- `h_arcane/core/_internal/task/requests.py`
- `h_arcane/core/_internal/task/inngest_functions/task_execute.py`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`

`requests.py` models are described as child Inngest function inputs, but in practice they are also shaping the internal execution boundary.

### Evaluation-side examples

- `h_arcane/core/_internal/evaluation/events.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/check_evaluators.py`

The same event DTOs are being used directly all the way down the stack, so orchestration contracts and service contracts are not clearly separated.

## Why This Is Bad

- Event payload evolution becomes harder.
- Internal services become less reusable.
- It is harder to tell what is a transport contract vs an application contract.
- Reviewers have to mentally separate three layers that currently share the same objects.

## Proposed Fix

Introduce three explicit DTO layers:

- event DTOs
- service commands/results
- domain models

The handler should translate from event DTOs to service commands. That translation is a good thing, not wasted indirection.

## Specific Code Changes

### File: `h_arcane/core/_internal/task/services/dto.py`

#### Change

- add service-specific command/result objects that are not event-shaped

#### Diff sketch

```diff
+ from pydantic import BaseModel
+ from uuid import UUID
+
+ class PrepareTaskExecutionCommand(BaseModel):
+     run_id: UUID
+     experiment_id: UUID
+     task_id: UUID
+
+ class PreparedTaskExecution(BaseModel):
+     run_id: UUID
+     experiment_id: UUID
+     task_id: UUID
+     execution_id: UUID
+     benchmark_name: str
+     task_description: str
+     input_resource_ids: list[UUID]
```

### File: `h_arcane/core/_internal/task/inngest_functions/task_execute.py`

#### Change

- stop using `TaskReadyEvent` as the internal service boundary
- map it into a service command

#### Diff sketch

```diff
 from h_arcane.core._internal.task.events import TaskReadyEvent
+ from h_arcane.core._internal.task.services.dto import PrepareTaskExecutionCommand

 payload = TaskReadyEvent.model_validate(ctx.event.data)
- # use payload directly throughout the whole handler
+ command = PrepareTaskExecutionCommand(
+     run_id=UUID(payload.run_id),
+     experiment_id=UUID(payload.experiment_id),
+     task_id=UUID(payload.task_id),
+ )
+ prep = await ctx.step.run(
+     "prepare-task-execution",
+     lambda: service.prepare(command),
+     output_type=PreparedTaskExecution,
+ )
```

### File: `h_arcane/core/_internal/evaluation/services/dto.py`

#### Change

- add evaluation service DTOs separate from `TaskEvaluationEvent`

#### Diff sketch

```diff
+ from pydantic import BaseModel
+ from uuid import UUID
+ from h_arcane.core._internal.db.models import ResourceRecord
+ from h_arcane.benchmarks.types import AnyRubric
+
+ class EvaluateTaskCommand(BaseModel):
+     run_id: UUID
+     task_input: str
+     agent_reasoning: str
+     agent_outputs: list[ResourceRecord]
+     rubric: AnyRubric
```

### File: `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`

#### Change

- map `TaskEvaluationEvent` into `EvaluateTaskCommand`
- let the service operate on the service DTO

#### Diff sketch

```diff
 payload = TaskEvaluationEvent.model_validate(ctx.event.data)
- context = TaskEvaluationContext(...)
- result = await service.evaluate(context, payload.rubric)
+ command = EvaluateTaskCommand(
+     run_id=UUID(payload.run_id),
+     task_input=payload.task_input,
+     agent_reasoning=payload.agent_reasoning,
+     agent_outputs=payload.agent_outputs,
+     rubric=payload.rubric,
+ )
+ result = await service.evaluate(command)
```

## What To Leave As Event DTOs

The following should remain event DTOs:

- `TaskReadyEvent`
- `TaskCompletedEvent`
- `WorkflowCompletedEvent`
- `BenchmarkRunRequest`
- `TaskEvaluationEvent`
- `CriterionEvaluationEvent`

These belong to orchestration.

What should move away from them is internal service logic, not the event definitions themselves.

## Acceptance Criteria

- Event DTOs are used at handler boundaries, not as the main internal service API.
- New service DTOs exist in service modules.
- Reviewers can clearly see where translation happens.
- Changing an event schema does not imply changing service-layer internals one-for-one.

## Notes

This is the least glamorous cleanup, but it reduces architectural confusion everywhere else. It should happen early because it gives the later refactors a cleaner seam to land on.
