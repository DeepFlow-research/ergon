# 13. Communication Service Architecture

## Overview

This document outlines the architecture for a **Communication Service** that enables structured messaging between agents. The core concept is a **Thread** — a topical conversation between exactly two agents consisting of a sequence of messages.

---

## 1. Core Concepts

### Thread
A **Thread** represents a conversation between two agents on a specific topic:
- Contains an ordered list of messages
- Has exactly two participants (agent IDs)
- Has a topic describing the conversation purpose
- Is identified by a unique `thread_id`

### Message
A **Message** is a single communication unit within a thread:
- Has sender and recipient agent IDs
- Belongs to exactly one thread
- Contains textual content
- Has a timestamp for ordering

---

## 2. Database Schema (SQLModel)

### Location: `h_arcane/core/db/models.py`

Add the following models to the existing models file:

```python
class Thread(SQLModel, table=True):
    """A conversation thread between two agents."""

    __tablename__ = "threads"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # Participants (stored in consistent order: min(agent_a, agent_b), max(agent_a, agent_b))
    agent_a_id: UUID = Field(index=True)  # Always the "smaller" UUID
    agent_b_id: UUID = Field(index=True)  # Always the "larger" UUID
    
    # Topic
    topic: str = Field(index=True)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)  # Updated on new message
    
    __table_args__ = (
        Index("ix_threads_participants", "agent_a_id", "agent_b_id"),
        Index("ix_threads_topic", "topic"),
    )


class ThreadMessage(SQLModel, table=True):
    """A message within a conversation thread."""

    __tablename__ = "thread_messages"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    thread_id: UUID = Field(foreign_key="threads.id", index=True)
    
    # Sender/Recipient
    from_agent_id: UUID = Field(index=True)
    to_agent_id: UUID = Field(index=True)
    
    # Content
    content: str
    
    # Ordering and timing
    sequence_num: int  # 0, 1, 2, ... within thread
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_thread_messages_thread_seq", "thread_id", "sequence_num"),
        Index("ix_thread_messages_from", "from_agent_id"),
        Index("ix_thread_messages_to", "to_agent_id"),
    )
```

### Design Decisions

1. **Separate `Thread` and `ThreadMessage` tables**: Enables efficient queries for "all threads between agents" without scanning all messages.

2. **Normalized participant storage**: `agent_a_id` always stores the lexicographically smaller UUID, `agent_b_id` the larger. This ensures we can query for threads between two agents without checking both orderings.

3. **Named `ThreadMessage`**: Avoids collision with existing `Message` model (which is tied to `Run`).

---

## 3. Pydantic Schemas (API/Service Layer)

### Location: `h_arcane/core/communication/schemas.py` (NEW FILE)

Create a new `communication` module for clean separation:

```python
"""Pydantic schemas for the Communication Service."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# ============================================================================
# Request Schemas (Input)
# ============================================================================

class CreateMessageRequest(BaseModel):
    """Request to create a new message in a thread."""
    
    from_agent_id: UUID
    to_agent_id: UUID
    thread_topic: str
    content: str


class GetMessageRequest(BaseModel):
    """Request to get a message by ID."""
    
    message_id: UUID


class GetThreadMessagesRequest(BaseModel):
    """Request to get all messages in a thread between two agents."""
    
    agent_a_id: UUID
    agent_b_id: UUID
    thread_id: UUID


class GetAgentThreadsRequest(BaseModel):
    """Request to get all threads between two agents."""
    
    agent_a_id: UUID
    agent_b_id: UUID


# ============================================================================
# Response Schemas (Output)
# ============================================================================

class MessageResponse(BaseModel):
    """Response containing a single message."""
    
    message_id: UUID
    thread_id: UUID
    thread_topic: str
    from_agent_id: UUID
    to_agent_id: UUID
    content: str
    sequence_num: int
    created_at: datetime


class ThreadSummary(BaseModel):
    """Summary of a thread (without messages)."""
    
    thread_id: UUID
    topic: str
    agent_a_id: UUID
    agent_b_id: UUID
    message_count: int
    created_at: datetime
    updated_at: datetime


class ThreadWithMessages(BaseModel):
    """Full thread with all messages."""
    
    thread_id: UUID
    topic: str
    agent_a_id: UUID
    agent_b_id: UUID
    messages: list[MessageResponse]
    created_at: datetime
    updated_at: datetime


class ThreadListResponse(BaseModel):
    """Response containing a list of threads."""
    
    threads: list[ThreadSummary]
    total_count: int
```

