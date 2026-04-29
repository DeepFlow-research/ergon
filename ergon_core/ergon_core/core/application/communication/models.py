"""Pydantic DTOs for inter-agent communication services and read models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class CamelModel(BaseModel):
    """Base model that exposes camelCase JSON to the frontend."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class RunCommunicationMessageDto(CamelModel):
    id: str
    thread_id: str
    thread_topic: str
    run_id: str
    task_id: str | None = None
    task_execution_id: str | None = None
    from_agent_id: str
    to_agent_id: str
    content: str
    sequence_num: int
    created_at: datetime


class RunCommunicationThreadDto(CamelModel):
    id: str
    run_id: str
    task_id: str | None = None
    topic: str
    summary: str | None = None
    agent_a_id: str
    agent_b_id: str
    created_at: datetime
    updated_at: datetime
    messages: list[RunCommunicationMessageDto] = Field(default_factory=list)


class CreateMessageRequest(BaseModel):
    run_id: UUID
    from_agent_id: str = Field(
        description="ID of the sending agent, e.g. '{run_id}:worker'",
    )
    to_agent_id: str = Field(
        description="ID of the receiving agent, e.g. '{run_id}:stakeholder'",
    )
    thread_topic: str
    thread_summary: str | None = Field(
        default=None,
        description="Optional human-readable summary set when the thread is first created.",
    )
    content: str
    task_execution_id: UUID | None = None


class MessageResponse(BaseModel):
    message_id: UUID
    thread_id: UUID
    run_id: UUID
    thread_topic: str
    from_agent_id: str
    to_agent_id: str
    content: str
    sequence_num: int
    task_execution_id: UUID | None = None
    created_at: datetime


class ThreadSummary(BaseModel):
    thread_id: UUID
    run_id: UUID
    topic: str
    summary: str | None = None
    agent_a_id: str
    agent_b_id: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ThreadWithMessages(BaseModel):
    thread_id: UUID
    run_id: UUID
    topic: str
    summary: str | None = None
    agent_a_id: str
    agent_b_id: str
    messages: list[MessageResponse]
    created_at: datetime
    updated_at: datetime
