# Current Inngest Orchestration Call Stack

This document describes the current backend orchestration flow that uses Inngest in `arcane_extension`.

It covers:

- backend registration and bootstrapping
- workflow and task execution orchestration
- agent execution and sandbox lifecycle
- evaluation orchestration
- cleanup/finalization
- dashboard event emission as a parallel observability stream

## 1. Registration And Entry Points

### Inngest server wiring

- `h_arcane/core/_internal/infrastructure/inngest_client.py`
  - Creates the shared `inngest_client`.
  - Configures `app_id`, event key, base URL, and serializer.

- `h_arcane/core/_internal/api/main.py`
  - Registers all Inngest functions with FastAPI via `inngest.fast_api.serve(...)`.

- `h_arcane/core/_internal/inngest_registry.py`
  - Central registry of all backend Inngest functions:
    - `benchmark_run_start`
    - `workflow_start`
    - `task_execute`
    - `task_propagate`
    - `workflow_complete`
    - `workflow_failed`
    - `sandbox_setup_fn`
    - `worker_execute_fn`
    - `persist_outputs_fn`
    - `check_and_run_evaluators`
    - `evaluate_task_run`
    - `evaluate_criterion_fn`
    - `run_cleanup`

## 2. Event Contracts

### Task/workflow execution events

Defined in `h_arcane/core/_internal/task/events.py`:

- `workflow/started`
- `task/ready`
- `task/started` (observability only, not currently a trigger)
- `task/completed`
- `task/failed`
- `workflow/completed`
- `workflow/failed`
- `benchmark/run-request`

### Evaluation events

Defined in `h_arcane/core/_internal/evaluation/events.py`:

- `task/evaluate`
- `criterion/evaluate`

### Infrastructure cleanup events

- `RunCleanupEvent` is used by the cleanup pipeline.
- Emitted by workflow terminal handlers and consumed by `run_cleanup`.

### Dashboard observability events

Defined in `h_arcane/core/dashboard/events.py`:

- `dashboard/workflow.started`
- `dashboard/workflow.completed`
- `dashboard/task.status_changed`
- `dashboard/agent.action_started`
- `dashboard/agent.action_completed`
- `dashboard/resource.published`
- `dashboard/sandbox.created`
- `dashboard/sandbox.command`
- `dashboard/sandbox.closed`

These do not drive orchestration. They mirror orchestration state to the dashboard.

## 3. Primary SDK/API Execution Flow

### Synchronous handoff into Inngest

The user-facing entry point is `h_arcane/core/runner.py::execute_task()`.

`execute_task()` does local setup first:

1. validates the DAG
2. stores workers in process memory
3. builds/persists experiment + run + task tree
4. persists agent mapping data
5. emits `workflow/started`
6. polls the DB until the run reaches a terminal state

At that point, orchestration is running inside Inngest.

## 4. Workflow Start Orchestration

### Trigger

- Event: `workflow/started`
- Handler: `h_arcane/core/_internal/task/inngest_functions/workflow_start.py`

### What `workflow_start` does

1. Loads the persisted experiment and task tree.
2. Initializes DAG task states in the database.
3. Creates task evaluator records.
4. Marks the run as executing.
5. Emits dashboard workflow started state.
6. Computes the initial ready tasks.
7. Emits `task/ready` for each initial task in parallel with `ctx.group.parallel(...)`.

### Important side effect

While initializing the DAG, `workflow_start` also emits dashboard task status updates for:

- initial `PENDING`
- initial `READY` tasks

So from the start of a run, there are two streams:

- the control stream: task/workflow events for execution
- the observability stream: dashboard events for UI state

## 5. Task Execution Orchestration

### Trigger

- Event: `task/ready`
- Handler: `h_arcane/core/_internal/task/inngest_functions/task_execute.py`

### What `task_execute` does

For each ready leaf task:

1. Loads run and experiment context.
2. Parses the task tree and resolves the task node.
3. Skips composite tasks early.
4. Loads input resources.
5. Creates a task execution record.
6. Marks the task as running.
7. Emits dashboard task-running state.
8. Invokes the child functions:
   - `sandbox_setup_fn`
   - `worker_execute_fn`
   - `persist_outputs_fn`
9. On success:
   - completes the execution record
   - emits `task/completed`
   - emits dashboard task completed state
10. On failure:
   - marks the execution failed
   - emits `task/failed`
   - emits dashboard task failed state

This is the central task orchestrator.

## 6. Task Child Functions

### 6.1 `sandbox_setup_fn`

- File: `h_arcane/core/_internal/task/inngest_functions/sandbox_setup.py`
- Trigger: `SandboxSetupRequest`

Responsibilities:

1. resolve the benchmark-specific sandbox manager
2. create the sandbox
3. prepare the output directory
4. store sandbox metadata on the run
5. return `sandbox_id` and output directory info

### 6.2 `worker_execute_fn`

