# 15. Inngest-Based Communication Architecture (Simplified)

## Philosophy

**The communication service IS Inngest functions.** That's it.

- No broker class
- No mixin
- No special base classes
- A thin `CommunicationRunner` wraps Inngest details (like `EvaluationRunner`)

---

## Inspiration: The EvaluationRunner Pattern

Looking at `EvaluationRunner`, the pattern is:

```python
class EvaluationRunner:
    """Wraps Inngest context, exposes domain methods."""
    
    def __init__(self, data, sandbox_manager, inngest_ctx: inngest.Context):
        self.inngest_ctx = inngest_ctx
        
    async def step(self, step_id: str, fn) -> R:
        """Delegates to ctx.step.run() - rules don't know about Inngest."""
        return await self.inngest_ctx.step.run(step_id, fn)
```

Rules use the runner:
```python
# Rule doesn't import inngest at all
async def evaluate(self, runner: EvaluationRunner) -> CriterionResult:
    await runner.step("ensure-sandbox", runner.ensure_sandbox)
    result = await runner.step("execute-code", execute_code)
```

**This decouples rules from Inngest.** We can do the same for communication.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Inngest                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   communication/ask  ──────►  communication_handler()  ──────►  response    │
│                               (Inngest function)                            │
│                               - Routes to agent                             │
│                               - Persists messages                           │
│                               - Emits response event                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
           ▲                                                    │
           │                                                    │
           │ step.send_event()                                  │ step.wait_for_event()
           │                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Any Tool / Any Agent                              │
│                                                                             │
│   # That's literally it:                                                    │
│   await step.send_event("communication/ask", {...})                         │
│   response = await step.wait_for_event("communication/response", ...)       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Communication Service (3 Files)

### File 1: `h_arcane/core/communication/events.py`

```python
"""Event constants for communication."""

# Event names
COMM_ASK = "communication/ask"
COMM_RESPONSE = "communication/response"
```

### File 2: `h_arcane/core/communication/registry.py`

```python
"""Simple registry for agent handlers."""

from typing import Callable, Awaitable
from uuid import UUID


# Just a dict. That's it.
_handlers: dict[str, Callable[[str], Awaitable[str]]] = {}


def register(agent_id: UUID, handler: Callable[[str], Awaitable[str]]) -> None:
    """Register a handler for an agent."""
    _handlers[str(agent_id)] = handler


def unregister(agent_id: UUID) -> None:
    """Unregister an agent."""
    _handlers.pop(str(agent_id), None)


def get(agent_id: str) -> Callable[[str], Awaitable[str]] | None:
    """Get handler for an agent."""
    return _handlers.get(agent_id)


def clear() -> None:
    """Clear all handlers (for tests)."""
    _handlers.clear()
```

### File 3: `h_arcane/core/communication/handler.py`

```python
"""The communication service - an Inngest function."""

import inngest

from h_arcane.core.infrastructure.inngest_client import inngest_client
from h_arcane.core.communication import registry
from h_arcane.core.communication.events import COMM_ASK, COMM_RESPONSE
from h_arcane.core.communication.service import communication_service
from h_arcane.core.communication.schemas import CreateMessageRequest
from uuid import UUID


@inngest_client.create_function(
    fn_id="communication-service",
    trigger=inngest.TriggerEvent(event=COMM_ASK),
    retries=2,
)
async def communication_handler(ctx: inngest.Context) -> dict:
    """
    THE communication service.
    
    Receives: communication/ask
    Emits: communication/response
    
    Does:
    1. Look up recipient handler
    2. Invoke it
    3. Persist both messages
    4. Emit response
    """
    data = ctx.event.data
    correlation_id = data["correlation_id"]
    from_agent_id = data["from_agent_id"]
    to_agent_id = data["to_agent_id"]
    topic = data.get("topic", "default")
    content = data["content"]
    
    # Look up handler
    handler = registry.get(to_agent_id)
    
    if handler is None:
        await ctx.step.send_event(
            "error-response",
            [inngest.SendEventRequest(
                name=COMM_RESPONSE,
                data={
                    "correlation_id": correlation_id,
                    "content": f"[Agent {to_agent_id} not found]",
                    "error": True,
                },
            )],
        )
        return {"status": "error", "reason": "agent_not_found"}
    
    # Persist incoming message
    await ctx.step.run(
        "persist-ask",
        lambda: communication_service.save_message(
            CreateMessageRequest(
                from_agent_id=UUID(from_agent_id),
                to_agent_id=UUID(to_agent_id),
                thread_topic=topic,
                content=content,
            )
        ),
    )
    
    # Invoke handler
    response_content = await ctx.step.run(
        "invoke-handler",
        lambda: handler(content),
    )
    
    # Persist response
    await ctx.step.run(
        "persist-response",
        lambda: communication_service.save_message(
            CreateMessageRequest(
                from_agent_id=UUID(to_agent_id),
                to_agent_id=UUID(from_agent_id),
                thread_topic=topic,
                content=response_content,
            )
        ),
    )
    
    # Emit response event
    await ctx.step.send_event(
        "emit-response",
        [inngest.SendEventRequest(
            name=COMM_RESPONSE,
            data={
                "correlation_id": correlation_id,
                "content": response_content,
            },
        )],
    )
    
    return {"status": "ok"}
```