---

## 4. Query Layer

### Option A: Extend Existing `queries.py` (Recommended for now)

Add to `h_arcane/core/db/queries.py`:

```python
class ThreadsQueries(BaseQueries[Thread]):
    """Query methods for Thread model."""

    def __init__(self):
        super().__init__(Thread)

    @staticmethod
    def _normalize_agent_ids(agent_a_id: UUID, agent_b_id: UUID) -> tuple[UUID, UUID]:
        """Normalize agent IDs to consistent order (smaller, larger)."""
        if str(agent_a_id) < str(agent_b_id):
            return agent_a_id, agent_b_id
        return agent_b_id, agent_a_id

    def get_or_create_thread(
        self, 
        agent_a_id: UUID, 
        agent_b_id: UUID, 
        topic: str
    ) -> Thread:
        """Get existing thread or create new one."""
        normalized_a, normalized_b = self._normalize_agent_ids(agent_a_id, agent_b_id)
        
        with next(get_session()) as session:
            statement = select(Thread).where(
                Thread.agent_a_id == normalized_a,
                Thread.agent_b_id == normalized_b,
                Thread.topic == topic,
            )
            existing = session.exec(statement).first()
            
            if existing:
                return existing
            
            # Create new thread
            new_thread = Thread(
                agent_a_id=normalized_a,
                agent_b_id=normalized_b,
                topic=topic,
            )
            session.add(new_thread)
            session.commit()
            session.refresh(new_thread)
            return new_thread

    def get_threads_between_agents(
        self, 
        agent_a_id: UUID, 
        agent_b_id: UUID
    ) -> list[Thread]:
        """Get all threads between two agents."""
        normalized_a, normalized_b = self._normalize_agent_ids(agent_a_id, agent_b_id)
        
        with next(get_session()) as session:
            statement = select(Thread).where(
                Thread.agent_a_id == normalized_a,
                Thread.agent_b_id == normalized_b,
            ).order_by(Thread.updated_at.desc())
            return list(session.exec(statement).all())


class ThreadMessagesQueries(BaseQueries[ThreadMessage]):
    """Query methods for ThreadMessage model."""

    def __init__(self):
        super().__init__(ThreadMessage)

    def get_by_thread(
        self, 
        thread_id: UUID, 
        order_by: str = "sequence_num"
    ) -> list[ThreadMessage]:
        """Get all messages in a thread, ordered by sequence."""
        with next(get_session()) as session:
            statement = select(ThreadMessage).where(
                ThreadMessage.thread_id == thread_id
            )
            if order_by == "sequence_num":
                statement = statement.order_by(ThreadMessage.sequence_num)
            return list(session.exec(statement).all())

    def get_next_sequence_num(self, thread_id: UUID) -> int:
        """Get the next sequence number for a thread."""
        with next(get_session()) as session:
            statement = select(ThreadMessage).where(
                ThreadMessage.thread_id == thread_id
            ).order_by(ThreadMessage.sequence_num.desc())
            last_message = session.exec(statement).first()
            return (last_message.sequence_num + 1) if last_message else 0

    def create_message(
        self,
        thread_id: UUID,
        from_agent_id: UUID,
        to_agent_id: UUID,
        content: str,
    ) -> ThreadMessage:
        """Create a new message in a thread."""
        sequence_num = self.get_next_sequence_num(thread_id)
        
        new_message = ThreadMessage(
            thread_id=thread_id,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            content=content,
            sequence_num=sequence_num,
        )
        return self.create(new_message)
```

Then add to the `Queries` class:

```python
class Queries:
    # ... existing ...
    threads: ThreadsQueries
    thread_messages: ThreadMessagesQueries

    def __init__(self):
        # ... existing ...
        self.threads = ThreadsQueries()
        self.thread_messages = ThreadMessagesQueries()
```

