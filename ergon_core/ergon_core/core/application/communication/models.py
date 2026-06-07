"""Pydantic DTOs for inter-agent communication service commands and results."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateMessageRequest(BaseModel):
    sample_id: UUID
    from_agent_id: str = Field(
        description="ID of the sending agent, e.g. '{sample_id}:worker'",
    )
    to_agent_id: str = Field(
        description="ID of the receiving agent, e.g. '{sample_id}:stakeholder'",
    )
    thread_topic: str
    thread_summary: str | None = Field(
        default=None,
        description="Optional human-readable summary set when the thread is first created.",
    )
    content: str
    task_attempt_id: UUID | None = None


class MessageResponse(BaseModel):
    message_id: UUID
    thread_id: UUID
    sample_id: UUID
    thread_topic: str
    from_agent_id: str
    to_agent_id: str
    content: str
    sequence_num: int
    task_attempt_id: UUID | None = None
    created_at: datetime


class ThreadSummary(BaseModel):
    thread_id: UUID
    sample_id: UUID
    topic: str
    summary: str | None = None
    agent_a_id: str
    agent_b_id: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ThreadWithMessages(BaseModel):
    thread_id: UUID
    sample_id: UUID
    topic: str
    summary: str | None = None
    agent_a_id: str
    agent_b_id: str
    messages: list[MessageResponse]
    created_at: datetime
    updated_at: datetime
