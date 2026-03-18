# Violation A: Rubric API Depends On Inngest

## Problem

Rubric interfaces currently depend on `inngest.Context`. That means benchmark scoring logic is not just domain logic anymore; it is partially an orchestration layer.

This is the wrong dependency direction.

The rubric layer should answer:

- what should be evaluated
- how scores should be aggregated

It should not answer:

- how work is scheduled
- whether work runs through Inngest
- how parallelism is implemented

## Trace Of The Violation

### Primary interface

- `h_arcane/core/_internal/evaluation/base.py`

Current shape:

```python
class BaseRubric(Protocol):
    async def compute_scores(
        self,
        context: "TaskEvaluationContext",
        inngest_ctx: inngest.Context,
    ) -> "TaskEvaluationResult":
        ...
```

This makes every rubric implementation framework-aware.

### Direct rubric implementations

- `h_arcane/benchmarks/gdpeval/rubric.py`
- `h_arcane/benchmarks/smoke_test/rubric.py`
- `h_arcane/benchmarks/researchrubrics/rubric.py`
- `h_arcane/benchmarks/minif2f/rubric.py`

All of these take `inngest_ctx` directly, so the dependency has spread from the protocol to every benchmark.

## Why This Is Bad

- Rubrics become hard to test without an Inngest-shaped fake.
- Evaluation logic becomes tied to replay semantics.
- The benchmark layer is forced to know about orchestration.
- Moving evaluation to another executor later becomes expensive.

## Proposed Fix

Change the rubric interface from an execution API to a planning-and-aggregation API.

### New rubric responsibilities

Rubrics should:

- build an evaluation plan
- aggregate criterion results into a task-level evaluation result

Rubrics should not:

- invoke handlers
- emit events
- use `step.run(...)`
- use `group.parallel(...)`

## Proposed API

### Before

```python
async def compute_scores(
    self,
    context: TaskEvaluationContext,
    inngest_ctx: inngest.Context,
) -> TaskEvaluationResult:
    ...
```

### After

```python
def build_plan(self, context: TaskEvaluationContext) -> EvaluationPlan:
    ...

def aggregate(
    self,
    context: TaskEvaluationContext,
    criterion_results: list[CriterionResult],
) -> TaskEvaluationResult:
    ...
```

## Specific Code Changes

### File: `h_arcane/core/_internal/evaluation/base.py`

#### Change

- remove the `inngest` import
- remove `inngest_ctx` from the rubric protocol
- introduce plan/aggregate style methods

#### Diff sketch

```diff
- import inngest
  from typing import TYPE_CHECKING, Protocol
+
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

### File: `h_arcane/core/_internal/evaluation/plan.py`

#### Change

- add a new plan model that represents criterion work without encoding orchestration strategy

#### Diff sketch

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

### File: `h_arcane/benchmarks/gdpeval/rubric.py`

#### Change

- replace `compute_scores(..., inngest_ctx)` with `build_plan(...)` and `aggregate(...)`

#### Diff sketch

```diff
- import inngest
  from pydantic import BaseModel, Field
+ from h_arcane.core._internal.evaluation.plan import CriterionSpec, EvaluationPlan

- async def compute_scores(self, context, inngest_ctx) -> TaskEvaluationResult:
-     ...
-     criterion_results_tuple = await inngest_ctx.group.parallel(parallel_invokers)
-     ...
-     return TaskEvaluationResult(...)
+ def build_plan(self, context) -> EvaluationPlan:
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
+ def aggregate(self, context, criterion_results) -> TaskEvaluationResult:
+     stage_results = _rebuild_stage_results(criterion_results, self)
+     aggregate = _calculate_aggregate_scores(context.run_id, stage_results, self)
+     return TaskEvaluationResult(...)
```

### Files: `smoke_test`, `researchrubrics`, `minif2f`

Apply the same pattern:

- `build_plan(...)` declares the criteria
- `aggregate(...)` computes the final task-level result

For `minif2f`, the plan can just be a single `CriterionSpec`.

## Acceptance Criteria

- No rubric imports `inngest`.
- `BaseRubric` does not mention `inngest.Context`.
- Rubrics do not call `step.run(...)`, `step.invoke(...)`, or `group.parallel(...)`.
- Rubrics remain owners of scoring semantics, not execution strategy.

## Notes

This change is a prerequisite for moving criterion fanout into the orchestration layer cleanly.
