# Rubric / Criterion / Service Redesign Plan

## Summary

This document proposes a concrete redesign of the evaluation architecture so that:

- a rubric is primarily metadata plus a list of criteria
- a criterion is the third-party extension point
- a criterion implements how it evaluates itself
- a criterion returns a shared `CriterionResult`
- rubrics do not take `inngest.Context`
- rubric execution is orchestrated by a separate service
- the service may use Inngest for parallelism and observability, but the criterion and rubric layers do not know that

This plan is intended to address the core concerns behind:

- `01_rubric_api_depends_on_inngest.md`
- `02_evaluation_runner_inngest_aware.md`
- `04_rubrics_orchestrate_criterion_fanout.md`

## Problem Statement

The current evaluation architecture mixes three concerns:

1. domain definition
   - what is being evaluated
   - how criteria are scored
   - how multiple criteria aggregate into a rubric result

2. execution/runtime behavior
   - sandbox access
   - file upload
   - code execution
   - LLM judge calls

3. orchestration behavior
   - fanout across criteria
   - parallelism
   - `step.run(...)`
   - `step.invoke(...)`
   - Inngest visibility and retries

Today, these are too mixed together:

- rubrics directly take `inngest.Context`
- rubrics decide criterion fanout
- rules use an Inngest-aware runner
- `task_run.py` is not the clear owner of orchestration

That makes the public evaluation abstraction too hard to understand and too tightly coupled to Inngest.

## Design Goals

### Primary goals

- Third-party users should implement criteria, not orchestration.
- Criteria should receive a clean runtime and a clean context.
- Rubrics should not know about Inngest.
- The orchestration layer should decide whether criteria run:
  - serially
  - in-process parallel
  - via `step.run(...)`
  - via `step.invoke(...)`
- Existing benchmark semantics should still be expressible:
  - staged GDPEval
  - flat weighted ResearchRubrics
  - single-criterion MiniF2F
  - simple smoke tests

### Non-goals

- This does not require removing Inngest from evaluation orchestration.
- This does not require rewriting all rules in one shot.
- This does not require changing the database result models immediately.

## Proposed Final Model

## 1. Criterion Is The Extension Point

The core pluggable abstraction should be a criterion.

Conceptually, the current `BaseRule` is already almost this. The redesign is mostly about clarifying and cleaning the interface.

### Proposed interface

```python
class BaseCriterion(BaseModel, ABC):
    name: str
    description: str
    weight: float = 1.0

    @abstractmethod
    async def evaluate(
        self,
        runtime: "CriterionRuntime",
        context: "CriterionContext",
    ) -> CriterionResult:
        ...
```

### Why this is the right abstraction

- It is understandable to third-party authors.
- It keeps evaluation logic local to the criterion.
- It does not require `inngest.Context`.
- It returns a shared result shape.

### Compatibility note

We do not need to rename everything immediately.

A low-risk migration path is:

- keep `BaseRule` for now
- treat it as the criterion abstraction
- later rename `BaseRule` -> `BaseCriterion`
- optionally keep `BaseRule = BaseCriterion` as a compatibility alias for one cycle

## 2. Rubric Is Metadata + Criteria + Aggregation

A rubric should not orchestrate its own execution.

A rubric should:

- hold benchmark-specific metadata
- hold a list of criteria or criterion specs
- define how criterion results aggregate into a `TaskEvaluationResult`

### Proposed rubric responsibilities

Good rubric responsibilities:

- category/stage metadata
- criterion definitions
- score normalization
- gate logic
- failure policy

Bad rubric responsibilities:

- constructing Inngest events
- invoking handlers
- choosing parallelism strategy
- calling `group.parallel(...)`

### Proposed interface

```python
class BaseRubric(Protocol):
    benchmark: str
    criteria: list["CriterionSpec"]

    def aggregate(
        self,
        task_context: TaskEvaluationContext,
        criterion_results: list[CriterionResult],
    ) -> TaskEvaluationResult:
        ...
```

If a rubric needs richer structure than a simple flat list, it should still expose a normalized execution list through `criteria`, while retaining any richer metadata internally for aggregation.

## 3. Criterion Context Is Separate From Task Context

Today we have:

- `TaskEvaluationContext`
- `EvaluationData`

These are close, but the naming does not cleanly match the new architecture.

### Proposed split

#### Task-level context

Used by the service to evaluate a whole rubric.

