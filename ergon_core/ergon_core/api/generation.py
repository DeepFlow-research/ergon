"""Public output types for model generation.

Workers populate these from whatever model framework they use.
``raw_response`` carries the framework's native serialisation (e.g.
``dataclasses.asdict()`` on PydanticAI's ``ModelResponse``).  No
normalisation, no format conversion.

``prompt_text`` is the formatted prompt string the model saw for this
turn.  Set by the worker on the first turn — used by the RL extraction
pipeline for TRL's ``prompt_ids``.  Workers own the formatting; core
reads the string without interpreting it.

Logprobs are extracted from PydanticAI's ``provider_details`` when
the backend is vLLM.  PydanticAI preserves token strings and logprob
floats but drops ``token_id`` (int).  For RL training we re-tokenize
the strings to recover IDs — TODO: verify this round-trip is lossless
for all tokenizers.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class TokenLogprob(BaseModel):
    """Per-token log probability from the serving backend."""

    model_config = {"frozen": True}

    token: str
    logprob: float
    top_logprobs: list[dict[str, object]] = Field(default_factory=list)


class GenerationTurn(BaseModel):
    """One model generation turn within a worker episode.

    ``prompt_text`` is the formatted user-facing prompt for this turn.
    Set by the worker on the first yielded turn so the RL extraction
    pipeline can build ``prompt_ids`` without parsing SDK-specific payloads.

    ``raw_response`` is the framework-native serialisation of the model
    response. Not normalised — carries whatever the framework produces.

    ``tool_results`` carries the tool execution outputs that were fed
    back to the model before the next turn.

    ``logprobs`` is populated when the serving backend provides them
    (vLLM with ``openai_logprobs=True``).
    """

    model_config = {"frozen": True}

    prompt_text: str | None = None
    raw_response: dict[str, object]
    tool_results: list[dict[str, object]] = Field(default_factory=list)

    logprobs: list[TokenLogprob] | None = None
    policy_version: str | None = None

    # Timing — set by framework in worker_execute.py, not by workers
    started_at: datetime | None = None
    completed_at: datetime | None = None
