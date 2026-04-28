from uuid import uuid4

from ergon_builtins.common.llm_context.adapters.pydantic_ai import (
    PydanticAITranscriptAdapter,
    TranscriptTurnCursor,
)
from ergon_core.core.generation import (
    AssistantTextPart,
    ContextPartChunkLog,
    SystemPromptPart as ErgonSystemPromptPart,
    ThinkingPart as ErgonThinkingPart,
    ToolCallPart as ErgonToolCallPart,
    ToolResultPart as ErgonToolResultPart,
    UserMessagePart as ErgonUserMessagePart,
)
from ergon_core.core.persistence.context.event_payloads import ContextEventType
from ergon_core.core.persistence.context.models import RunContextEvent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.messages import TextPart as PydanticTextPart
from pydantic_ai.messages import ThinkingPart as PydanticThinkingPart
from pydantic_ai.messages import ToolCallPart as PydanticToolCallPart
from pydantic_ai.messages import ToolReturnPart as PydanticToolReturnPart


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


def test_context_part_kinds_are_context_event_types() -> None:
    assert AssistantTextPart(content="x").part_kind == "assistant_text"
    assert ErgonThinkingPart(content="x").part_kind == "thinking"
    assert ErgonToolCallPart(tool_name="t", tool_call_id="1", args={}).part_kind == "tool_call"
    assert (
        ErgonToolResultPart(tool_call_id="1", tool_name="t", content="ok").part_kind
        == "tool_result"
    )

    assert "assistant_text" in ContextEventType.__args__
    assert "thinking" in ContextEventType.__args__
    assert "tool_call" in ContextEventType.__args__
    assert "tool_result" in ContextEventType.__args__


def test_text_and_thinking_are_context_part_chunks() -> None:
    adapter = PydanticAITranscriptAdapter()

    chunks = adapter.build_chunks(
        [
            ModelRequest(parts=[UserPromptPart(content="hard question")]),
            ModelResponse(
                parts=[
                    ThinkingPart(content="let me reason"),
                    TextPart(content="answer"),
                ]
            ),
        ]
    )

    assert [chunk.part.part_kind for chunk in chunks] == [
        "user_message",
        "thinking",
        "assistant_text",
    ]
    assert isinstance(chunks[0].part, ErgonUserMessagePart)
    assert isinstance(chunks[1].part, ErgonThinkingPart)
    assert isinstance(chunks[2].part, AssistantTextPart)


def test_tool_call_and_return_become_context_part_chunks() -> None:
    adapter = PydanticAITranscriptAdapter()

    chunks = adapter.build_chunks(
        [
            ModelRequest(parts=[UserPromptPart(content="search")]),
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="search",
                        tool_call_id="call-1",
                        args={"query": "ergon"},
                    )
                ]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="search",
                        tool_call_id="call-1",
                        content={"result": "found"},
                    )
                ]
            ),
        ]
    )

    assert [chunk.part.part_kind for chunk in chunks] == [
        "user_message",
        "tool_call",
        "tool_result",
    ]
    tool_result = chunks[-1].part
    assert isinstance(tool_result, ErgonToolResultPart)
    assert tool_result.content == '{"result": "found"}'


def test_incremental_extraction_does_not_emit_pending_tool_call_response() -> None:
    adapter = PydanticAITranscriptAdapter()
    cursor = TranscriptTurnCursor()
    transcript = [
        ModelRequest(parts=[UserPromptPart(content="search")]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="search",
                    tool_call_id="call-1",
                    args={"query": "ergon"},
                )
            ]
        ),
    ]

    first = adapter.build_new_chunks(transcript, cursor, flush_pending=False)
    assert [chunk.part.part_kind for chunk in first] == ["user_message"]

    flushed = adapter.build_new_chunks(transcript, cursor, flush_pending=True)
    assert [chunk.part.part_kind for chunk in flushed] == ["tool_call"]


def test_incremental_extraction_tracks_emitted_chunks() -> None:
    adapter = PydanticAITranscriptAdapter()
    cursor = TranscriptTurnCursor()
    transcript = [
        ModelRequest(parts=[UserPromptPart(content="search")]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="search",
                    tool_call_id="call-1",
                    args={"query": "ergon"},
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="search",
                    tool_call_id="call-1",
                    content={"result": "found"},
                )
            ]
        ),
    ]

    first = adapter.build_new_chunks(transcript, cursor, flush_pending=False)
    second = adapter.build_new_chunks(transcript, cursor, flush_pending=False)

    assert [chunk.part.part_kind for chunk in first] == [
        "user_message",
        "tool_call",
        "tool_result",
    ]
    assert second == []


def test_assemble_replay_reconstructs_pydantic_ai_messages() -> None:
    events = [
        _make_event(ErgonSystemPromptPart(content="sys"), 0),
        _make_event(ErgonUserMessagePart(content="use tool"), 1),
        _make_event(
            ErgonToolCallPart(
                tool_call_id="call-1",
                tool_name="my_tool",
                args={"x": 1},
            ),
            2,
            turn_id="t1",
        ),
        _make_event(
            ErgonToolResultPart(tool_call_id="call-1", tool_name="my_tool", content="42"),
            3,
        ),
        _make_event(ErgonThinkingPart(content="considering"), 4, turn_id="t2"),
        _make_event(AssistantTextPart(content="The answer is 42."), 5, turn_id="t2"),
    ]

    messages = PydanticAITranscriptAdapter().assemble_replay(events)

    assert len(messages) == 4
    assert isinstance(messages[0], ModelRequest)
    assert isinstance(messages[1], ModelResponse)
    assert isinstance(messages[2], ModelRequest)
    assert isinstance(messages[3], ModelResponse)
    assert any(isinstance(part, PydanticToolCallPart) for part in messages[1].parts)
    assert any(isinstance(part, PydanticToolReturnPart) for part in messages[2].parts)
    assert any(isinstance(part, PydanticThinkingPart) for part in messages[3].parts)
    assert any(isinstance(part, PydanticTextPart) for part in messages[3].parts)