```python
class TaskEvaluationContext(BaseModel):
    run_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[ResourceRecord]
```

#### Criterion-level context

Used by each criterion during one criterion evaluation.

```python
class CriterionContext(BaseModel):
    run_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[ResourceRecord]
    stage_idx: int
    stage_name: str
    criterion_idx: int
    max_score: float
```

This is basically a cleaner, better-named version of the current `EvaluationData`.

## 4. Criterion Runtime Is Framework-Agnostic

The criterion needs a runtime/helper, but it should not be Inngest-shaped.

### Proposed interface

```python
class CriterionRuntime(Protocol):
    async def ensure_sandbox(self) -> None: ...
    async def upload_files(self, files: list[ResourceRecord]) -> None: ...
    async def execute_code(self, code: str) -> SandboxResult: ...
    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T: ...
    async def cleanup(self) -> None: ...
```

### Proposed implementation

The current `EvaluationRunner` should become the default implementation of this runtime, but without any `inngest.Context` dependency.

Good rename options:

- `DefaultCriterionRuntime`
- `EvaluationRuntime`

I would avoid keeping the current name `EvaluationRunner` if possible, because "runner" currently implies orchestration.

## 5. Service Owns Rubric Execution

The orchestration-aware evaluation service should be separate from the rubric.

### Proposed service

```python
class RubricEvaluationService:
    def __init__(self, criterion_executor: "CriterionExecutor"):
        self.criterion_executor = criterion_executor

    async def evaluate(
        self,
        task_context: TaskEvaluationContext,
        rubric: BaseRubric,
    ) -> TaskEvaluationResult:
        criterion_results = await self.criterion_executor.execute_all(
            task_context=task_context,
            criteria=rubric.criteria,
        )
        return rubric.aggregate(task_context, criterion_results)
```

This is the key boundary:

- rubric defines evaluation structure
- criterion implements criterion logic
- service runs the rubric
- executor chooses orchestration strategy

## 6. Executor Owns Parallelism And Inngest

We need a separate abstraction for "run these criteria."

### Proposed interface

```python
class CriterionExecutor(Protocol):
    async def execute_all(
        self,
        task_context: TaskEvaluationContext,
        criteria: list[CriterionSpec],
    ) -> list[CriterionResult]:
        ...
```

### Inngest-backed implementation

```python
class InngestCriterionExecutor:
    def __init__(self, ctx: inngest.Context):
        self.ctx = ctx

    async def execute_all(self, task_context, criteria):
        ...
```

This class should be the only thing in the rubric execution path that knows about:

- `inngest.Context`
- `ctx.step.run(...)`
- `ctx.group.parallel(...)`
- `ctx.step.invoke(...)`

That is the architecture goal in one sentence.

## Proposed Data Model

## 1. CriterionSpec

We need a wrapper around the criterion so rubrics can attach metadata like stage info and max score.

```python
class CriterionSpec(BaseModel):
    criterion: AnyCriterion
    stage_idx: int = 0
    stage_name: str = "default"
    criterion_idx: int
    max_score: float
    required: bool = False
    on_failure_action: Literal["continue", "skip_remaining", "zero_category"] = "continue"
```

This lets us express:

- GDPEval gates
- ResearchRubrics weighted criteria
- smoke test flat lists
- MiniF2F single criterion

without forcing the rubric itself to orchestrate.

## Files To Change

This section lists the concrete files we would change for this redesign.

## Core interfaces

### `h_arcane/core/_internal/evaluation/base.py`

Why:

- currently defines a rubric protocol coupled to `inngest.Context`

Change:

- remove `inngest` import
- redefine `BaseRubric` around criteria + aggregation

### `h_arcane/core/_internal/evaluation/schemas.py`

Why:

- contains both task-level and criterion-level data already

Change:

- keep or simplify `TaskEvaluationContext`
- rename or replace `EvaluationData` with `CriterionContext`
- add `CriterionSpec` if this is the most natural place

### `h_arcane/core/_internal/evaluation/runner.py`

Why:

- currently an Inngest-aware runtime helper

Change:

- remove `inngest.Context`
- convert into framework-agnostic criterion runtime

## Rule / criterion layer

### `h_arcane/core/_internal/evaluation/rules/base.py`

Why:

- current `BaseRule` is the best candidate for the criterion abstraction

Change:

- update `evaluate(...)` signature to accept:
  - `CriterionRuntime`
  - `CriterionContext`

