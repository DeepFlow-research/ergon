# Violation C: Worker Execution Depends On Ambient Step Context

## Problem

Worker execution currently depends on hidden Inngest state being installed at runtime.

This is the clearest place where execution code is not truly independent from orchestration.

More importantly, this is the violation where we should take the strongest stance:

- remove the Inngest pollution from inside worker execution wholesale
- do not try to preserve per-tool Inngest step semantics inside the worker runtime

The worker should run as normal application code again.

## Trace Of The Violation

### File: `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`

This handler currently does:

```python
set_step(ctx.step)
```

That installs ambient step context for later use by tool execution.

### File: `h_arcane/benchmarks/common/workers/react_worker.py`

This worker currently does:

```python
from inngest_agents import as_step

raw_tools = [
    self._make_ask_tool(toolkit),
    *toolkit.get_tools(),
]
tools = [as_step(t) for t in raw_tools]
```

So the worker assumes:

- a hidden step context has already been installed
- tools should be converted into Inngest steps from inside the worker

That is an orchestration concern leaking into execution.

### Additional design smell: duplicated `ask_stakeholder`

The toolkit abstraction already says the toolkit should include `ask_stakeholder`, and benchmark toolkits do include it in `get_tools()`.

At the same time, `ReActWorker` creates its own `ask_stakeholder` tool wrapper.

So tool ownership is already muddy:

- toolkit owns the tool list
- worker also injects its own extra tool

This makes the current design harder to reason about even before the Inngest cleanup.

## Why This Is Bad

- The worker interface does not reveal this dependency.
- Correctness depends on a handler remembering to install step context.
- Local execution and orchestrated execution can diverge.
- Tool observability is implemented through framework magic instead of explicit application behavior.
- Tool ownership is split between worker and toolkit.

## Recommended Fix

We should strip Inngest from inside worker execution wholesale.

### What that means

Remove:

- `set_step(ctx.step)` from `worker_execute.py`
- `inngest_agents.as_step(...)` from `react_worker.py`
- worker-owned `ask_stakeholder` injection if the toolkit already provides it

Keep:

- outer Inngest orchestration
- `worker_execute_fn` as an orchestration boundary if we still want it
- `WorkerResult.actions` as the canonical trace of what happened during execution
- dashboard action events emitted from persisted actions

### Guiding rule

The worker should not know or care whether it is executing:

- inside Inngest
- in a local script
- in a unit test
- in another orchestrator later

## What This Removes

Removing the Inngest pollution from worker execution removes:

- ambient step injection from `worker_execute.py`
- per-tool `as_step(...)` wrapping in `ReActWorker`
- the assumption that worker correctness depends on an Inngest runtime being present
- per-tool Inngest step visibility in the Inngest UI

It does not remove:

- outer Inngest orchestration
- worker functionality
- tool usage
- action persistence
- dashboard action events, as long as we keep emitting them from persisted actions

## FE Impact Check

This should not break the frontend if we preserve the current dashboard action contract.

### Why

The dashboard does not depend on the internal Inngest step graph directly.

It consumes backend-emitted dashboard events such as:

- `dashboard/agent.action_started`
- `dashboard/agent.action_completed`

And the current backend path already appears to emit only `agent_action_completed` from `worker_execute.py` after actions are extracted from the final worker result.

So the current FE dependency is effectively:

- persisted action records
- dashboard action-completed events

Not:

- per-tool Inngest step internals

### Practical implication

If we remove `set_step(...)` and `as_step(...)` but keep:

- action extraction in `ReActWorker`
- action persistence in `worker_execute.py`
- `dashboard_emitter.agent_action_completed(...)`

Then the dashboard should continue to work.

### What we may lose

We may lose some potential future granularity such as:

- true live "tool started" updates during execution
- per-tool step visibility in the Inngest UI

But that is an observability downgrade in Inngest, not a frontend contract break.

## Specific Code Changes

### File: `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`

#### Change

- remove `set_step(ctx.step)`
- keep orchestration responsibilities in the handler
- continue to emit dashboard action events from the resulting persisted `Action` records

#### Diff sketch

```diff
- from inngest_agents import set_step
  import inngest

 async def worker_execute_fn(ctx: inngest.Context) -> WorkerExecuteResult:
     ...
-    # Set step context for durable tools
-    set_step(ctx.step)
-
     result = await _execute_worker(
         run_id=run_id,
         task_id=task_id,
         ...
     )
```

### File: `h_arcane/benchmarks/common/workers/react_worker.py`

#### Change

- remove `as_step(...)`
- stop trying to make tool execution an Inngest concern
- make the toolkit the single source of truth for the worker's tools

#### Diff sketch

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
+    tools = toolkit.get_tools()

     agent = Agent(
         name=self.name,
         model=self.model,
         instructions=self.system_prompt,
         tools=tools,
         output_type=WorkerExecutionOutput,
     )
```

## What We Should Not Preserve In The First Pass

We should not try to preserve:

- per-tool Inngest step boundaries
- per-tool Inngest durability semantics
- ambient framework magic inside the worker runtime

We should also not introduce a new intermediate worker hook abstraction in phase 1 just to replace the removed Inngest machinery.

That means:

- no `tool_observer`
- no `execution_hooks`
- no partial reintroduction of tracing concerns into `WorkerContext`

If we decide we truly need durable per-tool execution later, that should be a separate explicit abstraction such as:

- `ToolExecutor`
- `ObservedToolAdapter`
- `AgentRuntimeHooks`

But that should be a future design choice, not something we keep by default.

## Short-Term Observability Strategy

After this cleanup, the short-term observability story should be:

1. `WorkerResult.actions` remains the canonical execution trace.
2. Actions are persisted in `worker_execute.py`.
3. Dashboard events continue to be emitted from those persisted actions.

That is enough to preserve current product behavior while cleaning up architecture.

## Long-Term Observability Strategy: OTEL

The long-term replacement for the removed Inngest-internal observability should be OpenTelemetry.

Recommended direction:

1. strip Inngest from inside worker/tool execution first
2. keep DB-backed action traces and dashboard events as the short-term product observability path
3. add OTEL spans inside:
   - worker execution
   - tool invocation wrappers
   - stakeholder asks
   - sandbox skill calls
4. if desired later, build an adapter that maps selected OTEL spans into product-facing dashboard events

This gives us:

- clean architecture
- explicit instrumentation
- no hidden orchestration dependency
- the option to improve observability later without re-entangling the worker with Inngest

## Recommended Implementation Order For This Violation

1. Remove `set_step(ctx.step)` from `worker_execute.py`.
2. Remove `as_step(...)` from `react_worker.py`.
3. Make `toolkit.get_tools()` the single source of truth for worker tools.
4. Keep `WorkerResult.actions` as the canonical execution trace.
5. Verify the dashboard still renders action completion data.
6. Add OTEL instrumentation after the behavior is stable again.

## Acceptance Criteria

- `worker_execute.py` no longer calls `set_step(...)`.
- `react_worker.py` no longer imports `inngest_agents.as_step`.
- `react_worker.py` no longer injects a duplicate `ask_stakeholder` if the toolkit already owns it.
- Worker execution semantics are the same whether or not Inngest is present.
- The dashboard still receives action completion data through the existing backend event path.
- OTEL can be introduced later without reintroducing Inngest runtime coupling into the worker.

## Notes

This is the highest-risk refactor from a runtime behavior standpoint, but it is also the most important for restoring a clean execution/orchestration split.
