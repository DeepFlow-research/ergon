"""State tests for context event assembly -> PydanticAI message history."""

from uuid import uuid4

from ergon_builtins.common.llm_context.adapters.pydantic_ai import PydanticAITranscriptAdapter
from ergon_core.core.domain.generation.context_parts import (
    AssistantTextPart,
    ContextPartChunkLog,
    SystemPromptPart,
    ThinkingPart,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)
from ergon_core.core.persistence.context.models import RunContextEvent
from pydantic_ai.messages import ModelRequest, ModelResponse
from pydantic_ai.messages import SystemPromptPart as PydanticSystemPromptPart
from pydantic_ai.messages import TextPart as PydanticTextPart
from pydantic_ai.messages import ThinkingPart as PydanticThinkingPart
from pydantic_ai.messages import ToolCallPart as PydanticToolCallPart
from pydantic_ai.messages import ToolReturnPart as PydanticToolReturnPart


def assemble_pydantic_ai_messages(events: list[RunContextEvent]):
    return PydanticAITranscriptAdapter().assemble_replay(events)


def _make_event(part, sequence: int, turn_id: str | None = None) -> RunContextEvent:
    payload = ContextPartChunkLog(
        part=part,
        sequence=sequence,
        worker_binding_key="test-worker",
        turn_id=turn_id,
    )
    return RunContextEvent(
        run_id=uuid4(),
        task_execution_id=uuid4(),
        worker_binding_key="test-worker",
        sequence=sequence,
        event_type=part.part_kind,
        payload=payload.model_dump(mode="json"),
    )


class TestAssembleSimpleConversation:
    def test_system_and_user_become_model_request(self):
        events = [
            _make_event(SystemPromptPart(content="You are helpful."), 0),
            _make_event(UserMessagePart(content="Hello"), 1),
            _make_event(AssistantTextPart(content="Hi!"), 2, turn_id="t1"),
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
        events = [
            _make_event(SystemPromptPart(content="sys"), 0),
            _make_event(UserMessagePart(content="use tool"), 1),
            _make_event(
                ToolCallPart(
                    tool_call_id="call-1",
                    tool_name="my_tool",
                    args={"x": 1},
                ),
                2,
                turn_id="t1",
            ),
            _make_event(
                ToolResultPart(tool_call_id="call-1", tool_name="my_tool", content="42"),
                3,
            ),
            _make_event(AssistantTextPart(content="The answer is 42."), 4, turn_id="t2"),
        ]

        messages = assemble_pydantic_ai_messages(events)

        assert len(messages) == 4
        assert isinstance(messages[0], ModelRequest)
        assert isinstance(messages[1], ModelResponse)
        assert isinstance(messages[2], ModelRequest)
        assert isinstance(messages[3], ModelResponse)

        tool_call_parts = [p for p in messages[1].parts if isinstance(p, PydanticToolCallPart)]
        assert len(tool_call_parts) == 1
        assert tool_call_parts[0].tool_name == "my_tool"
        assert tool_call_parts[0].tool_call_id == "call-1"

        tool_return_parts = [p for p in messages[2].parts if isinstance(p, PydanticToolReturnPart)]
        assert len(tool_return_parts) == 1
        assert tool_return_parts[0].tool_call_id == "call-1"
        assert tool_return_parts[0].tool_name == "my_tool"
        assert tool_return_parts[0].content == "42"

        text_parts = [p for p in messages[3].parts if isinstance(p, PydanticTextPart)]
        assert len(text_parts) == 1
        assert text_parts[0].content == "The answer is 42."


class TestAssembleWithThinking:
    def test_thinking_appears_in_model_response(self):
        events = [
            _make_event(UserMessagePart(content="hard question"), 0),
            _make_event(ThinkingPart(content="let me think..."), 1, turn_id="t1"),
            _make_event(AssistantTextPart(content="42"), 2, turn_id="t1"),
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
            _make_event(UserMessagePart(content="q"), 0),
            _make_event(AssistantTextPart(content="a"), 1, turn_id="t1"),
        ]

        messages = assemble_pydantic_ai_messages(events)

        assert len(messages) == 2
        assert isinstance(messages[0], ModelRequest)
        assert isinstance(messages[1], ModelResponse)

    def test_request_only_produces_no_assembled_messages(self):
        events = [
            _make_event(SystemPromptPart(content="sys"), 0),
            _make_event(UserMessagePart(content="hi"), 1),
        ]

        messages = assemble_pydantic_ai_messages(events)
        assert messages == []


class TestSystemPromptPartType:
    def test_system_prompt_is_pydantic_system_prompt_part(self):
        events = [
            _make_event(SystemPromptPart(content="Be helpful."), 0),
            _make_event(AssistantTextPart(content="ok"), 1, turn_id="t1"),
        ]

        messages = assemble_pydantic_ai_messages(events)

        request = messages[0]
        system_parts = [p for p in request.parts if isinstance(p, PydanticSystemPromptPart)]
        assert len(system_parts) == 1
        assert system_parts[0].content == "Be helpful."