---

## The CommunicationRunner (Recommended)

Like `EvaluationRunner`, a thin wrapper that hides Inngest details:

### File: `h_arcane/core/communication/runner.py`

```python
"""Communication runner - wraps Inngest for agent messaging."""

from uuid import UUID, uuid4
from datetime import timedelta
from typing import Protocol

import inngest

from h_arcane.core.communication.events import COMM_ASK, COMM_RESPONSE


class CommunicationRunner:
    """
    Handles inter-agent communication via Inngest events.
    
    Wraps Inngest context so tools/toolkits don't need to know about Inngest.
    Similar pattern to EvaluationRunner.
    """
    
    def __init__(
        self,
        inngest_ctx: inngest.Context,
        agent_id: UUID,
        default_topic: str = "default",
    ):
        """
        Initialize runner.
        
        Args:
            inngest_ctx: Inngest context (for step.send_event, step.wait_for_event)
            agent_id: This agent's ID (the "from" in messages)
            default_topic: Default conversation topic
        """
        self.inngest_ctx = inngest_ctx
        self.agent_id = agent_id
        self.default_topic = default_topic
        self._message_count = 0
    
    async def ask(
        self,
        to_agent_id: UUID,
        content: str,
        topic: str | None = None,
        timeout_seconds: int = 60,
    ) -> str:
        """
        Send a message to another agent and wait for response.
        
        Args:
            to_agent_id: Recipient agent ID
            content: Message content
            topic: Conversation topic (uses default if not specified)
            timeout_seconds: How long to wait for response
            
        Returns:
            Response content from the other agent
        """
        correlation_id = str(uuid4())
        topic = topic or self.default_topic
        step_suffix = f"{self._message_count}-{correlation_id[:8]}"
        
        # Send ask event
        await self.inngest_ctx.step.send_event(
            f"comm-ask-{step_suffix}",
            [inngest.SendEventRequest(
                name=COMM_ASK,
                data={
                    "from_agent_id": str(self.agent_id),
                    "to_agent_id": str(to_agent_id),
                    "topic": topic,
                    "content": content,
                    "correlation_id": correlation_id,
                },
            )],
        )
        
        # Wait for response
        response = await self.inngest_ctx.step.wait_for_event(
            f"comm-wait-{step_suffix}",
            event=COMM_RESPONSE,
            if_exp=f"async.data.correlation_id == '{correlation_id}'",
            timeout=timedelta(seconds=timeout_seconds),
        )
        
        self._message_count += 1
        
        if response is None:
            return "[Timeout waiting for response]"
        
        if response.data.get("error"):
            return response.data["content"]
        
        return response.data["content"]
    
    @property
    def messages_sent(self) -> int:
        """Number of messages sent by this runner."""
        return self._message_count
```

### Optional: Protocol for Testing

```python
class Communicator(Protocol):
    """Protocol for communication - allows easy mocking."""
    
    async def ask(
        self,
        to_agent_id: UUID,
        content: str,
        topic: str | None = None,
        timeout_seconds: int = 60,
    ) -> str: ...
    
    @property
    def messages_sent(self) -> int: ...
```

---

## Using It In Tools

### Toolkit receives CommunicationRunner (not raw step)

```python
class GDPEvalToolkit:
    def __init__(
        self,
        comm: CommunicationRunner,  # Wraps Inngest - toolkit doesn't know about it
        stakeholder_id: UUID,
        sandbox_manager: BaseSandboxManager,
    ):
        self.comm = comm
        self.stakeholder_id = stakeholder_id
        self.sandbox_manager = sandbox_manager
    
    @property
    def questions_asked(self) -> int:
        return self.comm.messages_sent
    
    def _ask_stakeholder(self) -> Tool:
        @function_tool
        async def ask_stakeholder(question: str) -> str:
            """Ask the stakeholder a question."""
            return await self.comm.ask(
                to_agent_id=self.stakeholder_id,
                content=question,
                topic="task_clarification",
            )
        return ask_stakeholder
```

**The toolkit doesn't import inngest. Doesn't know about events. Just uses `comm.ask()`.**

---

## What Toolkits Need

**Minimal requirements for a toolkit that does communication:**

