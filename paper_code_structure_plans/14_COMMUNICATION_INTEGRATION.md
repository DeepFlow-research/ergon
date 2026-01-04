# 14. Communication Service Integration Plan

## Current State Analysis

### Pain Points
1. **Duplicated `ask_stakeholder` logic** across all toolkits (GDPEval, MiniF2F, ResearchRubrics)
2. **Direct coupling** to `queries.messages` (run-level Message model)
3. **Toolkit bloat**: Each toolkit maintains `run_id`, `_message_num`, `_questions_asked`, `stakeholder` reference
4. **Not scalable to multi-agent**: Current model assumes 1 worker + 1 stakeholder per run

### Current Flow
```
Worker Tool Call
    └── Toolkit.ask_stakeholder(question)
           ├── queries.messages.create(Message(run_id=..., sender=WORKER, ...))
           ├── stakeholder.answer(question)
           └── queries.messages.create(Message(run_id=..., sender=STAKEHOLDER, ...))
```

---

## Design Goals

1. **Lean agent interfaces** - Agents shouldn't know about communication internals
2. **Multi-agent scalability** - N workers, M stakeholders, P×Q connections
3. **Single source of truth** - All messages flow through one service
4. **Backward compatibility** - Existing run-level Message logging still works
5. **Testability** - Easy to mock/stub communication for tests

---

## Recommended Architecture: Message Broker Pattern

### Why Not DI into Every Agent?

Injecting `CommunicationService` directly into workers/stakeholders:
- **Bloats agent interfaces** with communication concerns
- **Tight coupling** - agents need to know about thread IDs, topics, etc.
- **Hard to change** - if communication model changes, all agents change

### Why Message Broker?

A **MessageBroker** acts as a thin routing layer:
- Agents only need their own ID and the broker reference
- Broker handles: routing, thread management, logging, limits
- Scales naturally: broker maps agent_id → agent_id communication
- Single point for adding features (rate limiting, encryption, etc.)

---

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Orchestration Layer                           │
│  (Creates broker, registers agents, passes broker to toolkits)          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            MessageBroker                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  - register_agent(agent_id, handler)                            │   │
│  │  - send(from_id, to_id, topic, content) → response              │   │
│  │  - get_conversation(agent_a, agent_b, topic) → messages         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│                     Uses internally:                                    │
│                                    ▼                                    │
│              ┌─────────────────────────────────┐                       │
│              │     CommunicationService        │                       │
│              │  (Persistence layer)            │                       │
│              └─────────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────────────┘
                          ▲                    ▲
                          │                    │
               ┌──────────┴──────┐    ┌───────┴────────┐
               │                 │    │                │
         ┌─────┴─────┐     ┌─────┴────┴┐     ┌────────┴────────┐
         │  Worker   │     │  Worker   │     │   Stakeholder   │
         │  Agent    │     │  Agent    │     │     Agent       │
         │  (id: A)  │     │  (id: B)  │     │     (id: S1)    │
         └───────────┘     └───────────┘     └─────────────────┘
```

---

## Implementation Plan

### Phase 1: Core Broker Implementation

#### File: `h_arcane/core/communication/broker.py`

```python
"""Message broker for inter-agent communication."""

from uuid import UUID
from typing import Callable, Awaitable
from dataclasses import dataclass, field

from h_arcane.core.communication.service import communication_service
from h_arcane.core.communication.schemas import CreateMessageRequest, MessageResponse


@dataclass
class AgentRegistration:
    """Registration info for an agent."""
    agent_id: UUID
    agent_type: str  # "worker", "stakeholder", etc.
    handler: Callable[[str], Awaitable[str]]  # async function to handle incoming messages
    max_incoming_messages: int | None = None  # Optional limit


