"""Shared generation provider value types."""

from pydantic import BaseModel, Field

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


class TokenLogprob(BaseModel):
    """Per-token log probability from the serving backend."""

    model_config = {"frozen": True}

    token: str
    logprob: float
    top_logprobs: list[JsonObject] = Field(default_factory=list)
