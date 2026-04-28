"""Typed context event payload exports.

The canonical context payload is an enriched ContextPartChunkLog. Event-specific
payload classes were removed in favor of ContextPartChunkLog.part.
"""

from typing import Literal

from ergon_core.core.generation import ContextPart, ContextPartChunk, ContextPartChunkLog

ContextEventType = Literal[
    "system_prompt",
    "user_message",
    "assistant_text",
    "tool_call",
    "tool_result",
    "thinking",
]

ContextEventPayload = ContextPartChunkLog
