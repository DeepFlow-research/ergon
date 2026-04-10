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

from ergon_core.api.generation import TokenLogprob


def extract_text(raw: dict[str, object]) -> str | None:
    """Extract the first text content from a PydanticAI response dump."""
    parts = raw.get("parts")
    if not isinstance(parts, list):
        return None
    for part in parts:
        if isinstance(part, dict) and part.get("part_kind") == "text":
            content = part.get("content")
            if isinstance(content, str):
                return content
    return None


def extract_tool_calls(
    raw: dict[str, object],
) -> list[dict[str, object]] | None:
    """Extract tool call dicts from a PydanticAI response dump."""
    parts = raw.get("parts")
    if not isinstance(parts, list):
        return None
    calls: list[dict[str, object]] = []
    for part in parts:
        if isinstance(part, dict) and part.get("part_kind") == "tool-call":
            calls.append(
                {
                    "tool_call_id": part.get("tool_call_id", ""),
                    "tool_name": part.get("tool_name", ""),
                    "args": part.get("args"),
                }
            )
    return calls or None


def extract_logprobs(
    raw: dict[str, object],
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
