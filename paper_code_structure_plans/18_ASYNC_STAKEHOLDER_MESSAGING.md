# 18. Async Stakeholder Messaging via Inngest Events

## Overview

Transform stakeholder interaction from a synchronous tool call into an **async event-driven interaction** brokered by the `CommunicationService`. This enables true agent-to-agent messaging where both worker and stakeholder are independent agents communicating via Inngest events.

---

## Current State

```
Worker Tool Call (sync)
    └── Toolkit.ask_stakeholder(question)
           ├── queries.messages.create(...)  ← save worker message
           ├── stakeholder.answer(question)  ← SYNC CALL - blocks
           └── queries.messages.create(...)  ← save stakeholder response
```

**Problems:**
- Stakeholder is not a real agent - just a function call
- No true async communication
- Tight coupling between worker and stakeholder
- Can't scale to multi-agent scenarios

---

## Target Architecture

```
                    ┌─────────────────────────────────────────────────┐
                    │              CommunicationService               │
                    │  (Message Broker + Inngest Event Emitter)       │
                    └─────────────────────────────────────────────────┘
                                ▲                    │
                                │                    ▼
                    ┌───────────┴────────┐  ┌───────────────────────┐
                    │   message/sent     │  │   message/received    │
                    │   (correlation_id) │  │   (correlation_id)    │
                    └────────────────────┘  └───────────────────────┘
                                ▲                    │
                                │                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │                                                                     │
    │  ┌──────────────────┐                     ┌────────────────────┐   │
    │  │  Worker Agent    │                     │ Stakeholder Agent  │   │
    │  │                  │                     │                    │   │
    │  │  1. Call tool    │ ─── message/sent ──►│ 3. Inngest trigger │   │
    │  │  2. step.wait_for│                     │ 4. agent.run()     │   │
    │  │  5. Resume       │◄─ message/received ─│ 5. save_message()  │   │
    │  │  6. Return answer│                     │                    │   │
    │  └──────────────────┘                     └────────────────────┘   │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Extend CommunicationService with Event Emission

#### 1.1 Add Inngest Client to CommunicationService

```python
# h_arcane/core/communication/service.py

from h_arcane.core.infrastructure.inngest_client import inngest_client
from h_arcane.core.communication.schemas import MessageSentEvent
from uuid import uuid4

class CommunicationService:
    """Service for managing agent-to-agent communication."""
    
    async def send_message(
        self,
        request: CreateMessageRequest,
        emit_event: bool = True,
    ) -> tuple[MessageResponse, str]:
        """Save a message AND emit an Inngest event for the recipient.
        
        Args:
            request: Message creation request
            emit_event: Whether to emit message/sent event (default True)
            
        Returns:
            Tuple of (MessageResponse, correlation_id)
        """
        # Generate correlation ID for request/response pairing
        correlation_id = str(uuid4())
        
        # Save message to database (existing logic)
        response = self.save_message(request)
        
        if emit_event:
            # Create strongly-typed event payload
            event_payload = MessageSentEvent.from_message_response(
                response=response,
                correlation_id=correlation_id,
            )
            
            # Emit event for recipient agent
            # mode='json' ensures UUIDs are serialized as strings
            await inngest_client.send(
                inngest.Event(
                    name="message/sent",
                    data=event_payload.model_dump(mode="json"),
                )
            )
        
        return response, correlation_id
```

#### 1.2 New Schemas for Event-Driven Messaging

```python
# h_arcane/core/communication/schemas.py

class SendMessageRequest(CreateMessageRequest):
    """Extended request that includes correlation tracking."""
    correlation_id: str | None = None  # Auto-generated if not provided


