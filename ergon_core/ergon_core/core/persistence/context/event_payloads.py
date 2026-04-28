# ergon_core/ergon_core/core/persistence/context/event_payloads.py
"""Typed discriminated-union payloads for run_context_events rows.

Pattern mirrors GraphMutationValue in graph_dto.py — embed event_type as
a Literal field so Pydantic can discriminate on deserialisation.
"""

from typing import Annotated, Any, Literal

from ergon_core.core.generation import TokenLogprob
from pydantic import BaseModel, Field

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
    from_worker_key: str | None = Field(
        default=None,
        description=(
            "Worker binding key when this message was sent by another agent instead of "
            "the external user."
        ),
    )


class AssistantTextPayload(BaseModel):
    event_type: Literal["assistant_text"] = "assistant_text"
    text: str
    turn_id: str = Field(
        description=(
            "Generation turn identifier that groups model-output events from the same "
            "single synchronous agent run."
        )
    )
    turn_token_ids: list[int] | None = Field(
        default=None,
        description=(
            "Token ids for the generation turn. Present only on the first model-output "
            "event so sibling events can share the turn-level token stream."
        ),
    )
    turn_logprobs: list[TokenLogprob] | None = Field(
        default=None,
        description=(
            "Token logprobs for the generation turn. Present only on the first "
            "model-output event so sibling events can share the turn-level logprob stream."
        ),
    )


class ToolCallPayload(BaseModel):
    event_type: Literal["tool_call"] = "tool_call"
    tool_call_id: str
    tool_name: str
    args: dict[str, Any]  # slopcop: ignore[no-typing-any]
    turn_id: str = Field(
        description=(
            "Generation turn identifier that groups this tool call with other events "
            "emitted by the same single synchronous agent run."
        )
    )
    turn_token_ids: list[int] | None = Field(
        default=None,
        description=(
            "Token ids for the generation turn, omitted when another event in this turn "
            "carries the shared token stream."
        ),
    )
    turn_logprobs: list[TokenLogprob] | None = Field(
        default=None,
        description=(
            "Token logprobs for the generation turn, omitted when another event in this "
            "turn carries the shared logprob stream."
        ),
    )


class ToolResultPayload(BaseModel):
    event_type: Literal["tool_result"] = "tool_result"
    tool_call_id: str = Field(
        description="Identifier linking this result back to the ToolCallPayload it answers."
    )
    tool_name: str
    result: Any = Field(  # slopcop: ignore[no-typing-any]
        description=(
            "Open JSON-serializable value returned by the tool call; intentionally accepts "
            "any persisted result shape."
        )
    )
    is_error: bool = False


class ThinkingPayload(BaseModel):
    event_type: Literal["thinking"] = "thinking"
    text: str
    turn_id: str = Field(
        description=(
            "Generation turn identifier that groups thinking text with other events from "
            "the same single synchronous agent run."
        )
    )
    turn_token_ids: list[int] | None = Field(
        default=None,
        description=(
            "Token ids for the generation turn. Present only on the first model-output "
            "event so sibling events can share the turn-level token stream."
        ),
    )
    turn_logprobs: list[TokenLogprob] | None = Field(
        default=None,
        description=(
            "Token logprobs for the generation turn. Present only on the first "
            "model-output event so sibling events can share the turn-level logprob stream."
        ),
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
