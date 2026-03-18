# Violation B: `EvaluationRunner` Is Inngest-Aware

## Problem

`EvaluationRunner` currently acts like a domain/application service, but its API is shaped around `inngest.Context`.

That means one of our core evaluation helpers is framework-bound.

## Trace Of The Violation

### File: `h_arcane/core/_internal/evaluation/runner.py`

Current characteristics:

- imports `inngest`
- stores `inngest_ctx`
- exposes a `step(...)` helper that delegates to `ctx.step.run(...)`

Representative current shape:

```python
class EvaluationRunner:
    def __init__(..., inngest_ctx: inngest.Context, ...):
        self.inngest_ctx = inngest_ctx

    async def step(...):
        return await self.inngest_ctx.step.run(...)
```

### File: `h_arcane/core/_internal/evaluation/inngest_functions/criterion.py`

The Inngest handler constructs the runner with `inngest_ctx=ctx`:

```python
runner = EvaluationRunner(data, sandbox_manager, inngest_ctx=ctx)
```

So the coupling is hardwired at the construction point.

## Why This Is Bad

- The evaluation helper cannot run independently of Inngest.
- Internal design is driven by observability boundaries instead of service boundaries.
- Unit tests need to supply orchestration context just to use the service.
- Domain rules inherit orchestration semantics through the runner object.

## Proposed Fix

Make `EvaluationRunner` framework-agnostic.

The runner should:

- manage sandbox access
- upload files
- run code
- call the judge model
- perform cleanup

The runner should not:

- own `step.run(...)`
- know about `inngest.Context`
- assume it is being executed inside an Inngest function

## Specific Code Changes

### File: `h_arcane/core/_internal/evaluation/runner.py`

#### Change

- remove the `inngest` import
- remove `inngest_ctx` from the constructor
- remove the `step(...)` helper
- optionally support a framework-agnostic tracing hook if we still want instrumentation

#### Diff sketch

```diff
- import inngest
  from openai import AsyncOpenAI
+
+ from typing import Protocol
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

-    async def step(self, step_id: str, fn, output_type=None):
-        if output_type:
-            return await self.inngest_ctx.step.run(step_id, fn, output_type=output_type)
-        return await self.inngest_ctx.step.run(step_id, fn)
+    async def trace(self, name: str, metadata: dict | None = None) -> None:
+        if self.trace_sink is not None:
+            await self.trace_sink.record(name, metadata)
```

### File: `h_arcane/core/_internal/evaluation/inngest_functions/criterion.py`

#### Change

- keep `ctx.step.run(...)` at the handler boundary
- create the runner without `inngest_ctx`
- make the handler responsible for durable wrapping

#### Diff sketch

```diff
 async def evaluate_criterion_fn(ctx: inngest.Context) -> CriterionResult:
     payload = CriterionEvaluationEvent.model_validate(ctx.event.data)
     data = EvaluationData(...)

-    runner = EvaluationRunner(data, sandbox_manager, inngest_ctx=ctx)
-    result = await payload.rule.evaluate(runner)
-
-    async def cleanup() -> None:
-        await runner.cleanup()
-
-    await ctx.step.run("cleanup", cleanup)
-    return result
+    async def run_rule() -> CriterionResult:
+        runner = EvaluationRunner(data, sandbox_manager)
+        try:
+            return await payload.rule.evaluate(runner)
+        finally:
+            await runner.cleanup()
+
+    return await ctx.step.run(
+        "evaluate-criterion",
+        run_rule,
+        output_type=CriterionResult,
+    )
```

## Optional Tracing Upgrade

If we still want richer observability than a single Inngest step per criterion, do not reintroduce `inngest.Context`.

Instead:

- define a `TraceSink`
- let the Inngest handler pass an `InngestTraceSink` adapter
- let the runner emit explicit `trace(...)` calls

That keeps the dependency direction correct.

## Acceptance Criteria

- `EvaluationRunner` imports no Inngest types.
- `EvaluationRunner` constructor takes no `inngest_ctx`.
- `criterion.py` is the place where Inngest step boundaries live.
- Rules using `EvaluationRunner` can run without Inngest-specific setup.

## Notes

This change pairs naturally with the rubric API cleanup and criterion fanout extraction. On its own, it already improves testability and removes one major source of framework leakage.