class MessageSentEvent(BaseModel):
    """Payload for message/sent Inngest event.
    
    Use model_dump(mode='json') when emitting to ensure UUID serialization.
    Use model_validate(data) when parsing from ctx.event.data.
    """
    correlation_id: str
    message_id: UUID
    thread_id: UUID
    run_id: UUID
    experiment_id: UUID
    from_agent_id: str
    to_agent_id: str
    content: str
    thread_topic: str
    
    @classmethod
    def from_message_response(
        cls,
        response: MessageResponse,
        correlation_id: str,
    ) -> "MessageSentEvent":
        """Create event payload from a MessageResponse."""
        return cls(
            correlation_id=correlation_id,
            message_id=response.message_id,
            thread_id=response.thread_id,
            run_id=response.run_id,
            experiment_id=response.experiment_id,
            from_agent_id=response.from_agent_id,
            to_agent_id=response.to_agent_id,
            content=response.content,
            thread_topic=response.thread_topic,
        )


class MessageReceivedEvent(BaseModel):
    """Payload for message/received Inngest event (response).
    
    Use model_dump(mode='json') when emitting to ensure UUID serialization.
    Use model_validate(data) when parsing from ctx.event.data.
    """
    correlation_id: str  # Matches original message/sent
    message_id: UUID
    thread_id: UUID
    run_id: UUID
    experiment_id: UUID
    from_agent_id: str
    to_agent_id: str
    content: str
    thread_topic: str
    
    @classmethod
    def from_message_response(
        cls,
        response: MessageResponse,
        correlation_id: str,
    ) -> "MessageReceivedEvent":
        """Create event payload from a MessageResponse."""
        return cls(
            correlation_id=correlation_id,
            message_id=response.message_id,
            thread_id=response.thread_id,
            run_id=response.run_id,
            experiment_id=response.experiment_id,
            from_agent_id=response.from_agent_id,
            to_agent_id=response.to_agent_id,
            content=response.content,
            thread_topic=response.thread_topic,
        )
```

---

### Phase 2: Worker Tool with step.wait_for

#### 2.1 Update Toolkit ask_stakeholder Tool

```python
# h_arcane/benchmarks/researchrubrics/toolkit.py (and others)

from h_arcane.core.orchestration.step_context import get_step  # Inngest step context
from h_arcane.core.communication.service import communication_service
from h_arcane.core.communication.schemas import CreateMessageRequest, MessageReceivedEvent

class ResearchRubricsToolkit(BaseToolkit):
    """Toolkit with async stakeholder messaging."""
    
    async def ask_stakeholder(self, question: str) -> str:
        """Ask the stakeholder a question via async messaging.
        
        Flow:
        1. Get Inngest step context (works in any Python function via contextvars)
        2. Send message via CommunicationService (emits message/sent)
        3. Wait for message/received event with matching correlation_id
        4. Return stakeholder's response
        """
        # 1. Get Inngest step context
        # This works because set_step() was called in worker_execute
        # and contextvars propagate through async/await
        step = get_step()
        if step is None:
            raise RuntimeError("ask_stakeholder must be called within Inngest context")
        
        # Check question limit
        if self._questions_asked >= self._max_questions:
            return f"Question limit ({self._max_questions}) reached. Cannot ask more questions."
        
        self._questions_asked += 1
        
        # 2. Send message and emit event
        worker_agent_id = f"{self._run_id}:worker"
        stakeholder_agent_id = f"{self._run_id}:stakeholder"
        
        response, correlation_id = await step.run(
            f"send-question-{self._questions_asked}",
            lambda: communication_service.send_message(
                CreateMessageRequest(
                    run_id=self._run_id,
                    experiment_id=self._experiment_id,
                    from_agent_id=worker_agent_id,
                    to_agent_id=stakeholder_agent_id,
                    thread_topic="stakeholder_qa",
                    content=question,
                )
            ),
        )
        
        # 3. Wait for response event with matching correlation_id
        response_event = await step.wait_for_event(
            f"wait-stakeholder-response-{self._questions_asked}",
            event="message/received",
            timeout="5m",  # 5 minute timeout
            if_exp=f"async.data.correlation_id == '{correlation_id}'",
        )
        
        if response_event is None:
            return "Stakeholder did not respond in time."
        
        # 4. Parse response into strongly-typed model and return content
        response = MessageReceivedEvent.model_validate(response_event.data)
        return response.content
