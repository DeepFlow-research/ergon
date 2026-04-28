"""Core model context-stream types.

These types are used by worker APIs, transcript adapters, persistence, replay,
and RL extraction. Keep them in core so persistence can import them without
loading ``ergon_core.api``.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from ergon_core.core.json_types import JsonObject
from pydantic import BaseModel, Field


class TokenLogprob(BaseModel):
    """Per-token log probability from the serving backend."""

    model_config = {"frozen": True}

    token: str
    logprob: float
    top_logprobs: list[JsonObject] = Field(default_factory=list)


class SystemPromptPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["system_prompt"] = "system_prompt"
    content: str


class UserMessagePart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["user_message"] = "user_message"
    content: str


class AssistantTextPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["assistant_text"] = "assistant_text"
    content: str


class ToolCallPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["tool_call"] = "tool_call"
    tool_name: str
    tool_call_id: str
    args: dict[str, Any]  # slopcop: ignore[no-typing-any]


class ToolResultPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False


class ThinkingPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["thinking"] = "thinking"
    content: str


ContextPart = Annotated[
    SystemPromptPart
    | UserMessagePart
    | AssistantTextPart
    | ToolCallPart
    | ToolResultPart
    | ThinkingPart,
    Field(discriminator="part_kind"),
]


class ContextPartChunk(BaseModel):
    """One worker-emitted context/action stream item.

    Core adds run/execution/sequence/timing metadata before persistence.
    """

    model_config = {"frozen": True}

    part: ContextPart
    token_ids: list[int] | None = None
    logprobs: list[TokenLogprob] | None = None


class ContextPartChunkLog(ContextPartChunk):
    """Core-enriched context stream item suitable for API/dashboard projection."""

    sequence: int
    worker_binding_key: str
    turn_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    policy_version: str | None = None


WorkerYield = ContextPartChunk