class MessageBroker:
    """
    Central broker for all agent-to-agent communication.
    
    The broker:
    1. Maintains a registry of active agents
    2. Routes messages between agents
    3. Persists all messages via CommunicationService
    4. Enforces limits (max questions, etc.)
    """
    
    def __init__(self, run_id: UUID | None = None):
        """
        Initialize broker.
        
        Args:
            run_id: Optional run context (for backward compat with run-level logging)
        """
        self.run_id = run_id
        self._agents: dict[UUID, AgentRegistration] = {}
        self._message_counts: dict[tuple[UUID, UUID], int] = {}  # (from, to) → count
    
    def register_agent(
        self,
        agent_id: UUID,
        agent_type: str,
        handler: Callable[[str], Awaitable[str]],
        max_incoming_messages: int | None = None,
    ) -> None:
        """
        Register an agent with the broker.
        
        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent ("worker", "stakeholder", etc.)
            handler: Async function that handles incoming messages and returns response
            max_incoming_messages: Optional limit on messages this agent can receive
        """
        self._agents[agent_id] = AgentRegistration(
            agent_id=agent_id,
            agent_type=agent_type,
            handler=handler,
            max_incoming_messages=max_incoming_messages,
        )
    
    def unregister_agent(self, agent_id: UUID) -> None:
        """Remove an agent from the registry."""
        self._agents.pop(agent_id, None)
    
    async def send(
        self,
        from_agent_id: UUID,
        to_agent_id: UUID,
        topic: str,
        content: str,
    ) -> str:
        """
        Send a message from one agent to another and get response.
        
        This is a synchronous request-response pattern:
        1. Persist outgoing message
        2. Route to recipient's handler
        3. Persist response
        4. Return response
        
        Args:
            from_agent_id: Sender agent ID
            to_agent_id: Recipient agent ID  
            topic: Conversation topic (e.g., "task_clarification")
            content: Message content
            
        Returns:
            Response from the recipient agent
            
        Raises:
            ValueError: If recipient not registered or limit exceeded
        """
        # Check recipient exists
        recipient = self._agents.get(to_agent_id)
        if recipient is None:
            raise ValueError(f"Agent {to_agent_id} not registered")
        
        # Check limits
        pair_key = (from_agent_id, to_agent_id)
        current_count = self._message_counts.get(pair_key, 0)
        
        if recipient.max_incoming_messages is not None:
            if current_count >= recipient.max_incoming_messages:
                return f"[Maximum messages ({recipient.max_incoming_messages}) to this agent reached.]"
        
        # Persist outgoing message
        communication_service.save_message(
            CreateMessageRequest(
                from_agent_id=from_agent_id,
                to_agent_id=to_agent_id,
                thread_topic=topic,
                content=content,
            )
        )
        
        # Route to handler
        response = await recipient.handler(content)
        
        # Persist response
        communication_service.save_message(
            CreateMessageRequest(
                from_agent_id=to_agent_id,
                to_agent_id=from_agent_id,
                thread_topic=topic,
                content=response,
            )
        )
        
        # Update count
        self._message_counts[pair_key] = current_count + 1
        
        return response
    
    def get_message_count(self, from_agent_id: UUID, to_agent_id: UUID) -> int:
        """Get number of messages sent from one agent to another."""
        return self._message_counts.get((from_agent_id, to_agent_id), 0)
    
    def get_all_threads(self, agent_a_id: UUID, agent_b_id: UUID):
        """Get all conversation threads between two agents."""
        return communication_service.get_all_threads_between_agents(agent_a_id, agent_b_id)
```

### Phase 2: Simplified Toolkit Interface

#### Update: `h_arcane/core/agents/base.py`

```python
class BaseToolkit(ABC):
    """Base class for benchmark-specific toolkits."""
    
    # Remove: questions_asked property (broker handles this)
    # Remove: ask_stakeholder method (broker handles this)
    
    @abstractmethod
    def get_tools(self) -> list:
        """Get list of tools available to the worker."""
        ...


