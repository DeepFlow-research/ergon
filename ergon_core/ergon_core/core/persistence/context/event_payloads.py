# ergon_core/ergon_core/core/persistence/context/event_payloads.py
"""Typed discriminated-union payloads for run_context_events rows.

Pattern mirrors GraphMutationValue in graph_dto.py — embed event_type as
a Literal field so Pydantic can discriminate on deserialisation.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from ergon_core.api.generation import TokenLogprob

# Exported type alias — use everywhere event_type is stored as a string field.
ContextEventType = Literal[
    "system_prompt",
    "user_message",
    "assistant_text",
    "tool_call",
    "tool_result",
    "thinking",
]


class SystemPromptPayload(BaseModel):
    event_type: Literal["system_prompt"] = "system_prompt"
    text: str


class UserMessagePayload(BaseModel):
    event_type: Literal["user_message"] = "user_message"
    text: str
    from_worker_key: str | None = None  # set for agent-to-agent messages


class AssistantTextPayload(BaseModel):
    event_type: Literal["assistant_text"] = "assistant_text"
    text: str
    turn_id: str  # links events from the same generation call
    turn_token_ids: list[int] | None = None  # set on FIRST model-output event of the turn only
    turn_logprobs: list[TokenLogprob] | None = (
        None  # set on FIRST model-output event of the turn only
    )


class ToolCallPayload(BaseModel):
    event_type: Literal["tool_call"] = "tool_call"
    tool_call_id: str
    tool_name: str
    args: dict[str, Any]  # slopcop: ignore[no-typing-any]
    turn_id: str  # links events from the same generation call
    turn_token_ids: list[int] | None = None  # None if another event in this turn holds them
    turn_logprobs: list[TokenLogprob] | None = None  # None if another event in this turn holds them


class ToolResultPayload(BaseModel):
    event_type: Literal["tool_result"] = "tool_result"
    tool_call_id: str  # links back to the ToolCallPayload with the same id
    tool_name: str
    result: Any  # slopcop: ignore[no-typing-any]  # intentionally open — any JSON-serialisable value
    is_error: bool = False


class ThinkingPayload(BaseModel):
    event_type: Literal["thinking"] = "thinking"
    text: str
    turn_id: str  # links events from the same generation call
    turn_token_ids: list[int] | None = None  # set on FIRST model-output event of the turn only
    turn_logprobs: list[TokenLogprob] | None = (
        None  # set on FIRST model-output event of the turn only
    )


ContextEventPayload = Annotated[
    SystemPromptPayload
    | UserMessagePayload
    | AssistantTextPayload
    | ToolCallPayload
    | ToolResultPayload
    | ThinkingPayload,
    Field(discriminator="event_type"),
]