```

---

### Phase 3: Generic Agent React Pattern

**Design Goal**: Instead of a stakeholder-specific handler, create a **generic agent reaction pattern** 
that aligns with the ma_gym architecture. This future-proofs for multi-agent scenarios.

#### 3.1 Agent Protocol (Minimal Interface)

Following the ma_gym pattern of minimal protocol interfaces:

```python
# h_arcane/core/agents/protocol.py

from typing import Protocol
from pydantic import BaseModel, ConfigDict

class AgentObservation(BaseModel):
    """Base observation for any agent - what the agent can see."""
    model_config = ConfigDict(frozen=True)
    
    agent_id: str
    run_id: UUID
    experiment_id: UUID
    observed_at: datetime
    
    # Messages addressed to this agent since last observation
    pending_messages: list[MessageResponse]
    
    # Optional: other context as needed per agent type
    context: dict = {}


class AgentResponse(BaseModel):
    """Base response from any agent."""
    model_config = ConfigDict(frozen=True)
    
    content: str
    metadata: dict = {}


class ReactiveAgent(Protocol):
    """
    Protocol: Minimal interface for agents that react to observations.
    
    Matches ma_gym pattern: single method, observation in → response out.
    Stateless: all context comes via observation.
    """
    
    @property
    def agent_id(self) -> str:
        """Unique identifier for this agent."""
        ...
    
    async def react(self, observation: AgentObservation) -> AgentResponse:
        """React to an observation and produce a response."""
        ...
```

#### 3.2 Agent Registry

```python
# h_arcane/core/agents/registry.py

from typing import Callable
from uuid import UUID

# Factory type: given run context, returns a ReactiveAgent
AgentFactory = Callable[[UUID, UUID], ReactiveAgent]  # (run_id, experiment_id) -> agent

# Registry of agent factories by agent_id pattern
_agent_factories: dict[str, AgentFactory] = {}


def register_agent_factory(pattern: str, factory: AgentFactory) -> None:
    """Register a factory for agents matching a pattern.
    
    Args:
        pattern: Suffix pattern like ":stakeholder", ":worker", etc.
        factory: Function that creates the agent given run/experiment IDs
    """
    _agent_factories[pattern] = factory


def get_agent_factory(agent_id: str) -> AgentFactory | None:
    """Get factory for an agent_id by matching suffix patterns."""
    for pattern, factory in _agent_factories.items():
        if agent_id.endswith(pattern):
            return factory
    return None


def build_agent(agent_id: str, run_id: UUID, experiment_id: UUID) -> ReactiveAgent | None:
    """Build an agent instance from registry."""
    factory = get_agent_factory(agent_id)
    if factory is None:
        return None
    return factory(run_id, experiment_id)
```

#### 3.3 Adapt Stakeholder to ReactiveAgent Protocol

```python
# h_arcane/benchmarks/researchrubrics/stakeholder.py (updated)

from h_arcane.core.agents.protocol import ReactiveAgent, AgentObservation, AgentResponse

class RubricAwareStakeholder(ReactiveAgent):
    """Stakeholder that conforms to ReactiveAgent protocol."""
    
    def __init__(self, agent_id: str, experiment: Experiment, model: str | None = None):
        self._agent_id = agent_id
        self._experiment = experiment
        self._model = model or evaluation_config.llm_stakeholder.model
        # ... rest of init
    
    @property
    def agent_id(self) -> str:
        return self._agent_id
    
    async def react(self, observation: AgentObservation) -> AgentResponse:
        """React to pending messages."""
        if not observation.pending_messages:
            return AgentResponse(content="", metadata={"no_action": True})
        
        # Get the latest message to respond to
        latest_message = observation.pending_messages[-1]
        
        # History is all messages except the latest
        history = observation.pending_messages[:-1]
        
        # Generate response using existing answer() logic
        answer = await self.answer(
            question=latest_message.content,
            history=history,
        )
        
        return AgentResponse(
            content=answer,
            metadata={
                "responding_to_message_id": str(latest_message.message_id),
            }
        )
