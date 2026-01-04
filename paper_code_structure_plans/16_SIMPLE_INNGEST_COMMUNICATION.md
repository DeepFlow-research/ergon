# 16. Simple Inngest Communication Architecture

## Design Principles

1. **Communication service = Inngest functions** (not classes with methods)
2. **Tools use `step.send_event()` / `step.wait_for_event()` directly**
3. **`WorkerContext` provides step context to tools** (no passing through toolkit constructors)
4. **No mixins, no registries, no base classes** - just functions and data

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              worker_execute                                 │
│                           (Inngest function)                                │
│                                                                             │
│   WorkerContext = { run_id, step, worker_id, stakeholder_id }               │
│                          │                                                  │
│                          ▼                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        Agent Runner                                 │   │
│   │                                                                     │   │
│   │   Tools receive WorkerContext automatically                         │   │
│   │                          │                                          │   │
│   │                          ▼                                          │   │
│   │   ┌─────────────────────────────────────────────────────────────┐   │   │
│   │   │              ask_stakeholder tool                           │   │   │
│   │   │                                                             │   │   │
│   │   │   ctx.step.send_event("communication/ask", {...})           │   │   │
│   │   │   ctx.step.wait_for_event("communication/response", ...)    │   │   │
│   │   └─────────────────────────────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    Inngest Event Bus
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     communication_handler                                   │
│                       (Inngest function)                                    │
│                                                                             │
│   1. Receive "communication/ask" event                                      │
│   2. Look up stakeholder by to_agent_id (from run context in event)         │
│   3. Invoke stakeholder.answer(question)                                    │
│   4. Persist messages to DB via CommunicationService                        │
│   5. Emit "communication/response" event                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation

### 1. Extended WorkerContext

**File: `h_arcane/core/agents/base.py`**

```python
"""Base classes and context for agents."""

from dataclasses import dataclass, field
from uuid import UUID
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import inngest


@dataclass
class WorkerContext:
    """
    Context passed to all tools during agent execution.
    
    Tools receive this automatically as their first parameter
    when typed as WorkerContext.
    """
    
    # Run identification
    run_id: UUID
    
    # Inngest step context for event operations
    step: "inngest.Step"
    
    # Agent identities
    worker_id: UUID
    stakeholder_id: UUID
    
    # Tracking
    num_executed_tools: int = 0
    questions_asked: int = 0
```

### 2. Communication Events

**File: `h_arcane/core/communication/events.py`**

```python
"""Communication event definitions."""

# Event names
COMMUNICATION_ASK = "communication/ask"
COMMUNICATION_RESPONSE = "communication/response"
```

### 3. The ask_stakeholder Tool (Simple Function)

**File: `h_arcane/core/communication/tools.py`**

```python
"""Communication tools for agents."""

from uuid import uuid4
from datetime import timedelta

from agents import function_tool

from h_arcane.core.agents.base import WorkerContext
from h_arcane.core.communication.events import (
    COMMUNICATION_ASK,
    COMMUNICATION_RESPONSE,
)


def make_ask_stakeholder_tool():
    """
    Create the ask_stakeholder tool.
    
    This is a factory function so each toolkit can get its own instance
    if needed, but the implementation is shared.
    """
    
    @function_tool
    async def ask_stakeholder(ctx: WorkerContext, question: str) -> str:
        """
        Ask the stakeholder a clarification question about the task.
        
        Use this when you're uncertain about requirements, preferences,
        or how to proceed.
        
        Args:
            ctx: Worker context (automatically injected)
            question: Your question for the stakeholder
            
        Returns:
            The stakeholder's answer
        """
        correlation_id = str(uuid4())
        
        # Send ask event
        await ctx.step.send_event(
            f"ask-{ctx.questions_asked}",
            [
                {
                    "name": COMMUNICATION_ASK,
                    "data": {
                        "run_id": str(ctx.run_id),
                        "from_agent_id": str(ctx.worker_id),
                        "to_agent_id": str(ctx.stakeholder_id),
                        "content": question,
                        "correlation_id": correlation_id,
                    },
                }
            ],
        )
        
        # Wait for response
        response = await ctx.step.wait_for_event(
            f"wait-{ctx.questions_asked}",
            event=COMMUNICATION_RESPONSE,
            if_exp=f"async.data.correlation_id == '{correlation_id}'",
            timeout=timedelta(seconds=60),
        )
        
        ctx.questions_asked += 1
        
        if response is None:
            return "[Error: Stakeholder response timed out]"
        
        return response.data["content"]
    
    return ask_stakeholder


# Pre-built instance for convenience
ask_stakeholder_tool = make_ask_stakeholder_tool()
```

### 4. Communication Handler (Inngest Function)

**File: `h_arcane/core/communication/handler.py`**

