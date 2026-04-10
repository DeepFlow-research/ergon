"""Public output types for model generation.

Workers populate these from whatever model framework they use.
``raw_response`` carries the framework's native serialisation (e.g.
``dataclasses.asdict()`` on PydanticAI's ``ModelResponse``).  No
normalisation, no format conversion.

Logprobs are extracted from PydanticAI's ``provider_details`` when
the backend is vLLM.  PydanticAI preserves token strings and logprob
floats but drops ``token_id`` (int).  For RL training we re-tokenize
the strings to recover IDs — TODO: verify this round-trip is lossless
for all tokenizers.
"""

from typing import Any

from pydantic import BaseModel, Field


class TokenLogprob(BaseModel):
    """Per-token log probability from the serving backend."""

    model_config = {"frozen": True}

    token: str
    logprob: float
    top_logprobs: list[dict[str, Any]] = Field(default_factory=list)  # slopcop: ignore[no-typing-any]


class GenerationTurn(BaseModel):
    """One model generation turn within a worker episode.

    ``raw_request`` is the message history that was sent to the model
    for this turn (for replay / debugging).  ``raw_response`` is the
    framework-native serialisation of the model response.  Neither is
    normalised — they carry whatever the framework produces.

    ``tool_results`` carries the tool execution outputs that were fed
    back to the model before the next turn.

    ``logprobs`` is populated when the serving backend provides them
    (vLLM with ``openai_logprobs=True``).  Contains token strings +
    logprob floats.  For RL training, token strings are re-tokenized
    to recover integer IDs.
    """

    model_config = {"frozen": True}

    raw_request: dict[str, Any] | None = None  # slopcop: ignore[no-typing-any]
    raw_response: dict[str, Any]  # slopcop: ignore[no-typing-any]
    tool_results: list[dict[str, Any]] = Field(default_factory=list)  # slopcop: ignore[no-typing-any]

    logprobs: list[TokenLogprob] | None = None
    policy_version: str | None = None
