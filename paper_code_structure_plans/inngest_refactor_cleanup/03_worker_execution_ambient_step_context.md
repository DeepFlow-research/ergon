# Violation C: Worker Execution Depends On Ambient Step Context

## Problem

Worker execution currently depends on hidden Inngest state being installed at runtime.

This is the clearest place where execution code is not truly independent from orchestration.

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

So the worker itself assumes that tool calls are being wrapped in Inngest-specific execution behavior.

## Why This Is Bad

- The worker interface does not reveal this dependency.
- Correctness depends on a handler remembering to install step context.
- Local execution and orchestrated execution can diverge.
- Tool observability is implemented through framework magic instead of explicit application behavior.

## Proposed Fix

Make tool-call observation explicit.

Change the worker model from:

- "tools become Inngest steps because orchestration injected ambient context"

To:

- "workers receive explicit observation hooks and run normally"

## Specific Code Changes

### File: `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`

#### Change

- remove `set_step(ctx.step)`
- keep orchestration responsibilities in the handler
- if needed later, pass an explicit observer/tracer into `WorkerContext`

#### Diff sketch

```diff
- from inngest_agents import set_step
  import inngest

 async def worker_execute_fn(ctx: inngest.Context) -> WorkerExecuteResult:
     ...
-    set_step(ctx.step)
-
     result = await _execute_worker(
         run_id=run_id,
         task_id=task_id,
         ...
     )
```

### File: `h_arcane/core/worker.py`

#### Change

- add an optional explicit observer/tracer field onto `WorkerContext`

#### Diff sketch

```diff
 class WorkerContext(BaseModel):
     run_id: UUID
     task_id: UUID
     sandbox: Any = Field(default=None)
     input_resources: list[Resource] = Field(default_factory=list)
     metadata: dict[str, Any] = Field(default_factory=dict)
     toolkit: Any = Field(default=None)
     agent_config_id: UUID | None = Field(default=None)
+    tool_observer: Any = Field(
+        default=None,
+        description="Optional observer for tool lifecycle events",
+    )
```

### File: `h_arcane/benchmarks/common/workers/react_worker.py`

#### Change

- remove `as_step(...)`
- keep tools as normal tools
- explicitly notify the observer for tool start/completion where needed

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
+    tools = [
+        self._make_ask_tool(toolkit, context.tool_observer),
+        *toolkit.get_tools(),
+    ]

     agent = Agent(
         name=self.name,
         model=self.model,
         instructions=self.system_prompt,
         tools=tools,
         output_type=WorkerExecutionOutput,
     )
```

### File: `h_arcane/benchmarks/common/workers/react_worker.py`

#### Change to explicit `ask_stakeholder` observation

#### Diff sketch

```diff
- def _make_ask_tool(self, toolkit: BaseToolkit):
+ def _make_ask_tool(self, toolkit: BaseToolkit, observer=None):
     @function_tool
     async def ask_stakeholder(question: str) -> str:
+        if observer:
+            await observer.on_tool_start(
+                "ask_stakeholder",
+                {"question": question},
+            )
         answer = await toolkit.ask_stakeholder(question)
+        if observer:
+            await observer.on_tool_complete(
+                "ask_stakeholder",
+                {"answer": answer},
+            )
         return answer
```

## Follow-Up Design Question

For toolkit tools beyond `ask_stakeholder`, we have two options:

### Option 1

Wrap toolkit tools in a lightweight observer adapter before passing them to the agent.

### Option 2

Teach toolkit factories to return already-observable tools.

I would start with Option 1 because it keeps the tool tracing concern near the worker runtime rather than distributing it across every toolkit.

## Acceptance Criteria

- `worker_execute.py` no longer calls `set_step(...)`.
- `react_worker.py` no longer imports `inngest_agents.as_step`.
- Worker execution semantics are the same whether or not Inngest is present.
- Tool lifecycle observability, if retained, is explicit through `WorkerContext` hooks or wrappers.

## Notes

This is the highest-risk refactor from a runtime behavior standpoint, but it is also the most important for restoring a clean execution/orchestration split.