```

#### 3.4 Generic Agent React Handler

```python
# h_arcane/core/orchestration/agent_react.py

import inngest
from datetime import datetime, timezone
from uuid import UUID

from h_arcane.core.infrastructure.inngest_client import inngest_client
from h_arcane.core.communication.service import communication_service
from h_arcane.core.communication.schemas import (
    CreateMessageRequest,
    MessageSentEvent,
    MessageReceivedEvent,
)
from h_arcane.core.agents.registry import build_agent
from h_arcane.core.agents.protocol import AgentObservation


@inngest_client.create_function(
    fn_id="agent-react",
    trigger=inngest.TriggerEvent(event="message/sent"),
    # BATCHING: Collect messages for same agent within 500ms window
    batch=inngest.Batch(max_size=10, timeout="500ms"),
    retries=2,
    concurrency=[inngest.Concurrency(limit=25, scope="fn")],
)
async def agent_react(ctx: inngest.Context) -> dict:
    """
    Generic agent reaction handler.
    
    Triggered by: message/sent events (batched)
    
    Pattern (aligned with ma_gym manager_react):
    1. Collect all pending context addressed to this agent
    2. Look up agent from registry by ID
    3. Build observation (messages + context)
    4. Call agent.react(observation)
    5. Apply response (save message, emit events)
    
    This generalizes beyond stakeholders to ANY reactive agent.
    """
    # Parse all events in batch
    events = [MessageSentEvent.model_validate(e.data) for e in ctx.events]
    
    # Group by recipient agent
    by_recipient: dict[str, list[MessageSentEvent]] = {}
    for event in events:
        recipient = event.to_agent_id
        if recipient not in by_recipient:
            by_recipient[recipient] = []
        by_recipient[recipient].append(event)
    
    results = []
    
    for recipient_agent_id, recipient_events in by_recipient.items():
        # Get context from first event (all should be same run/experiment)
        first_event = recipient_events[0]
        run_id = first_event.run_id
        experiment_id = first_event.experiment_id
        
        # 1. Build agent from registry
        agent = await ctx.step.run(
            f"build-agent-{recipient_agent_id}",
            lambda: build_agent(recipient_agent_id, run_id, experiment_id),
        )
        
        if agent is None:
            results.append({
                "agent_id": recipient_agent_id,
                "status": "skipped",
                "reason": "no_agent_registered",
            })
            continue
        
        # 2. Collect pending messages for this agent
        # (In a full implementation, we'd query all unprocessed messages)
        pending_messages = await ctx.step.run(
            f"get-pending-messages-{recipient_agent_id}",
            lambda: [
                communication_service.get_message(e.message_id)
                for e in recipient_events
            ],
        )
        
        # 3. Build observation
        observation = AgentObservation(
            agent_id=recipient_agent_id,
            run_id=run_id,
            experiment_id=experiment_id,
            observed_at=datetime.now(timezone.utc),
            pending_messages=[m for m in pending_messages if m is not None],
            context={},  # Could add benchmark-specific context
        )
        
        # 4. Run agent reaction
        response = await ctx.step.run(
            f"agent-react-{recipient_agent_id}",
            lambda: agent.react(observation),
        )
        
        if response.metadata.get("no_action"):
            results.append({
                "agent_id": recipient_agent_id,
                "status": "no_action",
            })
            continue
        
        # 5. Save response and emit events for each original message
        for event in recipient_events:
            await ctx.step.run(
                f"save-response-{event.correlation_id}",
                lambda e=event: _save_and_emit_response(
                    event=e,
                    response_content=response.content,
                    agent_id=recipient_agent_id,
                ),
            )
        
        results.append({
            "agent_id": recipient_agent_id,
            "status": "success",
            "messages_processed": len(recipient_events),
        })
    
    return {"results": results}


