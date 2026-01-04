"""Pydantic schemas for the Communication Service."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# Request Schemas (Input)
# =============================================================================


class CreateMessageRequest(BaseModel):
    """Request to create a new message in a thread."""

    run_id: UUID
    experiment_id: UUID
    from_agent_id: str = Field(description="ID of agent sending the message", examples=["{run_id}:worker"])
    to_agent_id: str = Field(description="ID of agent receiving the message", examples=["{run_id}:stakeholder"])
    thread_topic: str
    content: str


class GetMessageRequest(BaseModel):
    """Request to get a message by ID."""

    message_id: UUID


class GetThreadMessagesRequest(BaseModel):
    """Request to get all messages in a thread between two agents."""

    agent_a_id: str
    agent_b_id: str
    thread_id: UUID


class GetAgentThreadsRequest(BaseModel):
    """Request to get all threads between two agents."""

    agent_a_id: str
    agent_b_id: str


# =============================================================================
# Response Schemas (Output)
# =============================================================================


class MessageResponse(BaseModel):
    """Response containing a single message."""

    message_id: UUID
    thread_id: UUID
    run_id: UUID
    experiment_id: UUID
    thread_topic: str
    from_agent_id: str
    to_agent_id: str
    content: str
    sequence_num: int
    created_at: datetime


class ThreadSummary(BaseModel):
    """Summary of a thread (without messages)."""

    thread_id: UUID
    run_id: UUID
    experiment_id: UUID
    topic: str
    agent_a_id: str
    agent_b_id: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ThreadWithMessages(BaseModel):
    """Full thread with all messages."""

    thread_id: UUID
    run_id: UUID
    experiment_id: UUID
    topic: str
    agent_a_id: str
    agent_b_id: str
    messages: list[MessageResponse]
    created_at: datetime
    updated_at: datetime


class ThreadListResponse(BaseModel):
    """Response containing a list of threads."""

    threads: list[ThreadSummary]
    total_count: int