```python
"""Inngest function that handles communication events."""

import inngest
from uuid import UUID

from h_arcane.core.infrastructure.inngest_client import inngest_client
from h_arcane.core.communication.events import (
    COMMUNICATION_ASK,
    COMMUNICATION_RESPONSE,
)
from h_arcane.core.communication.service import communication_service
from h_arcane.core.communication.schemas import CreateMessageRequest
from h_arcane.core.db.queries import queries


@inngest_client.create_function(
    fn_id="communication-handler",
    trigger=inngest.TriggerEvent(event=COMMUNICATION_ASK),
    retries=2,
)
async def communication_handler(ctx: inngest.Context) -> dict:
    """
    Handle communication/ask events.
    
    This function:
    1. Loads the stakeholder for the run
    2. Invokes stakeholder.answer()
    3. Persists both messages
    4. Emits response event
    """
    data = ctx.event.data
    
    run_id = data["run_id"]
    from_agent_id = data["from_agent_id"]
    to_agent_id = data["to_agent_id"]
    question = data["content"]
    correlation_id = data["correlation_id"]
    
    # Step 1: Load stakeholder from run context
    # The stakeholder is created fresh based on run/experiment data
    stakeholder = await ctx.step.run(
        "load-stakeholder",
        lambda: _load_stakeholder_for_run(UUID(run_id)),
    )
    
    # Step 2: Persist the question
    await ctx.step.run(
        "persist-question",
        lambda: communication_service.save_message(
            CreateMessageRequest(
                from_agent_id=UUID(from_agent_id),
                to_agent_id=UUID(to_agent_id),
                thread_topic="task_clarification",
                content=question,
            )
        ),
    )
    
    # Step 3: Get stakeholder's answer
    answer = await ctx.step.run(
        "get-answer",
        lambda: stakeholder.answer(question),
    )
    
    # Step 4: Persist the answer
    await ctx.step.run(
        "persist-answer",
        lambda: communication_service.save_message(
            CreateMessageRequest(
                from_agent_id=UUID(to_agent_id),
                to_agent_id=UUID(from_agent_id),
                thread_topic="task_clarification",
                content=answer,
            )
        ),
    )
    
    # Step 5: Emit response event
    await ctx.step.send_event(
        "emit-response",
        [
            {
                "name": COMMUNICATION_RESPONSE,
                "data": {
                    "correlation_id": correlation_id,
                    "from_agent_id": to_agent_id,
                    "to_agent_id": from_agent_id,
                    "content": answer,
                },
            }
        ],
    )
    
    return {"status": "success"}


def _load_stakeholder_for_run(run_id: UUID):
    """Load and instantiate stakeholder for a run."""
    from h_arcane.benchmarks.registry import get_benchmark
    
    # Get run and experiment
    run = queries.runs.get(run_id)
    if run is None:
        raise ValueError(f"Run {run_id} not found")
    
    experiment = queries.experiments.get(run.experiment_id)
    if experiment is None:
        raise ValueError(f"Experiment {run.experiment_id} not found")
    
    # Get benchmark and create stakeholder
    benchmark = get_benchmark(experiment.benchmark_name)
    return benchmark.create_stakeholder(experiment)
```

### 5. Simplified Toolkit

**File: `h_arcane/benchmarks/gdpeval/toolkit.py`** (simplified)

```python
"""GDPEval toolkit - simplified."""

from uuid import UUID
from agents import Tool

from h_arcane.core.agents.base import BaseToolkit
from h_arcane.core.communication.tools import ask_stakeholder_tool
from h_arcane.core.infrastructure.sandbox import BaseSandboxManager


class GDPEvalToolkit(BaseToolkit):
    """GDPEval benchmark toolkit."""
    
    def __init__(self, sandbox_manager: BaseSandboxManager):
        """
        Initialize toolkit.
        
        Note: No run_id, stakeholder, or step needed!
        Tools get context from WorkerContext at runtime.
        """
        self.sandbox_manager = sandbox_manager
    
    def get_tools(self) -> list[Tool]:
        """Return all tools."""
        return [
            self._read_pdf(),
            self._read_csv(),
            # ... other tools ...
            ask_stakeholder_tool,  # Just include the pre-built tool!
        ]
    
    # Benchmark-specific tools only...
    def _read_pdf(self) -> Tool:
        ...
```

### 6. Updated Worker Execution

**File: `h_arcane/core/orchestration/worker_execute.py`** (relevant parts)

```python
"""Worker execution - simplified."""

from uuid import uuid4

import inngest

from h_arcane.core.infrastructure.inngest_client import inngest_client
from h_arcane.core.agents.base import WorkerContext


@inngest_client.create_function(
    fn_id="worker-execute",
    trigger=inngest.TriggerEvent(event="run/execute"),
)
async def worker_execute(ctx: inngest.Context) -> dict:
    """Execute a worker run."""
    
    run_id = UUID(ctx.event.data["run_id"])
    
    # ... load experiment, create sandbox, etc ...
    
    # Generate agent IDs
    worker_id = uuid4()
    stakeholder_id = uuid4()
    
    # Create context with step - this is all tools need!
    worker_context = WorkerContext(
        run_id=run_id,
        step=ctx.step,
        worker_id=worker_id,
        stakeholder_id=stakeholder_id,
    )
    
    # Create toolkit (no longer needs stakeholder or step!)
    toolkit = benchmark.create_toolkit(sandbox_manager=sandbox_manager)
    
    # Create agent
    agent = Agent[WorkerContext](
        name="TaskWorker",
        model=config.model,
        instructions=config.system_prompt,
        tools=toolkit.get_tools(),
        output_type=WorkerExecutionOutput,
    )
    
    # Run - context is passed to all tools automatically
    result = await Runner.run(
        agent,
        task_prompt,
        context=worker_context,
        max_turns=25,
    )
    
    return {"status": "success", "result": result.final_output}
```

