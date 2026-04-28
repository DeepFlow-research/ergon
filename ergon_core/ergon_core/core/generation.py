"""Core model-generation turn types.

These types are used by both public worker APIs and internal persistence. Keep
them in core so persistence can import them without loading ``ergon_core.api``.
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
    part_kind: Literal["system-prompt"] = "system-prompt"
    content: str


class UserPromptPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["user-prompt"] = "user-prompt"
    content: str


class ToolReturnPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["tool-return"] = "tool-return"
    tool_call_id: str
    tool_name: str
    content: str


ModelRequestPart = Annotated[
    SystemPromptPart | UserPromptPart | ToolReturnPart,
    Field(discriminator="part_kind"),
]


class TextPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["text"] = "text"
    content: str


class ToolCallPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["tool-call"] = "tool-call"
    tool_name: str
    tool_call_id: str
    args: dict[str, Any]  # slopcop: ignore[no-typing-any]


class ThinkingPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["thinking"] = "thinking"
    content: str


ModelResponsePart = Annotated[
    TextPart | ToolCallPart | ThinkingPart,
    Field(discriminator="part_kind"),
]


class GenerationTurn(BaseModel):
    """One model generation turn within a worker episode."""

    model_config = {"frozen": True}

    messages_in: list[ModelRequestPart] = Field(default_factory=list)
    response_parts: list[ModelResponsePart] = Field(default_factory=list)
    tool_results: list[ToolReturnPart] = Field(default_factory=list)
    turn_token_ids: list[int] | None = None
    turn_logprobs: list[TokenLogprob] | None = None
    policy_version: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
