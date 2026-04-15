"""State tests for context event assembly → PydanticAI message history.

Tests the assemble_pydantic_ai_messages function using RunContextEvent
instances built directly (no DB round-trip needed for pure logic tests).
"""

from uuid import uuid4

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart as PydanticSystemPromptPart,
    TextPart as PydanticTextPart,
    ThinkingPart as PydanticThinkingPart,
    ToolCallPart as PydanticToolCallPart,
    ToolReturnPart as PydanticToolReturnPart,
    UserPromptPart as PydanticUserPromptPart,
)

from ergon_core.core.persistence.context.assembly import assemble_pydantic_ai_messages
from ergon_core.core.persistence.context.event_payloads import (
    AssistantTextPayload,
    SystemPromptPayload,
    ThinkingPayload,
    ToolCallPayload,
    ToolResultPayload,
    UserMessagePayload,
)
from ergon_core.core.persistence.context.models import RunContextEvent


def _make_event(event_type: str, payload, sequence: int) -> RunContextEvent:
    run_id = uuid4()
    exec_id = uuid4()
    return RunContextEvent(
        run_id=run_id,
        task_execution_id=exec_id,
        worker_binding_key="test-worker",
        sequence=sequence,
        event_type=event_type,
        payload=payload.model_dump(mode="json"),
    )


class TestAssembleSimpleConversation:
    def test_system_and_user_become_model_request(self):
        events = [
            _make_event("system_prompt", SystemPromptPayload(text="You are helpful."), 0),
            _make_event("user_message", UserMessagePayload(text="Hello"), 1),
            _make_event(
                "assistant_text",
                AssistantTextPayload(text="Hi!", turn_id="t1"),
                2,
            ),
        ]

        messages = assemble_pydantic_ai_messages(events)

        assert len(messages) == 2
        request = messages[0]
        response = messages[1]

        assert isinstance(request, ModelRequest)
        assert isinstance(response, ModelResponse)

        part_kinds = [p.part_kind for p in request.parts]
        assert "system-prompt" in part_kinds
        assert "user-prompt" in part_kinds

        assert len(response.parts) == 1
        assert isinstance(response.parts[0], PydanticTextPart)
        assert response.parts[0].content == "Hi!"

    def test_empty_events_returns_empty_list(self):
        messages = assemble_pydantic_ai_messages([])
        assert messages == []


class TestAssembleWithToolCall:
    def test_tool_call_in_response_and_tool_result_in_next_request(self):
        tool_turn_id = "t1"
        events = [
            _make_event("system_prompt", SystemPromptPayload(text="sys"), 0),
            _make_event("user_message", UserMessagePayload(text="use tool"), 1),
            _make_event(
                "tool_call",
                ToolCallPayload(
                    tool_call_id="call-1",
                    tool_name="my_tool",
                    args={"x": 1},
                    turn_id=tool_turn_id,
                ),
                2,
            ),
            _make_event(
                "tool_result",
                ToolResultPayload(
                    tool_call_id="call-1",
                    tool_name="my_tool",
                    result="42",
                ),
                3,
            ),
            _make_event(
                "assistant_text",
                AssistantTextPayload(text="The answer is 42.", turn_id="t2"),
                4,
            ),
        ]

        messages = assemble_pydantic_ai_messages(events)

        # 3 messages: initial request, tool-call response, tool-result+continuation request
        # But the last assistant_text has no following tool_result, so it's a trailing response
        # Expected structure:
        # [0] ModelRequest(system_prompt, user_message)
        # [1] ModelResponse(tool_call)
        # [2] ModelRequest(tool_return)  <- tool_result flushes response and opens request
        # [3] ModelResponse(assistant_text)  <- trailing response flushed at end
        assert len(messages) == 4

        assert isinstance(messages[0], ModelRequest)
        assert isinstance(messages[1], ModelResponse)
        assert isinstance(messages[2], ModelRequest)
        assert isinstance(messages[3], ModelResponse)

        # Check tool call part
        tool_call_parts = [p for p in messages[1].parts if isinstance(p, PydanticToolCallPart)]
        assert len(tool_call_parts) == 1
        assert tool_call_parts[0].tool_name == "my_tool"
        assert tool_call_parts[0].tool_call_id == "call-1"

        # Check tool return part
        tool_return_parts = [p for p in messages[2].parts if isinstance(p, PydanticToolReturnPart)]
        assert len(tool_return_parts) == 1
        assert tool_return_parts[0].tool_call_id == "call-1"
        assert tool_return_parts[0].tool_name == "my_tool"
        assert tool_return_parts[0].content == "42"

        # Check final text response
        text_parts = [p for p in messages[3].parts if isinstance(p, PydanticTextPart)]
        assert len(text_parts) == 1
        assert text_parts[0].content == "The answer is 42."


class TestAssembleWithThinking:
    def test_thinking_appears_in_model_response(self):
        events = [
            _make_event("user_message", UserMessagePayload(text="hard question"), 0),
            _make_event(
                "thinking",
                ThinkingPayload(text="let me think...", turn_id="t1"),
                1,
            ),
            _make_event(
                "assistant_text",
                AssistantTextPayload(text="42", turn_id="t1"),
                2,
            ),
        ]

        messages = assemble_pydantic_ai_messages(events)

        assert len(messages) == 2
        assert isinstance(messages[0], ModelRequest)
        assert isinstance(messages[1], ModelResponse)

        thinking_parts = [p for p in messages[1].parts if isinstance(p, PydanticThinkingPart)]
        text_parts = [p for p in messages[1].parts if isinstance(p, PydanticTextPart)]
        assert len(thinking_parts) == 1
        assert len(text_parts) == 1
        assert thinking_parts[0].content == "let me think..."
        assert text_parts[0].content == "42"


class TestAssembleTrailingResponse:
    def test_trailing_response_without_tool_result_is_flushed(self):
        events = [
            _make_event("user_message", UserMessagePayload(text="q"), 0),
            _make_event(
                "assistant_text",
                AssistantTextPayload(text="a", turn_id="t1"),
                1,
            ),
        ]

        messages = assemble_pydantic_ai_messages(events)

        assert len(messages) == 2
        assert isinstance(messages[0], ModelRequest)
        assert isinstance(messages[1], ModelResponse)

    def test_only_request_events_no_response(self):
        events = [
            _make_event("system_prompt", SystemPromptPayload(text="sys"), 0),
            _make_event("user_message", UserMessagePayload(text="hi"), 1),
        ]

        # No model-generated events — request parts never flushed to a message
        # (they'd be pending). Assembly returns empty because no response events trigger flush.
        messages = assemble_pydantic_ai_messages(events)
        # Request-only: not flushed because no response event triggers it
        assert len(messages) == 0


class TestSystemPromptPartType:
    def test_system_prompt_is_pydantic_system_prompt_part(self):
        events = [
            _make_event("system_prompt", SystemPromptPayload(text="Be helpful."), 0),
            _make_event(
                "assistant_text",
                AssistantTextPayload(text="ok", turn_id="t1"),
                1,
            ),
        ]

        messages = assemble_pydantic_ai_messages(events)

        request = messages[0]
        system_parts = [p for p in request.parts if isinstance(p, PydanticSystemPromptPart)]
        assert len(system_parts) == 1
        assert system_parts[0].content == "Be helpful."