class CommunicatingToolkit(BaseToolkit):
    """Toolkit with broker-based communication capabilities.
    
    Extend this instead of BaseToolkit when your toolkit needs
    inter-agent communication (e.g., ask_stakeholder).
    """
    
    def __init__(
        self,
        agent_id: UUID,
        broker: "MessageBroker",
        stakeholder_id: UUID | None = None,
        topic: str = "task_clarification",
    ):
        self.agent_id = agent_id
        self.broker = broker
        self.stakeholder_id = stakeholder_id
        self.topic = topic
    
    @property
    def questions_asked(self) -> int:
        """Number of questions asked to stakeholder."""
        if self.stakeholder_id is None:
            return 0
        return self.broker.get_message_count(self.agent_id, self.stakeholder_id)
    
    async def ask_stakeholder(self, question: str) -> str:
        """Ask the stakeholder a question via the broker."""
        if self.stakeholder_id is None:
            raise ValueError("No stakeholder registered for this toolkit")
        return await self.broker.send(
            from_agent_id=self.agent_id,
            to_agent_id=self.stakeholder_id,
            topic=self.topic,
            content=question,
        )
    
    def _make_ask_stakeholder_tool(self):
        """Create the ask_stakeholder tool."""
        from agents import function_tool
        
        @function_tool
        async def ask_stakeholder(question: str) -> str:
            """
            Ask the stakeholder a clarification question about the task.
            
            Args:
                question: Your question for the stakeholder
                
            Returns:
                The stakeholder's answer
            """
            return await self.ask_stakeholder(question)
        
        return ask_stakeholder
```

### Phase 3: Refactored Toolkit Example

#### Updated: `h_arcane/benchmarks/gdpeval/toolkit.py`

```python
"""GDPEval toolkit - simplified with broker-based communication."""

from uuid import UUID
from agents import Tool

from h_arcane.core.agents.base import CommunicatingToolkit
from h_arcane.core.communication.broker import MessageBroker
from h_arcane.core.infrastructure.sandbox import BaseSandboxManager


class GDPEvalToolkit(CommunicatingToolkit):
    """GDPEval benchmark toolkit with document processing tools."""
    
    def __init__(
        self,
        agent_id: UUID,
        broker: MessageBroker,
        stakeholder_id: UUID,
        sandbox_manager: BaseSandboxManager,
    ):
        super().__init__(
            agent_id=agent_id,
            broker=broker,
            stakeholder_id=stakeholder_id,
            topic="task_clarification",
        )
        self.sandbox_manager = sandbox_manager
    
    def get_tools(self) -> list[Tool]:
        """Return all GDPEval tools."""
        return [
            self._read_pdf(),
            self._read_csv(),
            # ... other tools ...
            self._make_ask_stakeholder_tool(),  # From base class!
        ]
    
    # Only benchmark-specific tool implementations below
    def _read_pdf(self) -> Tool:
        ...
```

### Phase 4: Orchestration Integration

#### Updated: `h_arcane/core/orchestration/worker_execute.py`

```python
async def worker_execute(ctx: inngest.Context) -> dict:
    # ... setup ...
    
    # Create broker for this run
    broker = MessageBroker(run_id=run_id)
    
    # Generate agent IDs
    worker_id = uuid4()
    stakeholder_id = uuid4()
    
    # Create stakeholder and register with broker
    stakeholder = benchmark.create_stakeholder(experiment)
    broker.register_agent(
        agent_id=stakeholder_id,
        agent_type="stakeholder",
        handler=stakeholder.answer,
        max_incoming_messages=config.max_questions,
    )
    
    # Create toolkit with broker
    toolkit = benchmark.create_toolkit(
        agent_id=worker_id,
        broker=broker,
        stakeholder_id=stakeholder_id,
        sandbox_manager=sandbox_manager,
    )
    
    # Execute worker
    result = await worker.execute(
        run_id=run_id,
        task_description=experiment.task_description,
        input_resources=resources,
        toolkit=toolkit,
    )
    
    return result
```

---

## File Structure Summary

```
h_arcane/core/
├── communication/
│   ├── __init__.py          # Exports broker + service + schemas
│   ├── schemas.py           # Pydantic schemas (existing)
│   ├── service.py           # CommunicationService (existing)
│   └── broker.py            # MessageBroker (NEW)
│
├── agents/
│   └── base.py              # Add CommunicatingToolkit base class
```

---

## Migration Strategy

### Step 1: Add New Classes (Non-Breaking)
1. Create `broker.py` with `MessageBroker`
2. Add `CommunicatingToolkit` to `base.py`
3. Update `communication/__init__.py` exports

### Step 2: Migrate Toolkits One-by-One
1. Start with GDPEvalToolkit as pilot
2. Update to extend `CommunicatingToolkit`
3. Remove duplicated ask_stakeholder logic
4. Test thoroughly

### Step 3: Update Orchestration
1. Update `worker_execute.py` to create and wire broker
2. Test end-to-end

### Step 4: Migrate Remaining Toolkits
1. MiniF2FToolkit
2. ResearchRubricsToolkit

### Step 5: Cleanup
1. Remove old `ask_stakeholder` abstract method from `BaseToolkit`
2. Remove unused Message model logging (or keep for backward compat)

---

## Multi-Agent Scaling Examples

### Example 1: Multiple Workers, One Stakeholder

```python
broker = MessageBroker(run_id=run_id)