async def _save_and_emit_response(
    event: MessageSentEvent,
    response_content: str,
    agent_id: str,
) -> None:
    """Save response message and emit message/received event."""
    # Save the response
    response = communication_service.save_message(
        CreateMessageRequest(
            run_id=event.run_id,
            experiment_id=event.experiment_id,
            from_agent_id=agent_id,  # Responding agent
            to_agent_id=event.from_agent_id,  # Original sender
            thread_topic=event.thread_topic,
            content=response_content,
        )
    )
    
    # Emit response event with correlation_id
    response_event = MessageReceivedEvent.from_message_response(
        response=response,
        correlation_id=event.correlation_id,
    )
    
    await inngest_client.send(
        inngest.Event(
            name="message/received",
            data=response_event.model_dump(mode="json"),
        )
    )
```

#### 3.5 Register Stakeholder Factory at Startup

```python
# h_arcane/benchmarks/researchrubrics/factories.py (updated)

from h_arcane.core.agents.registry import register_agent_factory

def create_stakeholder_agent(run_id: UUID, experiment_id: UUID) -> RubricAwareStakeholder:
    """Factory for creating stakeholder agents."""
    experiment = queries.experiments.get(experiment_id)
    agent_id = f"{run_id}:stakeholder"
    return RubricAwareStakeholder(agent_id, experiment)

# Register at module load
register_agent_factory(":stakeholder", create_stakeholder_agent)
```

---

### Phase 4: Update Inngest Step Context Management

#### 4.1 Ensure Step Context is Available in Tools

**Important**: This uses Python's `contextvars` which works in ANY Python function - 
not just OpenAI SDK function tools. The context variable is set once at the start of 
`worker_execute` and remains available throughout that async execution context, including:
- Regular async functions
- Toolkit methods
- OpenAI function tools
- Nested function calls

```python
# h_arcane/core/orchestration/step_context.py (NEW FILE - separate from tracing.py)

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import inngest

# Context variable for Inngest step
# Works in ANY Python function within the same async execution context
_step_context: ContextVar["inngest.Step | None"] = ContextVar("step_context", default=None)


def set_step(step: "inngest.Step") -> None:
    """Set the Inngest step context for the current execution.
    
    Call this once at the start of an Inngest function (e.g., worker_execute).
    The step will be available to all code called within that function via get_step().
    
    Note: contextvars automatically propagate through async/await, so nested
    async functions will have access to the step without explicit passing.
    """
    _step_context.set(step)


def get_step() -> "inngest.Step | None":
    """Get the current Inngest step context, if any.
    
    Returns None if called outside of an Inngest function context.
    
    Works in:
    - Regular Python functions
    - Async functions
    - OpenAI SDK function tools
    - Any code called from within the Inngest function
    
    Example:
        step = get_step()
        if step is not None:
            result = await step.run("my-step", my_async_fn)
    """
    return _step_context.get()
```

#### 4.2 Set Step Context in worker_execute

```python
# h_arcane/core/orchestration/worker_execute.py

from h_arcane.core.orchestration.step_context import set_step

@inngest_client.create_function(...)
async def worker_execute(ctx: inngest.Context) -> dict:
    # ... existing setup ...
    
    # Set step context BEFORE any tool execution
    # This makes ctx.step available to all toolkit methods via get_step()
    set_step(ctx.step)
    
    # ... rest of execution ...
    # All toolkit.ask_stakeholder() calls can now access step via get_step()
```

#### 4.3 Why This Works

Python's `contextvars` module provides task-local storage that automatically
propagates through async/await boundaries. When you call `set_step(ctx.step)`:

1. The value is stored in the current async task's context
2. Any function called within that task can access it via `get_step()`
3. Works regardless of call depth or function type
4. Does NOT leak to other concurrent tasks

This is fundamentally different from thread-local storage which wouldn't
work correctly with async code.

---

## Event Flow Diagram

```
Timeline:
─────────────────────────────────────────────────────────────────────────────►