---

## What Changed vs Previous Plan

| Previous (Plan 15) | Now (Plan 16) |
|--------------------|---------------|
| `InngestCommunicationMixin` | Gone |
| `AgentRegistry` class | Gone |
| `CommunicatingToolkit` base class | Gone |
| Pass `step` through toolkit constructor | `step` in `WorkerContext` |
| Toolkit creates `ask_stakeholder` tool | Import pre-built `ask_stakeholder_tool` |
| Complex handler lookup | Handler loads stakeholder from run data |

---

## File Structure

```
h_arcane/core/
├── agents/
│   └── base.py                    # WorkerContext with step
│
├── communication/
│   ├── __init__.py                # Exports
│   ├── schemas.py                 # Pydantic schemas (existing)
│   ├── service.py                 # CommunicationService (existing)
│   ├── events.py                  # Event name constants (simple)
│   ├── tools.py                   # ask_stakeholder_tool (NEW)
│   └── handler.py                 # communication_handler fn (NEW)
```

**Total new code: ~150 lines across 3 small files**

---

## Flow Diagram

```
worker_execute                    Inngest                    communication_handler
     │                              │                              │
     │  Create WorkerContext        │                              │
     │  with step, agent IDs        │                              │
     │                              │                              │
     │  Run Agent                   │                              │
     │     │                        │                              │
     │     ▼                        │                              │
     │  Tool: ask_stakeholder       │                              │
     │     │                        │                              │
     │     │ ctx.step.send_event    │                              │
     │     │ ("communication/ask")  │                              │
     │     │───────────────────────►│                              │
     │     │                        │  trigger                     │
     │     │                        │─────────────────────────────►│
     │     │                        │                              │
     │     │ ctx.step.wait_for_event│                              │
     │     │ ("communication/       │                              │ load stakeholder
     │     │  response")            │                              │ get answer
     │     │      ┌─────────────────│                              │ persist messages
     │     │      │ waiting...      │                              │
     │     │      │                 │  send_event                  │
     │     │      │                 │  ("communication/response")  │
     │     │      │                 │◄─────────────────────────────│
     │     │      │                 │                              │
     │     │◄─────┘                 │                              │
     │     │ got answer!            │                              │
     │     │                        │                              │
     │     ▼                        │                              │
     │  Continue agent execution    │                              │
     │                              │                              │
     ▼                              ▼                              ▼
```

---

## Key Insight: Stakeholder Loaded in Handler

The previous plans required registering stakeholder handlers. Now:

1. **Worker sends event** with `run_id`
2. **Handler receives event** and loads stakeholder fresh from DB
3. **No registration needed** - stakeholder is reconstructed on demand

This works because stakeholders are stateless - they just need the rubric/experiment data to answer questions.

---

## Multi-Agent Support

Same architecture extends naturally:

```python
# Worker-to-worker communication
@function_tool
async def ask_coworker(ctx: WorkerContext, coworker_id: str, question: str) -> str:
    """Ask another worker agent a question."""
    correlation_id = str(uuid4())
    
    await ctx.step.send_event("ask-coworker", [{
        "name": "communication/ask",
        "data": {
            "run_id": str(ctx.run_id),
            "from_agent_id": str(ctx.worker_id),
            "to_agent_id": coworker_id,
            "content": question,
            "correlation_id": correlation_id,
        },
    }])
    
    response = await ctx.step.wait_for_event(...)
    return response.data["content"]
```

The handler just needs to route based on `to_agent_id` type.

---

## Migration Checklist

### Phase 1: Core
- [ ] Update `WorkerContext` in `base.py` to include `step`, `worker_id`, `stakeholder_id`
- [ ] Create `events.py` with event constants
- [ ] Create `tools.py` with `ask_stakeholder_tool`
- [ ] Create `handler.py` with `communication_handler` function
- [ ] Register handler with Inngest client

### Phase 2: Integration
- [ ] Update `worker_execute.py` to create full `WorkerContext`
- [ ] Update toolkits to use `ask_stakeholder_tool` import

### Phase 3: Cleanup
- [ ] Remove old `ask_stakeholder` implementations from toolkits
- [ ] Remove `stakeholder` and `run_id` from toolkit constructors
- [ ] Update tests

---

## Benefits of This Approach

1. **Simple**: Just functions, no class hierarchies
2. **Tools are pure**: They just use `ctx.step` - no toolkit coupling
3. **Toolkits are lean**: No communication concerns, just domain tools
4. **Testable**: Mock `ctx.step` in tests
5. **Extensible**: Add new communication tools by writing new functions
6. **Consistent**: Uses same Inngest patterns as rest of codebase