### Option B: Separate Query Module (For Larger Scale)

If you want cleaner separation as the library grows:

```
h_arcane/core/db/
├── __init__.py
├── connection.py
├── models.py
└── queries/
    ├── __init__.py          # Re-exports Queries class
    ├── base.py              # BaseQueries[T]
    ├── runs.py              # RunsQueries
    ├── experiments.py       # ExperimentsQueries
    ├── resources.py         # ResourcesQueries
    ├── messages.py          # MessagesQueries (existing run messages)
    ├── actions.py           # ActionsQueries
    ├── evaluations.py       # EvaluationsQueries, CriterionResultsQueries, etc.
    ├── threads.py           # ThreadsQueries (NEW)
    └── thread_messages.py   # ThreadMessagesQueries (NEW)
```

**Recommendation**: Start with Option A, migrate to Option B when `queries.py` exceeds ~500 lines.

---

## 5. Service Layer

### Location: `h_arcane/core/communication/service.py` (NEW FILE)

The service layer orchestrates queries and returns Pydantic schemas:

```python
"""Communication Service - manages inter-agent messaging."""

from uuid import UUID
from h_arcane.core.db.queries import queries
from h_arcane.core.communication.schemas import (
    CreateMessageRequest,
    MessageResponse,
    ThreadSummary,
    ThreadWithMessages,
    ThreadListResponse,
)


class CommunicationService:
    """Service for managing agent-to-agent communication."""

    def save_message(self, request: CreateMessageRequest) -> MessageResponse:
        """Save a new message, creating thread if needed."""
        # Get or create thread
        thread = queries.threads.get_or_create_thread(
            agent_a_id=request.from_agent_id,
            agent_b_id=request.to_agent_id,
            topic=request.thread_topic,
        )
        
        # Create message
        message = queries.thread_messages.create_message(
            thread_id=thread.id,
            from_agent_id=request.from_agent_id,
            to_agent_id=request.to_agent_id,
            content=request.content,
        )
        
        # Update thread timestamp
        thread.updated_at = message.created_at
        queries.threads.update(thread)
        
        return MessageResponse(
            message_id=message.id,
            thread_id=thread.id,
            thread_topic=thread.topic,
            from_agent_id=message.from_agent_id,
            to_agent_id=message.to_agent_id,
            content=message.content,
            sequence_num=message.sequence_num,
            created_at=message.created_at,
        )

    def get_message(self, message_id: UUID) -> MessageResponse | None:
        """Get a message by ID."""
        message = queries.thread_messages.get(message_id)
        if message is None:
            return None
        
        thread = queries.threads.get(message.thread_id)
        if thread is None:
            return None
        
        return MessageResponse(
            message_id=message.id,
            thread_id=message.thread_id,
            thread_topic=thread.topic,
            from_agent_id=message.from_agent_id,
            to_agent_id=message.to_agent_id,
            content=message.content,
            sequence_num=message.sequence_num,
            created_at=message.created_at,
        )

    def get_thread_messages(
        self, 
        thread_id: UUID
    ) -> ThreadWithMessages | None:
        """Get all messages in a specific thread."""
        thread = queries.threads.get(thread_id)
        if thread is None:
            return None
        
        messages = queries.thread_messages.get_by_thread(thread_id)
        
        return ThreadWithMessages(
            thread_id=thread.id,
            topic=thread.topic,
            agent_a_id=thread.agent_a_id,
            agent_b_id=thread.agent_b_id,
            messages=[
                MessageResponse(
                    message_id=m.id,
                    thread_id=m.thread_id,
                    thread_topic=thread.topic,
                    from_agent_id=m.from_agent_id,
                    to_agent_id=m.to_agent_id,
                    content=m.content,
                    sequence_num=m.sequence_num,
                    created_at=m.created_at,
                )
                for m in messages
            ],
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )

    def get_all_threads_between_agents(
        self, 
        agent_a_id: UUID, 
        agent_b_id: UUID
    ) -> ThreadListResponse:
        """Get all threads between two agents."""
        threads = queries.threads.get_threads_between_agents(agent_a_id, agent_b_id)
        
        summaries = []
        for thread in threads:
            message_count = len(queries.thread_messages.get_by_thread(thread.id))
            summaries.append(
                ThreadSummary(
                    thread_id=thread.id,
                    topic=thread.topic,
                    agent_a_id=thread.agent_a_id,
                    agent_b_id=thread.agent_b_id,
                    message_count=message_count,
                    created_at=thread.created_at,
                    updated_at=thread.updated_at,
                )
            )
        
        return ThreadListResponse(
            threads=summaries,
            total_count=len(summaries),
        )


# Global service instance
communication_service = CommunicationService()
```

