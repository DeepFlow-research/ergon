"""Pydantic DTOs for the inter-agent communication service."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class CreateMessageRequest(BaseModel):
    run_id: UUID
    from_agent_id: str = Field(
        description="ID of the sending agent, e.g. '{run_id}:worker'",
    )
    to_agent_id: str = Field(
        description="ID of the receiving agent, e.g. '{run_id}:stakeholder'",
    )
    thread_topic: str
    content: str


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class MessageResponse(BaseModel):
    message_id: UUID
    thread_id: UUID
    run_id: UUID
    thread_topic: str
    from_agent_id: str
    to_agent_id: str
    content: str
    sequence_num: int
    created_at: datetime


class ThreadSummary(BaseModel):
    thread_id: UUID
    run_id: UUID
    topic: str
    agent_a_id: str
    agent_b_id: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ThreadWithMessages(BaseModel):
    thread_id: UUID
    run_id: UUID
    topic: str
    agent_a_id: str
    agent_b_id: str
    messages: list[MessageResponse]
    created_at: datetime
    updated_at: datetime