### `h_arcane/core/_internal/evaluation/rules/code_rule.py`

Why:

- currently depends on runner step semantics

Change:

- update to use framework-agnostic runtime methods
- remove `runner.step(...)` usage

### `h_arcane/core/_internal/evaluation/rules/llm_judge.py`

Why:

- same as above

Change:

- update to use runtime methods directly

### `h_arcane/benchmarks/minif2f/rules/proof_verification.py`

Why:

- same as above

Change:

- update to use `CriterionRuntime` + `CriterionContext`
- remove `runner.step(...)`

## Rubric layer

### `h_arcane/benchmarks/gdpeval/rubric.py`

Why:

- currently flattens criteria and also orchestrates them

Change:

- keep staged metadata and score aggregation
- remove Inngest orchestration
- expose normalized `criteria: list[CriterionSpec]`

### `h_arcane/benchmarks/smoke_test/rubric.py`

Why:

- currently builds invokers itself

Change:

- replace orchestration logic with flat criterion list + aggregation logic

### `h_arcane/benchmarks/researchrubrics/rubric.py`

Why:

- currently converts criteria to LLM judge rules and orchestrates them

Change:

- keep the conversion logic if needed
- move execution orchestration out
- expose normalized criterion specs

### `h_arcane/benchmarks/minif2f/rubric.py`

Why:

- currently runs evaluation directly through the current runner

Change:

- reduce to a single criterion spec plus MiniF2F-specific aggregation

## Orchestration / service layer

### `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`

Why:

- should become the orchestration bridge for rubric evaluation

Change:

- create task context
- instantiate `RubricEvaluationService(InngestCriterionExecutor(ctx))`
- call service
- persist results

### `h_arcane/core/_internal/evaluation/inngest_functions/criterion.py`

Why:

- may remain useful if we want isolated criterion invocations

Change:

- make it a pure orchestration shell around one criterion evaluation
- no Inngest dependency in runtime/criterion code itself

### New file: `h_arcane/core/_internal/evaluation/services/rubric_evaluation_service.py`

Why:

- we need a clean service owner for rubric execution

Change:

- add a framework-agnostic service that evaluates a rubric by delegating to a criterion executor

### New file: `h_arcane/core/_internal/evaluation/executors.py`

Why:

- we need a clean execution strategy abstraction

Change:

- define `CriterionExecutor`
- optionally define a local executor

### New file: `h_arcane/core/_internal/evaluation/inngest_executor.py`

Why:

- we need a single place where rubric evaluation couples to Inngest

Change:

- add `InngestCriterionExecutor`

## Expected Final State

At the end of this refactor:

- third-party users implement criteria, not orchestration
- criteria return `CriterionResult`
- criteria know only about:
  - their own fields
  - `CriterionContext`
  - `CriterionRuntime`
- rubrics do not import `inngest`
- rubrics do not call `step.run`, `step.invoke`, or `group.parallel`
- `task_run.py` owns Inngest-backed orchestration of criteria
- the Inngest executor is the only place that knows how criterion evaluation is scheduled
- the runtime helper is framework-agnostic

## Implementation Plan

This is the concrete implementation order I would use.

## Phase 1: Introduce the new core abstractions

Files:

- `core/_internal/evaluation/schemas.py`
- `core/_internal/evaluation/base.py`
- `core/_internal/evaluation/rules/base.py`
- new service/executor files

Steps:

1. Introduce `CriterionContext`.
2. Introduce `CriterionSpec`.
3. Introduce `CriterionExecutor`.
4. Introduce `RubricEvaluationService`.
5. Redefine `BaseRubric` toward criteria + aggregation.
6. Redefine `BaseRule` / criterion interface.

Result:

- the new architecture exists in parallel with the old one

## Phase 2: Decouple the runtime

Files:

- `core/_internal/evaluation/runner.py`
- rule implementations

Steps:

1. Make the runtime framework-agnostic.
2. Remove `inngest.Context` from runtime constructor.
3. Change rules to call runtime methods directly instead of `runner.step(...)`.

Result:

- criteria no longer require an Inngest-aware runner

## Phase 3: Move orchestration into the service / executor

Files:

- `evaluation/inngest_functions/task_run.py`
- `evaluation/inngest_functions/criterion.py`
- new `inngest_executor.py`

Steps:

1. Create `InngestCriterionExecutor`.
2. Make `task_run.py` use `RubricEvaluationService`.
3. Decide whether executor uses:
   - `ctx.step.run(...)` around in-process criterion execution, or
   - `ctx.step.invoke(...)` to `evaluate_criterion_fn`

Recommended starting choice:

- use `ctx.step.run(...)` first

Why:

- less event/DTO churn
- simpler migration
- still gets Inngest visibility per criterion

Possible later evolution:

- switch executor implementation to `step.invoke(...)` if stronger isolation or retries per criterion become desirable

## Phase 4: Convert each rubric implementation

Files:

- `gdpeval/rubric.py`
- `smoke_test/rubric.py`
- `researchrubrics/rubric.py`
- `minif2f/rubric.py`

Steps:

1. replace `compute_scores(...)` with criteria exposure + aggregation logic
2. remove orchestration code
3. preserve benchmark-specific semantics

Result:

- rubrics are declarative + aggregative, not orchestration-aware

## Phase 5: Clean up compatibility and naming

Files:

- `benchmarks/types.py`
- imports across evaluation package

Steps:

1. decide whether to keep `BaseRule` name or migrate to `BaseCriterion`
2. update union names if desired
3. clean up deprecated code paths

## Important Design Decisions

## Decision 1: Criterion should still own its implementation

This is important and matches your goal.

The criterion should still decide how it evaluates:

- code execution
- LLM judging
- proof verification
- custom third-party logic

What it should not decide is how many criteria run in parallel or how orchestration is scheduled.

## Decision 2: Rubric should not "run itself"

This is the most important split to preserve.

The rubric should define:

- what criteria exist
- how results aggregate

The service should define:

- how the rubric gets executed

## Decision 3: Inngest should stay at the orchestration boundary

This redesign does not remove Inngest.

It simply narrows its responsibility to:

- orchestration
- visibility
- parallelism strategy

That is the correct layer for it.

## Resolved Decisions

### 1. `CriterionSpec` should live as a field on the rubric

Decision:

- `criteria: list[CriterionSpec]` should live on the rubric as a field

Why:

- it makes the rubric shape explicit and inspectable
- it is easier for reviewers and third-party users to understand than an implicit builder method
- it keeps "what this rubric evaluates" as declarative data rather than hidden construction logic

Implementation note:

- helper methods are still acceptable internally for constructing the field
- but the public shape should be "rubric owns a list of criteria"

### 2. Criterion execution should start with `step.run(...)`

Decision:

- use `step.run(...)` first in the Inngest executor implementation

Why:

- it is the simplest migration path
- it keeps orchestration out of rubric and criterion code
- it still gives us criterion-level observability in Inngest
- it avoids introducing extra event/DTO churn too early

Possible later evolution:

- move from `step.run(...)` to `step.invoke(...)` if we later want harder isolation, retry boundaries, or independent criterion workers

### 3. `EvaluationRunner` should be renamed immediately

Decision:

- rename it now as part of the refactor

Why:

The current name is misleading in the new architecture.

`EvaluationRunner` currently sounds like one of two things:

- an orchestration component that "runs evaluations"
- an Inngest-aware adapter responsible for evaluation execution flow

But in the target architecture, that object is neither of those.

Its actual responsibility after refactor will be closer to:

- a framework-agnostic runtime/helper passed into a single criterion
- an execution utility for sandbox access, LLM judge calls, and cleanup

So keeping the name `EvaluationRunner` would create the wrong mental model even if the implementation is fixed.

That would be harmful because:

- reviewers will keep assuming it owns orchestration
- future contributors may reintroduce orchestration concerns into it
- third-party users will not understand whether they are supposed to implement against it or around it

Recommended replacement names:

- `CriterionRuntime`
- `DefaultCriterionRuntime`
- `EvaluationRuntime`

Strong recommendation:

- use `CriterionRuntime` for the interface / concept
- use `DefaultCriterionRuntime` for the default implementation

That naming makes the architecture much clearer:

- criterion = extension point
- rubric = list of criteria + aggregation
- runtime = helper passed to a criterion
- service = runs a rubric
- executor = decides orchestration strategy

## Recommendation

This redesign is worth doing.

It gives us:

- a cleaner third-party extension point
- a rubric abstraction that is easy to reason about
- an orchestration layer that owns orchestration
- a runtime layer that owns execution helpers
- a direct path to solving the main rubric-related Inngest coupling problems

If we implement only one evaluation refactor first, this should be it.