Worker (worker_execute)                    Agent React Handler (generic)
        │                                           │
        │  1. ask_stakeholder("What format?")       │
        │      └─► get_step()                       │
        │      └─► communication_service.send_message()
        │          └─► save to DB                   │
        │          └─► emit "message/sent" ─────────┼─────────────────┐
        │                                           │                 │
        │  2. step.wait_for_event(                  │                 ▼
        │       "message/received",                 │      Inngest triggers
        │       correlation_id=xyz)                 │      agent_react (batched)
        │          │                                │                 │
        │          │ (WAITING)                      │  3. Look up agent by ID
        │          │                                │     (registry pattern)
        │          │                                │  4. Build AgentObservation
        │          │                                │  5. agent.react(observation)
        │          │                                │  6. save_message() to DB
        │          │                                │  7. emit "message/received"
        │          │                                │      (correlation_id=xyz)
        │          │◄───────────────────────────────┼─────────────────┘
        │          │                                │
        │  8. Resume, return answer                 │
        ▼                                           ▼

Key: Generic handler works for ANY agent type registered in the registry.
     Stakeholder, worker, or future agent types all use the same flow.
```

---

## Key Design Decisions

### 1. Correlation ID Pattern
- Each message gets a unique `correlation_id`
- Response events include the same `correlation_id`
- `step.wait_for_event` filters by `correlation_id` to match request/response

### 2. Strongly-Typed Event Payloads
- `MessageSentEvent` and `MessageReceivedEvent` are Pydantic models
- Use `model_dump(mode="json")` when emitting (serializes UUIDs as strings)
- Use `model_validate(ctx.event.data)` when receiving (parses + validates)
- Factory methods (`from_message_response()`) for clean construction

### 3. CommunicationService as Single Source of Truth
- All messages flow through `CommunicationService`
- Service handles both persistence AND event emission
- Decouples agents from Inngest internals

### 4. Generic Agent React Pattern (ma_gym Aligned)
- **`ReactiveAgent` protocol** - minimal interface: `react(observation) -> response`
- **Agent registry** - look up agents by ID pattern (`:stakeholder`, `:worker`, etc.)
- **Generic `agent_react` handler** - single Inngest function for ALL reactive agents
- **Batching support** - coalesce rapid-fire messages to same agent
- Future-proof for multi-agent scenarios without new handlers

### 5. Step Context via ContextVar
- Tools need access to Inngest step for `step.wait_for_event`
- Use Python's `contextvars` (NOT thread-local) - works with async
- Set once at start of `worker_execute`, available to ALL code in that context
- Works in regular functions, toolkit methods, OpenAI tools - anything

---

## File Changes Summary

| File | Changes |
|------|---------|
| `h_arcane/core/communication/service.py` | Add `send_message()` with event emission |
| `h_arcane/core/communication/schemas.py` | Add `MessageSentEvent`, `MessageReceivedEvent` with factory methods |
| `h_arcane/core/orchestration/step_context.py` | **NEW** - `set_step()`, `get_step()` via contextvars |
| `h_arcane/core/agents/protocol.py` | **NEW** - `ReactiveAgent` protocol, `AgentObservation`, `AgentResponse` |
| `h_arcane/core/agents/registry.py` | **NEW** - Agent registry for lookup by ID pattern |
| `h_arcane/core/orchestration/agent_react.py` | **NEW** - Generic Inngest handler for all reactive agents |
| `h_arcane/core/orchestration/worker_execute.py` | Add `set_step(ctx.step)` call |
| `h_arcane/benchmarks/*/toolkit.py` | Update `ask_stakeholder` to use async pattern |
| `h_arcane/benchmarks/*/stakeholder.py` | Implement `ReactiveAgent` protocol |
| `h_arcane/benchmarks/*/factories.py` | Register stakeholder factory with agent registry |
| `h_arcane/core/infrastructure/inngest_client.py` | Register `agent_react` function |

---

## Alignment with ma_gym Architecture

This design is intentionally aligned with the `ma_gym_code` plans:

| ma_gym Concept | This Implementation |
|----------------|---------------------|
| `manager_react` batched handler | `agent_react` generic handler |
| `ManagerObservation` | `AgentObservation` (generic) |
| `ManagerAction` | `AgentResponse` (generic) |
| `ManagerAgent.decide()` | `ReactiveAgent.react()` |
| Event-driven waking | `message/sent` triggers `agent_react` |
| Observation snapshots | `pending_messages` + `context` |

**Key Pattern**: Agents don't know about communication internals. They receive an observation, 
produce a response, and the orchestration layer handles persistence and event emission.

---

## Migration Strategy

### Step 1: Add Infrastructure (Non-Breaking)
1. Add `MessageSentEvent`, `MessageReceivedEvent` schemas with factory methods
2. Add `send_message()` method (keep `save_message()` working)
3. Create `step_context.py` with `set_step()` / `get_step()`
4. Create `protocol.py` with `ReactiveAgent`, `AgentObservation`, `AgentResponse`
5. Create `registry.py` with agent factory registration

### Step 2: Create Generic Handler
1. Create `agent_react.py` generic Inngest handler
2. Add batching support for rapid-fire messages

### Step 3: Update One Benchmark (ResearchRubrics)
1. Update `RubricAwareStakeholder` to implement `ReactiveAgent`
2. Register factory in `factories.py`
3. Update toolkit to use async pattern
4. Test end-to-end

### Step 4: Migrate Other Benchmarks
1. Update GDPEval stakeholder
2. Update MiniF2F stakeholder

### Step 5: Clean Up
1. Remove old synchronous `ask_stakeholder` implementations
2. Update documentation

---

## Testing Plan

### Unit Tests
- `test_communication_service_emits_event`: Verify event emission
- `test_correlation_id_matching`: Verify correlation ID flow

### Integration Tests
- `test_worker_stakeholder_roundtrip`: Full async message exchange
- `test_conversation_history_preserved`: Multi-turn conversation
- `test_timeout_handling`: Stakeholder doesn't respond in time

### E2E Tests
- Run full experiment with async messaging
- Compare results with sync baseline

---

## Future Extensions

With the generic `ReactiveAgent` pattern, extensions become trivial:

1. **Multi-Stakeholder**: Register multiple stakeholder factories (`:stakeholder-a`, `:stakeholder-b`)
2. **Agent-to-Agent**: Any agent implementing `ReactiveAgent` just works
3. **Parallel Questions**: Worker emits multiple `message/sent` events, waits for all `message/received`
4. **New Agent Types**: Register factory → implement `ReactiveAgent` → done
5. **Observation Enrichment**: Add benchmark-specific context to `AgentObservation.context`
6. **Action Recording**: Log all agent reactions to `agent_actions` table (ma_gym pattern)
7. **Rate Limiting**: Add at registry or handler level

---

## Open Questions

1. **Timeout Value**: What's appropriate timeout for agent response?
   - Current: 5 minutes
   - Consider: Per-agent-type configuration in registry?

2. **Retry Semantics**: If agent fails, should caller retry?
   - Current: Caller gets timeout, returns "no response"
   - Consider: Auto-retry with exponential backoff?

3. **Event Naming**: `message/sent` vs `communication/ask`?
   - Decided: `message/sent` for generality (ma_gym aligned)

4. **Agent Factory Caching**: Create fresh each time or cache?
   - Current plan: Create fresh (stateless agents)
   - Consider: Cache per run if agents have expensive init?

5. **Observation Scope**: What context goes in `AgentObservation.context`?
   - Stakeholder: rubric criteria, task description
   - Worker: sandbox state, available tools
   - Consider: Per-agent-type observation subclasses?

6. **Action Recording**: Should we log agent reactions to `agent_actions` table?
   - ma_gym does this for training data
   - Would enable training stakeholder agents too