# One stakeholder
stakeholder_id = uuid4()
broker.register_agent(stakeholder_id, "stakeholder", stakeholder.answer)

# Multiple workers
for i in range(3):
    worker_id = uuid4()
    toolkit = GDPEvalToolkit(
        agent_id=worker_id,
        broker=broker,
        stakeholder_id=stakeholder_id,
        sandbox_manager=sandbox,
    )
    # Each worker can ask the same stakeholder
```

### Example 2: Worker-to-Worker Communication

```python
broker = MessageBroker(run_id=run_id)

# Register worker A
worker_a_id = uuid4()
broker.register_agent(worker_a_id, "worker", worker_a.handle_message)

# Register worker B  
worker_b_id = uuid4()
broker.register_agent(worker_b_id, "worker", worker_b.handle_message)

# Worker A can message Worker B
response = await broker.send(
    from_agent_id=worker_a_id,
    to_agent_id=worker_b_id,
    topic="coordination",
    content="I've finished processing section 1, you can start section 2",
)
```

### Example 3: Hierarchical Agents (Manager → Workers)

```python
broker = MessageBroker(run_id=run_id)

# Manager agent
manager_id = uuid4()
broker.register_agent(manager_id, "manager", manager.handle_message)

# Sub-workers
for i in range(5):
    worker_id = uuid4()
    broker.register_agent(worker_id, "worker", workers[i].handle_message)
    
# Manager can coordinate all workers through the same broker
```

---

## Backward Compatibility: Run-Level Messages

To maintain backward compatibility with the existing `Message` model (tied to runs):

```python
class MessageBroker:
    def __init__(self, run_id: UUID | None = None, log_to_run: bool = True):
        self.run_id = run_id
        self.log_to_run = log_to_run
        self._run_message_num = 0
    
    async def send(self, ...):
        # ... existing logic ...
        
        # Also log to run-level messages if enabled
        if self.log_to_run and self.run_id:
            self._log_to_run_messages(from_agent_id, to_agent_id, content, response)
    
    def _log_to_run_messages(self, from_id, to_id, question, answer):
        """Log to legacy run-level Message table."""
        from h_arcane.core.db.models import Message, MessageRole
        from h_arcane.core.db.queries import queries
        
        # Question
        queries.messages.create(Message(
            run_id=self.run_id,
            sender=MessageRole.WORKER,
            content=question,
            sequence_num=self._run_message_num,
        ))
        self._run_message_num += 1
        
        # Answer
        queries.messages.create(Message(
            run_id=self.run_id,
            sender=MessageRole.STAKEHOLDER,
            content=answer,
            sequence_num=self._run_message_num,
        ))
        self._run_message_num += 1
```

---

## Benefits Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Code Duplication** | ask_stakeholder in every toolkit | Single implementation in CommunicatingToolkit |
| **Agent Interface** | Toolkit knows about messages, queries, counts | Toolkit only knows broker + agent IDs |
| **Multi-Agent** | Not supported | Native support via broker |
| **Testability** | Mock queries.messages | Mock broker.send() |
| **Extensibility** | Change every toolkit | Change broker once |

---

## Next Steps

1. [ ] Create `broker.py` with `MessageBroker` class
2. [ ] Add `CommunicatingToolkit` to `base.py`
3. [ ] Update `communication/__init__.py` exports
4. [ ] Refactor GDPEvalToolkit as pilot
5. [ ] Update worker_execute orchestration
6. [ ] Test end-to-end
7. [ ] Migrate remaining toolkits