---

## 6. File Structure Summary

```
h_arcane/
├── core/
│   ├── db/
│   │   ├── connection.py        # Existing
│   │   ├── models.py            # ADD: Thread, ThreadMessage
│   │   └── queries.py           # ADD: ThreadsQueries, ThreadMessagesQueries
│   │
│   └── communication/           # NEW MODULE
│       ├── __init__.py          # Exports service, schemas
│       ├── schemas.py           # Pydantic request/response schemas
│       └── service.py           # CommunicationService class
```

### `h_arcane/core/communication/__init__.py`

```python
"""Communication service for agent-to-agent messaging."""

from h_arcane.core.communication.service import (
    CommunicationService,
    communication_service,
)
from h_arcane.core.communication.schemas import (
    CreateMessageRequest,
    GetMessageRequest,
    GetThreadMessagesRequest,
    GetAgentThreadsRequest,
    MessageResponse,
    ThreadSummary,
    ThreadWithMessages,
    ThreadListResponse,
)

__all__ = [
    "CommunicationService",
    "communication_service",
    "CreateMessageRequest",
    "GetMessageRequest",
    "GetThreadMessagesRequest",
    "GetAgentThreadsRequest",
    "MessageResponse",
    "ThreadSummary",
    "ThreadWithMessages",
    "ThreadListResponse",
]
```

---

## 7. Usage Example

```python
from uuid import uuid4
from h_arcane.core.communication import (
    communication_service,
    CreateMessageRequest,
)

# Two agents
agent_1 = uuid4()
agent_2 = uuid4()

# Send a message
response = communication_service.save_message(
    CreateMessageRequest(
        from_agent_id=agent_1,
        to_agent_id=agent_2,
        thread_topic="Resource Allocation Discussion",
        content="I need access to the database credentials.",
    )
)

print(f"Message saved: {response.message_id}")
print(f"Thread: {response.thread_id} ({response.thread_topic})")

# Reply
response2 = communication_service.save_message(
    CreateMessageRequest(
        from_agent_id=agent_2,
        to_agent_id=agent_1,
        thread_topic="Resource Allocation Discussion",  # Same topic = same thread
        content="Credentials sent via secure channel.",
    )
)

# Get all threads between agents
threads = communication_service.get_all_threads_between_agents(agent_1, agent_2)
print(f"Found {threads.total_count} threads")

# Get messages in a thread
thread = communication_service.get_thread_messages(response.thread_id)
for msg in thread.messages:
    print(f"[{msg.sequence_num}] {msg.from_agent_id}: {msg.content}")
```

---

## 8. Future Considerations

1. **Pagination**: Add `offset`/`limit` to list queries for large threads.
2. **Message metadata**: Add optional `metadata: dict` field for structured data.
3. **Read receipts**: Track when messages are read.
4. **Thread participants expansion**: Support multi-agent threads (3+ participants).
5. **Soft deletes**: Add `deleted_at` for message retention.
6. **Full-text search**: Index `content` for searchable messages.

---

## 9. Migration Checklist

- [ ] Add `Thread` and `ThreadMessage` models to `models.py`
- [ ] Run Alembic migration to create tables
- [ ] Add `ThreadsQueries` and `ThreadMessagesQueries` to `queries.py`
- [ ] Create `h_arcane/core/communication/` module
- [ ] Create `schemas.py` with Pydantic models
- [ ] Create `service.py` with `CommunicationService`
- [ ] Create `__init__.py` with exports
- [ ] Add unit tests
- [ ] Update `__init__.py` at `h_arcane/core/` level if needed

