# Violation D: Rubrics Orchestrate Criterion Fanout

## Problem

Several rubric implementations are currently choosing the criterion execution strategy themselves.

That means the benchmark layer is not only defining scoring semantics, it is also orchestrating the work.

## Trace Of The Violation

### Files

- `h_arcane/benchmarks/gdpeval/rubric.py`
- `h_arcane/benchmarks/smoke_test/rubric.py`
- `h_arcane/benchmarks/researchrubrics/rubric.py`

### Common pattern

These files currently:

- construct `CriterionEvaluationEvent`
- import `evaluate_criterion_fn`
- create lambdas that call `inngest_ctx.step.invoke(...)`
- run `inngest_ctx.group.parallel(...)`

That is orchestration logic living inside benchmark code.

## Why This Is Bad

- Rubrics now know handler names and orchestration topology.
- Criterion execution strategy is hardcoded into scoring code.
- Local evaluation cannot reuse rubric logic cleanly.
- The benchmark layer has become dependent on Inngest mechanics.

## Proposed Fix

Move criterion fanout to an evaluation application service plus an execution adapter.

The rubric should only provide:

- a plan describing the criterion work
- an aggregation function

The orchestrator/service should decide:

- local vs Inngest-backed execution
- serial vs parallel execution
- how failures and retries are handled

## Specific Code Changes

### File: `h_arcane/core/_internal/evaluation/inngest_functions/task_run.py`

#### Change

- stop calling `payload.rubric.compute_scores(context, ctx)`
- instead, create an evaluation service with a criterion executor

#### Diff sketch

```diff
+ from h_arcane.core._internal.evaluation.services.task_evaluation_service import (
+     TaskEvaluationService,
+ )
+ from h_arcane.core._internal.evaluation.inngest_adapters import InngestCriterionExecutor

 async def evaluate_task_run(ctx: inngest.Context) -> TaskEvaluationResult:
     payload = TaskEvaluationEvent.model_validate(ctx.event.data)
     context = TaskEvaluationContext(...)

-    result = await payload.rubric.compute_scores(context, ctx)
+    service = TaskEvaluationService(
+        criterion_executor=InngestCriterionExecutor(ctx),
+    )
+    result = await service.evaluate(
+        context=context,
+        rubric=payload.rubric,
+    )

     await ctx.step.run("persist-criterion-results", persist_criterion_results)
     await ctx.step.run("persist-task-evaluation-result", persist_task_evaluation_result)
     return result
```

### New file: `h_arcane/core/_internal/evaluation/services/task_evaluation_service.py`

#### Change

- add a service that coordinates plan generation, criterion execution, and aggregation

#### Diff sketch

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
+         criterion_results = await self.criterion_executor.execute_all(
+             context=context,
+             criteria=plan.criteria,
+         )
+         return rubric.aggregate(context, criterion_results)
```

### New file: `h_arcane/core/_internal/evaluation/inngest_adapters.py`

#### Change

- add an Inngest-backed criterion executor adapter

#### Diff sketch

```diff
+ class InngestCriterionExecutor:
+     def __init__(self, ctx: inngest.Context):
+         self.ctx = ctx
+
+     async def execute_all(self, context, criteria):
+         def make_invoker(spec):
+             event = CriterionEvaluationEvent(
+                 run_id=str(context.run_id),
+                 task_input=context.task_input,
+                 agent_reasoning=context.agent_reasoning,
+                 agent_outputs=context.agent_outputs,
+                 benchmark_name=spec.benchmark_name,
+                 stage_name=spec.stage_name,
+                 stage_idx=spec.stage_idx,
+                 rule_idx=spec.rule_idx,
+                 max_score=spec.max_score,
+                 rule=spec.rule,
+             )
+             return lambda: self.ctx.step.invoke(
+                 step_id=f"criterion-{spec.stage_idx}-{spec.rule_idx}",
+                 function=evaluate_criterion_fn,
+                 data=event.model_dump(mode="json"),
+             )
+
+         return list(
+             await self.ctx.group.parallel(
+                 tuple(make_invoker(spec) for spec in criteria)
+             )
+         )
```

## Rubric-Level Changes

### GDPEval

- remove all `CriterionEvaluationEvent` construction from the rubric
- move all `step.invoke(...)` and `group.parallel(...)` logic out
- keep only:
  - staged criterion extraction
  - staged score aggregation

### Smoke test

- remove direct invocation of `evaluate_criterion_fn`
- produce a flat criterion plan instead

### ResearchRubrics

- remove orchestration lambdas from the rubric
- keep weighted aggregation logic only

## Acceptance Criteria

- No rubric imports `CriterionEvaluationEvent`.
- No rubric imports `evaluate_criterion_fn`.
- No rubric uses `group.parallel(...)`.
- `task_run.py` owns the criterion execution strategy through a service/adapter boundary.

## Notes

This refactor depends on the rubric API cleanup. The two changes should be treated as one mini-epic rather than isolated edits.