- File: `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
- Trigger: `WorkerExecuteRequest`

Responsibilities:

1. load run, experiment, and input resources
2. resolve benchmark-specific factories:
   - sandbox manager
   - stakeholder factory
   - toolkit factory
   - skills directory
3. create stakeholder and toolkit
4. prepare sandbox state for the task
5. rehydrate the worker from in-memory worker context
6. get/create worker agent config
7. link the task execution to the agent
8. get/create stakeholder agent config
9. call `set_step(ctx.step)` for durable step-aware tooling
10. execute `worker.execute(task, context)`
11. persist resulting actions
12. emit dashboard agent action completion events
13. return `WorkerExecuteResult`

This is the actual agent execution point in the stack.

### 6.3 `persist_outputs_fn`

- File: `h_arcane/core/_internal/task/inngest_functions/persist_outputs.py`
- Trigger: `PersistOutputsRequest`

Responsibilities:

1. download output files from the sandbox
2. register them as `ResourceRecord`s
3. emit dashboard resource events
4. return output resource IDs

## 7. DAG Propagation After Task Completion

### Trigger

- Event: `task/completed`
- Handler: `h_arcane/core/_internal/task/inngest_functions/task_propagate.py`

### What `task_propagate` does

1. updates dependency state via `on_task_completed(...)`
2. computes newly unblocked tasks
3. emits `task/ready` for each newly ready task in parallel
4. emits dashboard task-ready state for those tasks
5. checks if the workflow is now terminal
6. emits:
   - `workflow/completed` if the DAG is done successfully
   - `workflow/failed` if the workflow should fail

This is the fanout step that keeps the DAG moving.

## 8. Workflow Terminal Handlers

### 8.1 `workflow_complete`

- File: `h_arcane/core/_internal/task/inngest_functions/workflow_complete.py`
- Trigger: `workflow/completed`

Responsibilities:

1. mark the run completed
2. aggregate task scores from task evaluators
3. aggregate total action cost
4. build per-task `TaskResult`s
5. build the final `ExecutionResult`
6. persist run-level completion data
7. create a run-level `Evaluation` record when evaluation data exists
8. emit dashboard workflow completed state
9. emit `RunCleanupEvent`

### 8.2 `workflow_failed`

- File: `h_arcane/core/_internal/task/inngest_functions/workflow_failed.py`
- Trigger: `workflow/failed`

Responsibilities:

1. mark the run failed
2. build a failed `ExecutionResult`
3. persist failure metadata
4. emit `RunCleanupEvent`
5. emit dashboard workflow failed state

## 9. Evaluation Orchestration

Evaluation is not embedded directly in `task_execute`.

Instead, it is event-driven and hangs off `task/completed`.

### 9.1 Evaluation fanout trigger

- Event: `task/completed`
- Handler: `h_arcane/core/_internal/evaluation/inngest_functions/check_evaluators.py`

### What `check_and_run_evaluators` does

1. queries evaluator records for the completed task
2. loads the latest task execution and outputs
3. reconstructs the evaluation context:
   - task input
   - agent reasoning
   - agent outputs
   - rubric
4. marks valid evaluators as running
5. invokes `evaluate_task_run` for each evaluator in parallel
6. marks evaluator records completed or failed

Important note:

`task/completed` has multiple subscribers:

- `task_propagate` for execution flow
- `check_and_run_evaluators` for evaluation flow

That means task progression and evaluation are decoupled but synchronized on the same lifecycle event.

### 9.2 Task-level evaluation

- File: `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`
- Trigger: `task/evaluate`
- Handler: `evaluate_task_run`

Responsibilities:

1. deserialize `TaskEvaluationEvent`
2. build `TaskEvaluationContext`
3. delegate scoring to `payload.rubric.compute_scores(context, ctx)`
4. persist all `CriterionResult`s
5. persist a `TaskEvaluationResult`
6. return the aggregate evaluation result

This function is the task-level evaluation orchestrator.

### 9.3 Criterion-level evaluation

- File: `h_arcane/core/_internal/evaluation/inngest_functions/criterion.py`
- Trigger: `criterion/evaluate`
- Handler: `evaluate_criterion_fn`

Responsibilities:

1. deserialize `CriterionEvaluationEvent`
2. resolve benchmark-specific sandbox manager
3. build an `EvaluationRunner`
4. call `payload.rule.evaluate(runner)`
5. cleanup the evaluation sandbox if needed
6. return `CriterionResult`

This is the leaf evaluator for an individual scoring rule.

## 10. How Rubrics Use Inngest Internally

Rubrics do not just compute everything inline. Several benchmark rubric implementations use Inngest to fan out per-criterion evaluation work.

### GDPEval

- File: `h_arcane/benchmarks/gdpeval/rubric.py`

`StagedRubric.compute_scores(...)`:

1. flattens staged rubric criteria
2. builds `CriterionEvaluationEvent` payloads
3. invokes `evaluate_criterion_fn` in parallel with `inngest_ctx.step.invoke(...)`
4. waits on `inngest_ctx.group.parallel(...)`
5. rebuilds stage results
6. applies staged gate logic
7. returns a `TaskEvaluationResult`

### Smoke test

- File: `h_arcane/benchmarks/smoke_test/rubric.py`

`SmokeTestRubric.compute_scores(...)`:

1. serializes rules
2. creates criterion-evaluation invokers
3. invokes `evaluate_criterion_fn` for each rule in parallel
4. aggregates the resulting scores
5. returns a `TaskEvaluationResult`

### ResearchRubrics

- File: `h_arcane/benchmarks/researchrubrics/rubric.py`

`ResearchRubricsRubric.compute_scores(...)`:

1. converts criteria into `LLMJudgeRule`s
2. builds `CriterionEvaluationEvent` payloads
3. invokes `evaluate_criterion_fn` in parallel
4. aggregates weighted scores
5. returns a `TaskEvaluationResult`

## 11. EvaluationRunner As Step-Level Infra

- File: `h_arcane/core/_internal/evaluation/runner.py`

`EvaluationRunner` is not itself an Inngest function, but it is built to run inside Inngest contexts.

Its purpose is to wrap evaluation operations in `ctx.step.run(...)` so evaluation work gets:

- durable step boundaries
- per-step tracing
- retryable boundaries where appropriate
- timing/observability in Inngest

It supports:

- sandbox provisioning
- file upload to evaluation sandboxes
- code execution in sandbox
- LLM judge calls
- cleanup

## 12. Cleanup Orchestration

### Trigger

- Event: `RunCleanupEvent`
- Handler: `h_arcane/core/_internal/infrastructure/inngest_functions/run_cleanup.py`

### What `run_cleanup` does

1. loads the run
2. terminates the sandbox by stored sandbox ID if present
3. clears sandbox metadata from the run
4. verifies or corrects final run status
5. persists the final cleanup state

This is the last infrastructure step in the orchestration chain.

## 13. Benchmark CLI Entry Path

There is a second orchestration entry point used by benchmark CLIs.

### Trigger

- Event: `benchmark/run-request`
- Handler: `h_arcane/core/_internal/task/inngest_functions/benchmark_run_start.py`

### Why it exists

The CLI may run outside the same process/container as the backend Inngest worker. Since workers are stored in-memory for later retrieval by `worker_execute_fn`, the system reconstructs workers server-side through an Inngest function so both initialization and execution happen in the same process context.

### What `benchmark_run_start` does

1. parses the benchmark request
2. resolves benchmark worker config
3. creates a `ReActWorker`
4. resolves the benchmark workflow factory
5. builds the workflow task tree
6. validates the DAG
7. stores workers in memory
8. persists the workflow and run
9. emits `workflow/started`
10. returns the created run metadata

You can see this event being emitted from `h_arcane/benchmarks/smoke_test/cli.py`.

## 14. Dashboard Event Side Channel

The backend also emits a separate stream of Inngest events for live dashboard visualization.

- emitter: `h_arcane/core/dashboard/emitter.py`
- contracts: `h_arcane/core/dashboard/events.py`

These are emitted from the execution and evaluation flow to mirror state changes such as:

- workflow started/completed
- task status transitions
- action completion
- resource publication
- sandbox lifecycle

These events are consumed by the dashboard app and are not required to drive backend control flow.

## 15. Full Call Stack Summary

### Standard SDK/API path

1. `execute_task()`
2. emit `workflow/started`
3. `workflow_start`
4. emit one or more `task/ready`
5. `task_execute`
6. invoke:
   - `sandbox_setup_fn`
   - `worker_execute_fn`
   - `persist_outputs_fn`
7. emit `task/completed` or `task/failed`
8. `task_propagate`
9. emit more `task/ready` events as dependencies clear
10. emit `workflow/completed` or `workflow/failed`
11. `workflow_complete` or `workflow_failed`
12. emit `RunCleanupEvent`
13. `run_cleanup`

### Evaluation path hanging off task completion

1. `task/completed`
2. `check_and_run_evaluators`
3. invoke one or more `evaluate_task_run`
4. inside rubric `compute_scores(...)`, invoke one or more `evaluate_criterion_fn`
5. persist criterion results
6. persist task evaluation result
7. later, `workflow_complete` aggregates completed evaluator scores into final run data

### Dashboard side channel

Execution functions and supporting components emit `dashboard/*` events in parallel to update the live dashboard.

## 16. Mental Model

The current architecture uses Inngest in three different ways at once:

1. as the control plane for workflow/task orchestration
2. as the fanout engine for evaluation work
3. as the transport layer for dashboard observability events

The most important design pattern in the codebase is:

- persist run state first
- emit an event
- let one or more Inngest subscribers react to that event
- keep execution, evaluation, and dashboard concerns loosely coupled

## 17. PRD: Decouple Core Logic From Inngest

### Background

The current system uses Inngest for both:

1. orchestration of workflow state transitions
2. execution-time instrumentation and durability inside core business logic

That second use has created architectural tension.

We originally wanted Inngest to be our main source of observability for internal operations like:

- sandbox setup
- worker execution
- evaluation fanout
- criterion/rule execution

But in practice, this has pushed Inngest concepts down into the core execution model:

- core abstractions accept `inngest.Context`
- benchmark rubric logic knows how to `step.invoke(...)`
- worker/tool execution depends on dynamically injected step context
- business logic correctness partly depends on Inngest's "only code inside `step.run` is durable" semantics

This mixes orchestration concerns with domain execution in a way that makes the system harder to reason about and more failure-prone.

### Problem Statement

The current implementation violates the intended separation of concerns:

- Inngest runners are not thin orchestration adapters.
- Core execution and evaluation code is coupled to Inngest APIs and lifecycle semantics.
- Some correctness and idempotency assumptions depend on whether logic is wrapped in `step.run(...)`.
- The architecture is biased toward "making internal work show up in Inngest" rather than keeping core code framework-agnostic.

This has likely contributed to bugs where:

- logic before or after `step.run(...)` is not replay-safe
- side effects happen outside durable boundaries
- code correctness depends on ordering around `ctx.step.*`
- internal classes are difficult to test outside an Inngest context
- domain abstractions silently become orchestration abstractions

### Product Goal

Refactor the execution architecture so that:

- the core majority of logic is fully independent of Inngest
- Inngest runners are thin orchestration wrappers
- domain interfaces/classes are not coupled to `inngest.Context`, `ctx.step`, or `inngest_agents`
- event-driven architecture remains the main orchestration pattern
- we still retain good observability, but through explicit domain events and traces rather than framework leakage

### Non-Goals

This cleanup does not require:

- removing Inngest entirely
- removing event-driven workflow orchestration
- eliminating all asynchronous fanout
- rewriting the whole pipeline in one PR

It is acceptable to keep:

- event-driven fanout such as `task/completed -> evaluation`
- Inngest for workflow subscribers and orchestration
- `ctx.step.invoke(...)` at runner boundaries where one orchestration function calls another orchestration function

### Desired Architectural Principle

The desired rule is:

- Inngest owns orchestration boundaries.
- Domain/application services own business logic.
- Domain/application services may emit domain events and traces.
- Inngest runners translate events into service calls and service outcomes back into events.

The desired anti-rule is:

- domain logic must not know whether it is being executed inside Inngest

## 18. Current Violations

This section lists the current places where we are violating that rule.

### Violation A: Rubric interfaces depend on `inngest.Context`

Files:

- `h_arcane/core/_internal/evaluation/base.py`
- `h_arcane/benchmarks/gdpeval/rubric.py`
- `h_arcane/benchmarks/smoke_test/rubric.py`
- `h_arcane/benchmarks/researchrubrics/rubric.py`
- `h_arcane/benchmarks/minif2f/rubric.py`

Why this is a violation:

- `BaseRubric.compute_scores(...)` currently requires `inngest_ctx: inngest.Context`.
- That means benchmark scoring logic is no longer a pure evaluation abstraction.
- Rubrics know how to use `step.run`, `step.invoke`, and `group.parallel`.
- Rubric implementations are acting as mini-orchestrators instead of domain logic.

Why this is risky:

- evaluation logic becomes framework-coupled
- testing rubrics requires an Inngest-shaped harness
- replay and idempotency semantics leak into scoring code
- moving evaluation to another executor would require rewriting rubric code

### Violation B: `EvaluationRunner` is an Inngest-aware domain service

Files:

- `h_arcane/core/_internal/evaluation/runner.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/criterion.py`

Why this is a violation:

- `EvaluationRunner` currently requires `inngest_ctx`.
- Its public API is built around wrapping internal operations in `ctx.step.run(...)`.
- This makes the evaluation execution helper a framework-specific object instead of an application service.

Why this is risky:

- core evaluation primitives inherit Inngest lifecycle semantics
- unit testing becomes more complex
- observability concerns dominate service design

### Violation C: Worker execution depends on dynamically injected Inngest step context

Files:

- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
- `h_arcane/benchmarks/common/workers/react_worker.py`

Why this is a violation:

- `worker_execute_fn` calls `set_step(ctx.step)`.
- `ReActWorker` wraps tools with `inngest_agents.as_step(...)`.
- This means worker execution depends on a dynamically installed Inngest step context.
- The worker abstraction is no longer truly independent from orchestration.

Why this is risky:

- hidden ambient context
- correctness depends on runtime setup not visible in the worker interface
- local execution and orchestration execution behave differently
- tool execution durability is coupled to framework behavior rather than explicit application logic

This is the clearest example of "execution code is wearing orchestration clothes."

### Violation D: Benchmark rubrics are orchestrating criterion fanout directly

Files:

- `h_arcane/benchmarks/gdpeval/rubric.py`
- `h_arcane/benchmarks/smoke_test/rubric.py`
- `h_arcane/benchmarks/researchrubrics/rubric.py`

Why this is a violation:

- rubrics construct `CriterionEvaluationEvent`
- rubrics invoke `evaluate_criterion_fn`
- rubrics perform `group.parallel(...)`

This means:

- the rubric layer is choosing the orchestration strategy
- the domain layer knows concrete Inngest handlers by name
- the line between "what to evaluate" and "how to schedule evaluation" is blurred

### Violation E: Core execution correctness is mixed with step durability assumptions

Files most affected:

- `h_arcane/core/_internal/task/inngest_functions/task_execute.py`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/check_evaluators.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`

Why this is a violation:

- code structure is partially shaped by "what must be inside `step.run(...)`"
- step boundaries are driving service design instead of merely wrapping it
- comments and helper models such as `step_outputs.py` encode Inngest-specific execution contracts in internal domains

This is not always wrong in runners, but it is wrong when these concerns become the reason core APIs look the way they do.

### Violation F: Event payloads and execution services are too tightly interleaved

Examples:

- `worker_execute_fn` both orchestrates and performs significant execution composition
- `check_and_run_evaluators` both discovers work and manages evaluator state mutation
- `evaluate_task_run` both orchestrates and persists domain outputs

Why this is a violation:

- some runners are still "thick"
- domain services are not consistently extracted
- it is difficult to tell what is orchestration glue vs reusable application logic

## 18A. Detailed Remediation Plan With Diff Sketches

This section expands each violation into:

- where the violation lives
- what code should change
- how it should change
- representative diff sketches

These are planning diffs, not exact final patches. They are intended to make the migration concrete.

### Violation A Remediation: Remove `inngest.Context` from rubric APIs

#### Where the violation is

- `h_arcane/core/_internal/evaluation/base.py`
- `h_arcane/benchmarks/gdpeval/rubric.py`
- `h_arcane/benchmarks/smoke_test/rubric.py`
- `h_arcane/benchmarks/researchrubrics/rubric.py`
- `h_arcane/benchmarks/minif2f/rubric.py`

#### What code should change

Change rubric APIs from:

- "rubric computes scores by directly orchestrating execution through Inngest"

To:

- "rubric describes the evaluation work and aggregate logic"

Concretely:

1. remove `inngest.Context` from `BaseRubric`
2. replace `compute_scores(context, inngest_ctx)` with a framework-agnostic API
3. move fanout/execution out of rubric classes

#### How it should change

Introduce a plan-based rubric API:

- `build_plan(context) -> EvaluationPlan`
- `aggregate(context, criterion_results) -> TaskEvaluationResult`

This lets rubrics remain owners of:

- criterion definition
- score aggregation
- benchmark-specific evaluation semantics

But not owners of:

- how work is executed
- whether work is parallelized
- whether Inngest is used

#### Diff sketch: `evaluation/base.py`

```diff
- import inngest
+ from typing import Protocol

+ from h_arcane.core._internal.evaluation.plan import EvaluationPlan
+ from h_arcane.core._internal.db.models import CriterionResult

 class BaseRubric(Protocol):
     benchmark: str

-    async def compute_scores(
-        self,
-        context: "TaskEvaluationContext",
-        inngest_ctx: inngest.Context,
-    ) -> "TaskEvaluationResult":
-        ...
+    def build_plan(self, context: "TaskEvaluationContext") -> EvaluationPlan:
+        ...
+
+    def aggregate(
+        self,
+        context: "TaskEvaluationContext",
+        criterion_results: list[CriterionResult],
+    ) -> "TaskEvaluationResult":
+        ...
```

#### Diff sketch: new `evaluation/plan.py`

```diff
+ from pydantic import BaseModel
+ from h_arcane.benchmarks.types import AnyRule
+
+ class CriterionSpec(BaseModel):
+     benchmark_name: str
+     stage_name: str
+     stage_idx: int
+     rule_idx: int
+     max_score: float
+     rule: AnyRule
+
+ class EvaluationPlan(BaseModel):
+     criteria: list[CriterionSpec]
```

#### Diff sketch: representative rubric change in `gdpeval/rubric.py`

```diff
- import inngest
  from pydantic import BaseModel, Field
+ from h_arcane.core._internal.evaluation.plan import CriterionSpec, EvaluationPlan

- async def compute_scores(
-     self,
-     context: "TaskEvaluationContext",
-     inngest_ctx: inngest.Context,
- ) -> TaskEvaluationResult:
-     ...
-     criterion_results_tuple = await inngest_ctx.group.parallel(parallel_invokers)
-     ...
-     return TaskEvaluationResult(...)
+ def build_plan(self, context: "TaskEvaluationContext") -> EvaluationPlan:
+     criteria = []
+     for stage, rule, stage_idx, rule_idx in flatten_rubric(self):
+         criteria.append(
+             CriterionSpec(
+                 benchmark_name="gdpeval",
+                 stage_name=stage.name,
+                 stage_idx=stage_idx,
+                 rule_idx=rule_idx,
+                 max_score=rule.weight * stage.max_points,
+                 rule=rule,
+             )
+         )
+     return EvaluationPlan(criteria=criteria)
+
+ def aggregate(
+     self,
+     context: "TaskEvaluationContext",
+     criterion_results: list[CriterionResult],
+ ) -> TaskEvaluationResult:
+     stage_results = _rebuild_stage_results(criterion_results, self)
+     aggregate = _calculate_aggregate_scores(context.run_id, stage_results, self)
+     return TaskEvaluationResult(...)
```

#### Apply the same pattern to

- `smoke_test/rubric.py`
- `researchrubrics/rubric.py`
- `minif2f/rubric.py`

For `minif2f`, the change is even simpler because it is effectively a single-criterion plan.

### Violation B Remediation: Make `EvaluationRunner` framework-agnostic

#### Where the violation is

- `h_arcane/core/_internal/evaluation/runner.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/criterion.py`
- indirectly: all rules using `EvaluationRunner`

#### What code should change

Change `EvaluationRunner` from:

- a runner that requires `inngest_ctx` and wraps all operations in `step.run`

To:

- a pure application/infrastructure service with optional tracing hooks

#### How it should change

1. remove `inngest_ctx` from `EvaluationRunner.__init__`
2. remove the `step(...)` helper that delegates to `ctx.step.run(...)`
3. optionally inject a lightweight `TraceSink` interface if we still want structured spans
4. let the Inngest handler own any `step.run(...)` wrapping

#### Diff sketch: `evaluation/runner.py`

```diff
- import inngest
  from openai import AsyncOpenAI
+
+ class TraceSink(Protocol):
+     async def record(self, name: str, metadata: dict | None = None) -> None: ...

 class EvaluationRunner:
     def __init__(
         self,
         data: EvaluationData,
         sandbox_manager: BaseSandboxManager,
-        inngest_ctx: inngest.Context,
+        trace_sink: TraceSink | None = None,
         llm_model: str = "gpt-4o",
         ...
     ):
         self.data = data
         self.sandbox_manager = sandbox_manager
-        self.inngest_ctx = inngest_ctx
+        self.trace_sink = trace_sink

-    async def step(...):
-        return await self.inngest_ctx.step.run(...)
+    async def trace(self, name: str, metadata: dict | None = None) -> None:
+        if self.trace_sink is not None:
+            await self.trace_sink.record(name, metadata)
```

#### Diff sketch: `evaluation/inngest_functions/criterion.py`

```diff
 @inngest_client.create_function(...)
 async def evaluate_criterion_fn(ctx: inngest.Context) -> CriterionResult:
     payload = CriterionEvaluationEvent.model_validate(ctx.event.data)

-    runner = EvaluationRunner(data, sandbox_manager, inngest_ctx=ctx)
-    result = await payload.rule.evaluate(runner)
-    await ctx.step.run("cleanup", cleanup)
+    async def run_criterion() -> CriterionResult:
+        runner = EvaluationRunner(data, sandbox_manager)
+        try:
+            return await payload.rule.evaluate(runner)
+        finally:
+            await runner.cleanup()
+
+    result = await ctx.step.run("evaluate-criterion", run_criterion, output_type=CriterionResult)
     return result
```

This preserves Inngest visibility at the handler boundary while removing it from the runner itself.

### Violation C Remediation: Remove dynamic step injection from workers

#### Where the violation is

- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
- `h_arcane/benchmarks/common/workers/react_worker.py`
- `h_arcane/core/worker.py`

#### What code should change

Change worker execution from:

- "worker behavior depends on ambient Inngest step context"

To:

- "worker behavior depends only on explicit context and explicit observation hooks"

#### How it should change

1. remove `set_step(ctx.step)` from `worker_execute.py`
2. remove `as_step(...)` wrapping from `ReActWorker`
3. add an explicit optional observer/tracer onto `WorkerContext`
4. emit tool call lifecycle information through that observer instead of ambient Inngest APIs

#### Diff sketch: `core/worker.py`

```diff
 class WorkerContext(BaseModel):
     run_id: UUID
     task_id: UUID
     sandbox: Any = None
     input_resources: list[Resource] = Field(default_factory=list)
     metadata: dict[str, Any] = Field(default_factory=dict)
     toolkit: Any = Field(default=None)
     agent_config_id: UUID | None = None
+    tool_observer: Any = Field(
+        default=None,
+        description="Optional observer for tool lifecycle events",
+    )
```

#### Diff sketch: `worker_execute.py`

```diff
- from inngest_agents import set_step
  import inngest

 async def worker_execute_fn(ctx: inngest.Context) -> WorkerExecuteResult:
     ...
-    set_step(ctx.step)
-
     result = await _execute_worker(...)
     return result
```

#### Diff sketch: `react_worker.py`

```diff
- from inngest_agents import as_step
  from agents import Agent, Runner, function_tool

 async def execute(self, task: Task, context: WorkerContext) -> WorkerResult:
     toolkit: BaseToolkit = context.toolkit
     self.tools = toolkit.get_tools()

-    raw_tools = [
-        self._make_ask_tool(toolkit),
-        *toolkit.get_tools(),
-    ]
-    tools = [as_step(t) for t in raw_tools]
+    tools = [
+        self._make_ask_tool(toolkit, context.tool_observer),
+        *toolkit.get_tools(),
+    ]

     agent = Agent(..., tools=tools, ...)
```

#### Diff sketch: `react_worker.py` explicit ask tool hook

```diff
- def _make_ask_tool(self, toolkit: BaseToolkit):
+ def _make_ask_tool(self, toolkit: BaseToolkit, observer=None):
     @function_tool
     async def ask_stakeholder(question: str) -> str:
+        if observer:
+            await observer.on_tool_start("ask_stakeholder", {"question": question})
         answer = await toolkit.ask_stakeholder(question)
+        if observer:
+            await observer.on_tool_complete("ask_stakeholder", {"answer": answer})
         return answer
```

This makes tool observability explicit and keeps the worker runnable without Inngest.

### Violation D Remediation: Move criterion fanout out of rubrics

#### Where the violation is

- `h_arcane/benchmarks/gdpeval/rubric.py`
- `h_arcane/benchmarks/smoke_test/rubric.py`
- `h_arcane/benchmarks/researchrubrics/rubric.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`

#### What code should change

Change criterion fanout from:

- rubric-owned `step.invoke(...)` and `group.parallel(...)`

To:

- an evaluation service or orchestrator-owned fanout using a rubric-produced plan

#### How it should change

1. add an `EvaluationService` that:
   - asks rubric for `EvaluationPlan`
   - executes each `CriterionSpec`
   - passes results back to rubric aggregation
2. let `evaluate_task_run` decide whether criterion execution happens:
   - locally
   - via a `ParallelExecutor`
   - via `ctx.step.invoke(...)`
3. keep rubric code unaware of the execution strategy

#### Diff sketch: new service `evaluation/services/task_evaluation_service.py`

```diff
+ class TaskEvaluationService:
+     def __init__(self, criterion_executor):
+         self.criterion_executor = criterion_executor
+
+     async def evaluate(
+         self,
+         context: TaskEvaluationContext,
+         rubric: BaseRubric,
+     ) -> TaskEvaluationResult:
+         plan = rubric.build_plan(context)
+         criterion_results = await self.criterion_executor.execute_all(context, plan.criteria)
+         return rubric.aggregate(context, criterion_results)
```

#### Diff sketch: `evaluation/inngest_functions/task_run.py`

```diff
 async def evaluate_task_run(ctx: inngest.Context) -> TaskEvaluationResult:
     payload = TaskEvaluationEvent.model_validate(ctx.event.data)
     context = TaskEvaluationContext(...)

-    result = await payload.rubric.compute_scores(context, ctx)
+    criterion_executor = InngestCriterionExecutor(ctx)
+    service = TaskEvaluationService(criterion_executor)
+    result = await service.evaluate(context, payload.rubric)

     await ctx.step.run("persist-criterion-results", persist_criterion_results)
     await ctx.step.run("persist-task-evaluation-result", persist_task_evaluation_result)
     return result
```

#### Diff sketch: new adapter `evaluation/inngest_adapters.py`

```diff
+ class InngestCriterionExecutor:
+     def __init__(self, ctx: inngest.Context):
+         self.ctx = ctx
+
+     async def execute_all(self, context, criteria):
+         def make_invoker(spec):
+             event = CriterionEvaluationEvent(...)
+             return lambda: self.ctx.step.invoke(
+                 step_id=f"criterion-{spec.stage_idx}-{spec.rule_idx}",
+                 function=evaluate_criterion_fn,
+                 data=event.model_dump(mode="json"),
+             )
+         return list(await self.ctx.group.parallel(tuple(make_invoker(spec) for spec in criteria)))
```

This preserves event-driven fanout without letting rubrics know about it.

### Violation E Remediation: Stop letting `step.run` shape core service APIs

#### Where the violation is

- `h_arcane/core/_internal/task/inngest_functions/task_execute.py`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/check_evaluators.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`
- `h_arcane/core/_internal/agents/step_outputs.py`
- `h_arcane/core/_internal/evaluation/step_outputs.py`

#### What code should change

Change handler design from:

- "business logic split according to Inngest step durability concerns"

To:

- "business logic expressed as normal services, with handlers wrapping them in durable boundaries"

#### How it should change

1. move business logic into service modules
2. keep `ctx.step.run(...)` only around service calls or persistence side effects
3. gradually delete `step_outputs.py` files once the service layer returns normal DTOs

#### Diff sketch: `task_execute.py`

```diff
+ from h_arcane.core._internal.task.services.task_execution_service import TaskExecutionService

 async def task_execute(ctx: inngest.Context) -> TaskExecuteResult:
     payload = TaskReadyEvent.model_validate(ctx.event.data)

-    # lots of orchestration + business logic mixed together here
-    run = require_not_none(...)
-    experiment = require_not_none(...)
-    tree = parse_task_tree(...)
-    ...
-    execution = await ctx.step.run(...)
-    ...
+    service = TaskExecutionService()
+
+    prep = await ctx.step.run(
+        "prepare-task-execution",
+        lambda: service.prepare(payload),
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

#### Diff sketch: `check_evaluators.py`

```diff
+ from h_arcane.core._internal.evaluation.services.evaluator_dispatch_service import EvaluatorDispatchService

 async def check_and_run_evaluators(ctx: inngest.Context) -> EvaluatorsResult:
     payload = TaskCompletedEvent.model_validate(ctx.event.data)
-    # inline lookup, filtering, mutation, invocation orchestration
+    service = EvaluatorDispatchService(...)
+    return await ctx.step.run(
+        "dispatch-evaluators",
+        lambda: service.dispatch(payload),
+        output_type=EvaluatorsResult,
+    )
```

This keeps step durability useful without forcing handlers to become the service boundary.

### Violation F Remediation: Separate event DTOs from service DTOs

#### Where the violation is

- `h_arcane/core/_internal/task/requests.py`
- `h_arcane/core/_internal/task/inngest_functions/task_execute.py`
- `h_arcane/core/_internal/evaluation/events.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`

#### What code should change

Right now, event/request models are doing too much double duty as internal service contracts.

We should distinguish:

- event payloads
- service commands
- service results

#### How it should change

1. keep event types near the orchestrators
2. create service-layer DTOs in service modules
3. map event payloads into service commands at handler boundaries

#### Diff sketch: new task service DTOs

```diff
+ # h_arcane/core/_internal/task/services/dto.py
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

#### Diff sketch: `task_execute.py`

```diff
 from h_arcane.core._internal.task.events import TaskReadyEvent
+ from h_arcane.core._internal.task.services.dto import PrepareTaskExecutionCommand

 payload = TaskReadyEvent.model_validate(ctx.event.data)
- # use payload directly throughout handler
+ command = PrepareTaskExecutionCommand(
+     run_id=UUID(payload.run_id),
+     experiment_id=UUID(payload.experiment_id),
+     task_id=UUID(payload.task_id),
+ )
+ prep = await ctx.step.run("prepare", lambda: service.prepare(command), output_type=PreparedTaskExecution)
```

This makes event schemas clearly orchestration-only and keeps the service layer reusable.

### Ordering Recommendation

If we want the safest sequence, we should implement the above in this order:

1. Violation F
   - define clean service DTOs and boundaries first
2. Violation E
   - extract services from thick handlers
3. Violation A
   - redesign rubric interfaces
4. Violation D
   - move criterion fanout into orchestrators/services
5. Violation B
   - simplify `EvaluationRunner`
6. Violation C
   - remove ambient step injection from workers

This order minimizes churn because it first clarifies boundaries, then moves orchestration responsibilities outward, and only then rewrites the more coupled worker/evaluation internals.

## 19. Target Architecture

### Architectural layers

We should move to four explicit layers.

#### 1. Domain layer

Owns:

- task/rubric/rule/business models
- pure decisions and transformations
- no Inngest imports
- no orchestration dependencies

Examples:

- rubric scoring logic
- task graph reasoning
- aggregation logic

#### 2. Application service layer

Owns:

- imperative business workflows
- calling domain logic and infrastructure ports
- explicit inputs/outputs
- optional trace/event emission through our own interfaces
- still no `inngest.Context`

Examples:

- `TaskExecutionService`
- `WorkerExecutionService`
- `EvaluationService`
- `CriterionEvaluationService`
- `RunFinalizationService`

#### 3. Infrastructure adapter layer

Owns:

- sandbox adapters
- DB repositories
- LLM adapters
- event publishers
- tracing/telemetry emitters

These should be behind explicit interfaces where practical.

#### 4. Orchestration layer

Owns:

- Inngest handlers
- translating event payloads into service calls
- emitting follow-up events
- choosing fanout strategy
- durable step boundaries

This layer should be thin.

## 20. Proposed Refactor Direction

### Principle 1: Replace `inngest.Context` in core APIs with app-level interfaces

Introduce framework-agnostic interfaces such as:

- `TraceSink`
- `DomainEventPublisher`
- `ParallelExecutor`
- `TaskEvaluationExecutor`
- `ToolExecutionObserver`

These are examples, not final names.

The key is:

- core services depend on our interfaces
- Inngest runners provide adapters

### Principle 2: Move fanout decisions out of rubrics

Rubrics should define:

- what criteria/rules need to run
- how to aggregate results

Rubrics should not define:

- whether criteria are invoked via Inngest
- how parallelism is implemented
- what event gets emitted
- what handler name receives the work

Proposed shape:

- rubric returns an evaluation plan or criterion specs
- evaluation application service executes that plan
- orchestration layer chooses whether execution is local, threaded, async, or Inngest-backed

### Principle 3: Remove ambient step injection from workers

`ReActWorker` and tool execution should not depend on `set_step(ctx.step)` or `as_step(...)` for correctness.

Instead:

- tool execution should be explicit in the worker execution runtime
- observability for tool calls should come from explicit hooks/events
- if individual tool calls need durability, that should be mediated by a runner/executor adapter, not the worker itself

Desired outcome:

- a worker can run in a unit test, a CLI script, or an orchestrated environment with the same core semantics

### Principle 4: Keep event-driven orchestration, but only at boundaries

Good:

- `task/completed -> evaluate subscribed handler`
- `workflow/started -> workflow_start`
- `workflow/completed -> cleanup`

Bad:

- domain objects invoking Inngest functions directly
- service objects requiring `inngest.Context`
- core abstractions wrapping themselves in `step.run(...)`

## 21. Concrete Migration Plan

### Phase 1: Extract application services without changing behavior

Goal:

- pull business logic out of Inngest handlers while preserving the current event graph

Actions:

1. Extract `TaskExecutionService` from `task_execute.py`
2. Extract `WorkflowStartService` from `workflow_start.py`
3. Extract `TaskPropagationService` from `task_propagate.py`
4. Extract `WorkflowFinalizationService` from `workflow_complete.py`
5. Extract `WorkflowFailureService` from `workflow_failed.py`
6. Keep handlers as thin adapters that:
   - deserialize event
   - call service
   - emit next event(s)

Acceptance criteria:

- Inngest handlers become mostly translation/orchestration shells
- business logic is callable without `inngest.Context`

### Phase 2: Decouple evaluation APIs from Inngest

Goal:

- make evaluation/rubric logic framework-agnostic

Actions:

1. Change `BaseRubric.compute_scores(...)` to remove `inngest_ctx`
2. Introduce an evaluation execution abstraction, for example:
   - `CriterionExecutor`
   - `EvaluationExecutionContext`
3. Refactor benchmark rubrics so they produce evaluation plans or criterion specs
4. Move criterion fanout to:
   - an evaluation service, or
   - an Inngest runner dedicated to orchestration only
5. Refactor `EvaluationRunner` so it no longer requires `inngest.Context`
6. If step-level observability is still desired, provide an adapter that wraps service calls in traced steps externally

Acceptance criteria:

- benchmark rubrics import no Inngest types
- `EvaluationRunner` imports no Inngest types
- `evaluate_task_run` becomes a thin orchestrator around an application service

### Phase 3: Remove dynamic step injection from worker execution

Goal:

- worker execution is framework-independent

Actions:

1. remove `set_step(ctx.step)` from `worker_execute.py`
2. remove `inngest_agents.as_step(...)` from `ReActWorker`
3. replace ambient step durability with explicit tool-execution observation hooks
4. model tool-call tracing as domain/application events or callbacks
5. if per-tool orchestration is still needed, build it into a dedicated executor adapter, not the worker class

Acceptance criteria:

- `ReActWorker` can execute without any Inngest setup
- tool observability still exists via explicit emitted events or persisted traces

### Phase 4: Simplify event payload ownership

Goal:

- keep event payloads as orchestration contracts only

Actions:

1. keep event contracts near runners
2. move internal service request/response objects out of Inngest-focused modules where needed
3. separate:
   - domain DTOs
   - service DTOs
   - event DTOs

Acceptance criteria:

- event schemas are no longer the default internal service API
- orchestration contracts are clearly distinct from core service contracts

### Phase 5: Rebuild observability on explicit signals

Goal:

- preserve visibility without framework leakage

Actions:

1. define explicit lifecycle signals for:
   - task started/completed/failed
   - sandbox created/closed
   - tool call started/completed
   - criterion evaluation started/completed
2. publish those through a framework-agnostic event/trace sink
3. optionally have an Inngest adapter forward selected signals into dashboard/event streams
4. optionally write selected spans/logs to DB for postmortem analysis

Acceptance criteria:

- observability comes from explicit application signals
- not from forcing business logic to know about `step.run`

## 22. Suggested First Files To Change

These are the highest-leverage starting points.

### First wave

- `h_arcane/core/_internal/evaluation/base.py`
- `h_arcane/core/_internal/evaluation/runner.py`
- `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`
- `h_arcane/benchmarks/gdpeval/rubric.py`
- `h_arcane/benchmarks/smoke_test/rubric.py`
- `h_arcane/benchmarks/researchrubrics/rubric.py`
- `h_arcane/benchmarks/minif2f/rubric.py`
- `h_arcane/benchmarks/common/workers/react_worker.py`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`

### Why these first

- they contain the most direct framework leakage into core execution and evaluation
- they are the places most likely to be causing "correctness depends on step semantics"
- cleaning them up will establish the architecture we want for the rest of the codebase

## 23. Proposed "Good" End State

In the desired future shape:

- `execute_task()` emits `workflow/started` and waits for completion
- Inngest subscribers remain for workflow/task/evaluation orchestration
- handlers are thin and mostly stateless
- core services can run without Inngest
- rubrics are pure domain/application logic
- workers do not depend on ambient step context
- observability is emitted explicitly and can be routed to Inngest, logs, DB, or the dashboard

## 24. Recommendation

The best cleanup path is not "remove Inngest."

It is:

- keep Inngest as the event-driven orchestration layer
- stop using it as the shape-defining abstraction for core execution logic

The most important immediate fixes are:

1. remove `inngest.Context` from rubric and evaluation service interfaces
2. remove dynamic step injection from worker execution
3. extract application services out of thick runners
4. move criterion fanout orchestration out of rubric classes

If we do only those four things, the architecture will already be substantially cleaner and much less likely to produce the class of bugs caused by mixing orchestration semantics with business logic.

