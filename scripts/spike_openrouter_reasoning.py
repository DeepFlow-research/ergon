"""Spike reasoning settings and streamed thinking events.

Usage:
    uv run python scripts/spike_openrouter_reasoning.py
    uv run python scripts/spike_openrouter_reasoning.py --model openrouter:anthropic/claude-opus-4.7
    uv run python scripts/spike_openrouter_reasoning.py --model anthropic:claude-opus-4.7

The script always prints Ergon's resolved model settings. If OPENROUTER_API_KEY
is available, it also runs one tiny PydanticAI streaming request and reports
whether ThinkingPart / ThinkingPartDelta events are surfaced.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections import Counter
from typing import Any

# Register production model backends before resolving OpenRouter targets.
import ergon_builtins.registry  # noqa: F401
from ergon_builtins.models.resolution import resolve_model_target
from pydantic_ai import Agent
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
)


def _thinking_content(part: ThinkingPart) -> str:
    if part.content:
        return part.content
    details = part.provider_details
    if isinstance(details, dict):
        raw_content = details.get("raw_content")
        if isinstance(raw_content, str):
            return raw_content
    return ""


async def _run_stream(model: str, prompt: str) -> None:
    resolved = resolve_model_target(model)
    print(f"resolved.model={resolved.model!r}")
    print(f"resolved.capture_model_settings={resolved.capture_model_settings!r}")

    required_key = _required_api_key_name(model)
    if required_key and not os.environ.get(required_key):
        print(f"{required_key} is not set; skipping live call.")
        return

    agent: Agent[None, str] = Agent(
        model=resolved.model,
        instructions=("Answer briefly. Use reasoning if available, then give the final answer."),
        output_type=str,
    )

    counts: Counter[str] = Counter()
    thinking_chunks: list[str] = []

    async with agent.iter(
        prompt,
        model_settings=resolved.capture_model_settings,
    ) as run:
        async for node in run:
            if Agent.is_model_request_node(node) or Agent.is_call_tools_node(node):
                async with node.stream(run.ctx) as stream:
                    async for event in stream:
                        counts[type(event).__name__] += 1
                        _record_part_shape(event, counts)
                        _record_thinking_event(event, thinking_chunks, counts)

    print(f"event_counts={dict(counts)}")
    print(f"thinking_chunk_count={len(thinking_chunks)}")
    if thinking_chunks:
        preview = "".join(thinking_chunks)[:1000]
        print(f"thinking_preview={preview!r}")
    else:
        print("thinking_preview=None")


def _record_part_shape(event: Any, counts: Counter[str]) -> None:
    if isinstance(event, PartStartEvent):
        counts[f"PartStartEvent:{type(event.part).__name__}"] += 1
    elif isinstance(event, PartDeltaEvent):
        counts[f"PartDeltaEvent:{type(event.delta).__name__}"] += 1
        if isinstance(event.delta, TextPartDelta) and event.delta.content_delta:
            counts["text_delta_chars"] += len(event.delta.content_delta)
    elif isinstance(event, PartEndEvent):
        counts[f"PartEndEvent:{type(event.part).__name__}"] += 1


def _record_thinking_event(
    event: Any,
    thinking_chunks: list[str],
    counts: Counter[str],
) -> None:
    if isinstance(event, PartStartEvent) and isinstance(event.part, ThinkingPart):
        counts["ThinkingPart:start"] += 1
        if content := _thinking_content(event.part):
            thinking_chunks.append(content)
    elif isinstance(event, PartDeltaEvent) and isinstance(
        event.delta,
        ThinkingPartDelta,
    ):
        counts["ThinkingPartDelta"] += 1
        if event.delta.content_delta:
            thinking_chunks.append(event.delta.content_delta)
    elif isinstance(event, PartEndEvent) and isinstance(event.part, ThinkingPart):
        counts["ThinkingPart:end"] += 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default="openrouter:anthropic/claude-opus-4.7",
        help="Model target to resolve and optionally call.",
    )
    parser.add_argument(
        "--prompt",
        default="In one sentence, explain why task decomposition helps research agents.",
    )
    args = parser.parse_args()
    asyncio.run(_run_stream(args.model, args.prompt))


def _required_api_key_name(model: str) -> str | None:
    if model.startswith(("openrouter:", "openai-responses:")):
        return "OPENROUTER_API_KEY"
    if model.startswith("anthropic:"):
        return "ANTHROPIC_API_KEY"
    return None


if __name__ == "__main__":
    main()
