"""Shared context-stream contracts.

These types are used by worker APIs, transcript adapters, persistence, replay,
and RL extraction. Keep them in core so persistence can import them without
loading ``ergon_core.api``.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel, Field


class TokenLogprob(BaseModel):
    """Per-token log probability from the serving backend."""

    model_config = {"frozen": True}

    token: str = Field(description="Generated token text.")
    logprob: float = Field(description="Natural-log probability assigned to the token.")
    top_logprobs: list[JsonObject] = Field(
        default_factory=list,
        description="Optional model-provider alternatives and probabilities for this position.",
    )


class ProviderTokenUsage(BaseModel):
    """Provider-reported token and cost usage for one generation boundary."""

    model_config = {"frozen": True}

    prompt_tokens: int | None = Field(
        default=None,
        description="Input tokens charged or reported by the model provider.",
    )
    completion_tokens: int | None = Field(
        default=None,
        description="Output tokens charged or reported by the model provider.",
    )
    reasoning_tokens: int | None = Field(
        default=None,
        description="Reasoning tokens when the provider reports them separately.",
    )
    tool_call_tokens: int | None = Field(
        default=None,
        description="Tool-call argument tokens when reported separately.",
    )
    tool_result_tokens: int | None = Field(
        default=None,
        description="Tool-result tokens when reported separately.",
    )
    cached_tokens: int | None = Field(
        default=None,
        description="Cached/read tokens when reported separately.",
    )
    total_tokens: int | None = Field(
        default=None,
        description="Provider total when semantic buckets are unavailable.",
    )
    total_cost_usd: float | None = Field(
        default=None,
        description="Observed provider cost in USD for this generation boundary.",
    )


class SystemPromptPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["system_prompt"] = Field(
        default="system_prompt",
        description="Discriminator identifying this context part as a system prompt.",
    )
    content: str = Field(description="System instructions supplied to the worker.")


class UserMessagePart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["user_message"] = Field(
        default="user_message",
        description="Discriminator identifying this context part as a user message.",
    )
    content: str = Field(description="User or upstream task message content.")


class AssistantTextPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["assistant_text"] = Field(
        default="assistant_text",
        description="Discriminator identifying this context part as assistant text.",
    )
    content: str = Field(description="Assistant response text emitted by the worker.")


class ToolCallPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["tool_call"] = Field(
        default="tool_call",
        description="Discriminator identifying this context part as a tool call.",
    )
    tool_name: str = Field(description="Name of the tool requested by the worker.")
    tool_call_id: str = Field(description="Provider-stable identifier for this tool call.")
    args: dict[str, Any] = Field(  # slopcop: ignore[no-typing-any]
        description="JSON-like tool input arguments.",
    )


class ToolResultPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["tool_result"] = Field(
        default="tool_result",
        description="Discriminator identifying this context part as a tool result.",
    )
    tool_call_id: str = Field(description="Identifier of the tool call this result answers.")
    tool_name: str = Field(description="Name of the tool that produced this result.")
    content: str = Field(description="Serialized tool result content.")
    is_error: bool = Field(
        default=False,
        description="Whether the tool result represents an error response.",
    )


class ThinkingPart(BaseModel):
    model_config = {"frozen": True}
    part_kind: Literal["thinking"] = Field(
        default="thinking",
        description="Discriminator identifying this context part as private thinking.",
    )
    content: str = Field(description="Reasoning or thinking text emitted by the model.")


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

    part: ContextPart = Field(description="Typed context stream payload.")
    token_ids: list[int] | None = Field(
        default=None,
        description="Token IDs associated with this context part when provided by the backend.",
    )
    logprobs: list[TokenLogprob] | None = Field(
        default=None,
        description="Per-token log probabilities associated with this context part.",
    )
    provider_usage: ProviderTokenUsage | None = Field(
        default=None,
        description="Provider-reported token and cost usage for this generation boundary.",
    )


class ContextPartChunkLog(ContextPartChunk):
    """Core-enriched context stream item suitable for API/dashboard projection."""

    sequence: int = Field(description="Monotonic sequence number within the execution stream.")
    worker_binding_key: str = Field(description="Worker binding that emitted this context part.")
    turn_id: str | None = Field(
        default=None,
        description="Stable generation turn identifier shared by related streamed parts.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Timestamp when generation for this part started.",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when generation for this part completed.",
    )
    policy_version: str | None = Field(
        default=None,
        description="Optional worker or policy version that produced the part.",
    )


ContextEventType = Literal[
    "system_prompt",
    "user_message",
    "assistant_text",
    "tool_call",
    "tool_result",
    "thinking",
]
