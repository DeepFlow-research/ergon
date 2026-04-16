# ergon_core/ergon_core/core/persistence/context/assembly.py
"""Reconstruct PydanticAI message history from stored context events.

Used by ReActWorker.from_buffer() to resume a paused execution.
Events must be pre-sorted by sequence (ascending).
"""

from ergon_core.core.persistence.context.event_payloads import (
    AssistantTextPayload,
    SystemPromptPayload,
    ThinkingPayload,
    ToolCallPayload,
    ToolResultPayload,
    UserMessagePayload,
)
from ergon_core.core.persistence.context.models import RunContextEvent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
)
from pydantic_ai.messages import (
    SystemPromptPart as PydanticSystemPromptPart,
)
from pydantic_ai.messages import (
    TextPart as PydanticTextPart,
)
from pydantic_ai.messages import (
    ThinkingPart as PydanticThinkingPart,
)
from pydantic_ai.messages import (
    ToolCallPart as PydanticToolCallPart,
)
from pydantic_ai.messages import (
    ToolReturnPart as PydanticToolReturnPart,
)
from pydantic_ai.messages import (
    UserPromptPart as PydanticUserPromptPart,
)


def _to_response_part(event: RunContextEvent):
    """Convert a model-output event to its PydanticAI response part."""
    parsed = event.parsed_payload()
    if event.event_type == "thinking":
        if not isinstance(parsed, ThinkingPayload):
            raise ValueError(f"Expected ThinkingPayload for thinking event, got {type(parsed)}")
        return PydanticThinkingPart(content=parsed.text)
    if event.event_type == "assistant_text":
        if not isinstance(parsed, AssistantTextPayload):
            raise ValueError(
                f"Expected AssistantTextPayload for assistant_text event, got {type(parsed)}"
            )
        return PydanticTextPart(content=parsed.text)
    if event.event_type == "tool_call":
        if not isinstance(parsed, ToolCallPayload):
            raise ValueError(f"Expected ToolCallPayload for tool_call event, got {type(parsed)}")
        return PydanticToolCallPart(
            tool_name=parsed.tool_name,
            tool_call_id=parsed.tool_call_id,
            args=parsed.args,
        )
    raise ValueError(f"Unexpected response event_type: {event.event_type!r}")


def _to_request_part(event: RunContextEvent):
    """Convert a request-side event to its PydanticAI request part."""
    parsed = event.parsed_payload()
    if event.event_type == "system_prompt":
        if not isinstance(parsed, SystemPromptPayload):
            raise ValueError(
                f"Expected SystemPromptPayload for system_prompt event, got {type(parsed)}"
            )
        return PydanticSystemPromptPart(content=parsed.text)
    if event.event_type == "user_message":
        if not isinstance(parsed, UserMessagePayload):
            raise ValueError(
                f"Expected UserMessagePayload for user_message event, got {type(parsed)}"
            )
        return PydanticUserPromptPart(content=parsed.text)
    if event.event_type == "tool_result":
        if not isinstance(parsed, ToolResultPayload):
            raise ValueError(
                f"Expected ToolResultPayload for tool_result event, got {type(parsed)}"
            )
        return PydanticToolReturnPart(
            tool_call_id=parsed.tool_call_id,
            tool_name=parsed.tool_name,
            content=str(parsed.result),
        )
    raise ValueError(f"Unexpected request event_type: {event.event_type!r}")


def assemble_pydantic_ai_messages(events: list[RunContextEvent]) -> list[ModelMessage]:
    """Reconstruct the alternating ModelRequest / ModelResponse sequence.

    Grouping rules:
    - system_prompt / user_message → parts of the leading ModelRequest
    - thinking / assistant_text / tool_call → parts of the current ModelResponse
    - tool_result → closes the current ModelResponse, opens a new ModelRequest
    - Trailing response (no subsequent tool_result) is flushed at end.
    """
    messages: list[ModelMessage] = []
    current_request_parts: list = []
    current_response_parts: list = []

    for event in events:
        if event.event_type in ("system_prompt", "user_message"):
            current_request_parts.append(_to_request_part(event))

        elif event.event_type in ("thinking", "assistant_text", "tool_call"):
            # First model-generated event: flush the pending request
            if current_request_parts and not current_response_parts:
                messages.append(ModelRequest(parts=current_request_parts))
                current_request_parts = []
            current_response_parts.append(_to_response_part(event))

        elif event.event_type == "tool_result":
            if current_response_parts:
                messages.append(ModelResponse(parts=current_response_parts))
                current_response_parts = []
            current_request_parts.append(_to_request_part(event))

    if current_response_parts:
        messages.append(ModelResponse(parts=current_response_parts))

    return messages
