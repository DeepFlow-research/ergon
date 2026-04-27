"""Single source of truth for parsing PydanticAI's serialised message format.

PydanticAI serialises ``ModelResponse`` via ``dataclasses.asdict()`` into::

    {
        "parts": [
            {"part_kind": "text", "content": "..."},
            {"part_kind": "tool-call", "tool_call_id": "...", "tool_name": "...", "args": {...}},
        ],
        "provider_details": {"logprobs": [{"token": "...", "logprob": -0.1, ...}]},
        ...
    }

All code that needs to read these dumps should call into this module
rather than re-implementing the parsing.
"""

from ergon_core.api.json_types import JsonObject
from ergon_core.core.providers.generation.types import TokenLogprob


def extract_logprobs(
    raw: JsonObject,
) -> list[TokenLogprob] | None:
    """Extract per-token logprobs from a PydanticAI response dump.

    PydanticAI stores vLLM logprobs in ``provider_details["logprobs"]``.
    Returns None if no logprobs are available (cloud APIs).
    """
    details = raw.get("provider_details")
    if not isinstance(details, dict):
        return None
    raw_logprobs = details.get("logprobs")
    if not isinstance(raw_logprobs, list) or not raw_logprobs:
        return None
    return [
        TokenLogprob(
            token=entry["token"],
            logprob=entry["logprob"],
            top_logprobs=entry.get("top_logprobs", []),
        )
        for entry in raw_logprobs
        if isinstance(entry, dict) and "token" in entry and "logprob" in entry
    ]
