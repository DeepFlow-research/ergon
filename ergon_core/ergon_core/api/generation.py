"""Public output types for model generation.

Workers yield GenerationTurn objects from their execute() generator.
The framework adapter (_build_turns in react_worker.py) populates all
typed list fields — workers never set messages_in, response_parts, or
tool_results directly.

turn_token_ids and turn_logprobs are turn-level flat lists from vLLM's
choice.logprobs.content. Both are stored on the FIRST model-output context
event of each turn (group by turn_id to find them). Currently None until
the vLLM provider is updated to extract token IDs from provider_details.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from ergon_core.api.json_types import JsonObject
from pydantic import BaseModel, Field


class TokenLogprob(BaseModel):
    """Per-token log probability from the serving backend."""

    model_config = {"frozen": True}

    token: str
    logprob: float
    top_logprobs: list[JsonObject] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Request parts (ModelRequest input — what went INTO the model)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Response parts (ModelResponse output — what the model produced)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# GenerationTurn
# ---------------------------------------------------------------------------


class GenerationTurn(BaseModel):
    """One model generation turn within a worker episode.

    Populated by the framework adapter (_build_turns in react_worker.py).
    Workers do not set any fields directly — they only yield the object.
    """

    model_config = {"frozen": True}

    messages_in: list[ModelRequestPart] = Field(default_factory=list)
    response_parts: list[ModelResponsePart] = Field(default_factory=list)
    tool_results: list[ToolReturnPart] = Field(default_factory=list)

    # turn_token_ids and turn_logprobs: turn-level flat lists from vLLM.
    # Stored on the FIRST model-output context event only; group by turn_id.
    # None until vLLM provider exposes token IDs (logprobs arrive first).
    turn_token_ids: list[int] | None = None
    turn_logprobs: list[TokenLogprob] | None = None

    policy_version: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