```python
class GDPEvalToolkit:
    def __init__(
        self,
        comm: CommunicationRunner,   # Handles all communication
        stakeholder_id: UUID,        # Who to ask
        sandbox_manager: ...,        # Other stuff
    ):
        self.comm = comm
        self.stakeholder_id = stakeholder_id
        self.sandbox_manager = sandbox_manager
```

That's it. No base class. No mixin. No Inngest imports in the toolkit.

---

## Orchestration Setup

```python
@inngest_client.create_function(
    fn_id="worker-execute",
    trigger=inngest.TriggerEvent(event="run/execute"),
)
async def worker_execute(ctx: inngest.Context) -> dict:
    # ... load experiment, etc ...
    
    # Create agent IDs
    worker_id = uuid4()
    stakeholder_id = uuid4()
    
    # Create stakeholder
    stakeholder = benchmark.create_stakeholder(experiment)
    
    # Register stakeholder handler
    from h_arcane.core.communication import registry
    registry.register(stakeholder_id, stakeholder.answer)
    
    try:
        # Create communication runner (wraps Inngest context)
        comm = CommunicationRunner(
            inngest_ctx=ctx,
            agent_id=worker_id,
            default_topic="task_clarification",
        )
        
        # Create toolkit - receives runner, not raw ctx
        toolkit = GDPEvalToolkit(
            comm=comm,
            stakeholder_id=stakeholder_id,
            sandbox_manager=sandbox_manager,
        )
        
        # Run worker
        result = await worker.execute(toolkit=toolkit, ...)
        
        return {"status": "ok", "result": result}
        
    finally:
        registry.unregister(stakeholder_id)
```

---

## File Structure

```
h_arcane/core/communication/
├── __init__.py         # Exports
├── schemas.py          # Pydantic schemas (existing)
├── service.py          # CommunicationService for DB ops (existing)
├── events.py           # Event name constants (NEW, 3 lines)
├── registry.py         # Agent handler registry (NEW, ~20 lines)
├── handler.py          # Inngest function (NEW, ~60 lines)
└── runner.py           # CommunicationRunner (NEW, ~60 lines)
```

**Total new code: ~150 lines**

---

## Summary

| Component | What it is |
|-----------|------------|
| `events.py` | Two constants: `COMM_ASK`, `COMM_RESPONSE` |
| `registry.py` | A dict mapping agent_id → handler |
| `handler.py` | One Inngest function that routes messages |
| `runner.py` | `CommunicationRunner` - wraps Inngest, exposes `ask()` |

**No mixin. No base class. Toolkits don't import Inngest.**

The pattern mirrors `EvaluationRunner`:
- Orchestration creates the runner with Inngest context
- Toolkits/rules receive the runner
- They call `runner.ask()` or `runner.step()` without knowing about Inngest

---

## Multi-Agent: Just Works

```python
# Register multiple agents
registry.register(stakeholder_1_id, stakeholder_1.answer)
registry.register(stakeholder_2_id, stakeholder_2.answer)
registry.register(worker_b_id, worker_b.handle_message)

# Each worker gets its own CommunicationRunner
comm_a = CommunicationRunner(ctx, agent_id=worker_a_id)
comm_b = CommunicationRunner(ctx, agent_id=worker_b_id)

# Workers can message anyone
await comm_a.ask(to_agent_id=stakeholder_1_id, content="...")
await comm_a.ask(to_agent_id=worker_b_id, content="...")
```

---

## Testing: Easy to Mock

```python
class MockCommunicator:
    """Mock for testing - no Inngest needed."""
    
    def __init__(self, responses: dict[UUID, str]):
        self.responses = responses
        self.messages_sent = 0
        self.sent_messages: list[tuple[UUID, str]] = []
    
    async def ask(self, to_agent_id: UUID, content: str, **kwargs) -> str:
        self.sent_messages.append((to_agent_id, content))
        self.messages_sent += 1
        return self.responses.get(to_agent_id, "Mock response")

# In tests:
mock_comm = MockCommunicator(responses={stakeholder_id: "Use JSON format"})
toolkit = GDPEvalToolkit(comm=mock_comm, stakeholder_id=stakeholder_id, ...)

# Toolkit works without any Inngest infrastructure
```

---

## Comparison with Previous Approaches

| Approach | Toolkit knows about | Testability |
|----------|---------------------|-------------|
| Raw `step` in toolkit | Inngest internals | Hard (need Inngest) |
| Mixin | Base class, Inngest | Medium |
| **CommunicationRunner** | Just `ask()` method | Easy (mock runner) |

The runner pattern is the cleanest because:
1. **Consistent** with existing `EvaluationRunner` pattern
2. **Decoupled** - toolkits don't know about Inngest
3. **Testable** - just mock the runner
4. **Minimal** - one simple class, one method
