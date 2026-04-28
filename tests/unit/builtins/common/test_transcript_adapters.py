from uuid import uuid4

from ergon_builtins.common.llm_context.adapters.base import TranscriptAdapter
from ergon_builtins.common.llm_context.adapters.pydantic_ai import (
    PydanticAITranscriptAdapter,
    TranscriptTurnCursor,
)
from ergon_core.core.generation import (
    GenerationTurn,
    TextPart as ErgonTextPart,
    ThinkingPart as ErgonThinkingPart,
    ToolCallPart as ErgonToolCallPart,
    ToolReturnPart as ErgonToolReturnPart,
    UserPromptPart as ErgonUserPromptPart,
)
from ergon_core.core.persistence.context.event_payloads import (
    AssistantTextPayload,
    ContextEventType,
    SystemPromptPayload,
    ThinkingPayload,
    ToolCallPayload,
    ToolResultPayload,
    UserMessagePayload,
)
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


def _make_event(event_type: str, payload, sequence: int) -> RunContextEvent:
    return RunContextEvent(
        run_id=uuid4(),
        task_execution_id=uuid4(),
        worker_binding_key="test-worker",
        sequence=sequence,
        event_type=event_type,
        payload=payload.model_dump(mode="json"),
    )


def test_generation_part_kinds_have_context_event_counterparts() -> None:
    assert ErgonTextPart(content="x").part_kind == "text"
    assert ErgonThinkingPart(content="x").part_kind == "thinking"
    assert ErgonToolCallPart(tool_name="t", tool_call_id="1", args={}).part_kind == "tool-call"
    assert (
        ErgonToolReturnPart(tool_call_id="1", tool_name="t", content="ok").part_kind
        == "tool-return"
    )

    assert "assistant_text" in ContextEventType.__args__
    assert "thinking" in ContextEventType.__args__
    assert "tool_call" in ContextEventType.__args__
    assert "tool_result" in ContextEventType.__args__


def test_text_and_thinking_are_response_parts() -> None:
    adapter: TranscriptAdapter[
        list[ModelRequest | ModelResponse], list[ModelRequest | ModelResponse]
    ]
    adapter = PydanticAITranscriptAdapter()

    turns = adapter.build_turns(
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

    assert len(turns) == 1
    turn = turns[0]
    assert isinstance(turn, GenerationTurn)
    assert any(isinstance(part, ErgonUserPromptPart) for part in turn.messages_in)
    assert any(isinstance(part, ErgonThinkingPart) for part in turn.response_parts)
    assert any(isinstance(part, ErgonTextPart) for part in turn.response_parts)


def test_tool_return_is_attached_to_generating_turn() -> None:
    adapter = PydanticAITranscriptAdapter()

    turns = adapter.build_turns(
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
            ModelResponse(parts=[TextPart(content="done")]),
        ]
    )

    assert len(turns) == 2
    first = turns[0]
    assert any(isinstance(part, ErgonToolCallPart) for part in first.response_parts)
    assert len(first.tool_results) == 1
    result = first.tool_results[0]
    assert isinstance(result, ErgonToolReturnPart)
    assert result.tool_call_id == "call-1"
    assert result.tool_name == "search"
    assert result.content == '{"result": "found"}'


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

    assert adapter.build_new_turns(transcript, cursor, flush_pending=False) == []

    flushed = adapter.build_new_turns(transcript, cursor, flush_pending=True)
    assert len(flushed) == 1
    assert any(isinstance(part, ErgonToolCallPart) for part in flushed[0].response_parts)


def test_incremental_extraction_tracks_emitted_turns() -> None:
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

    first = adapter.build_new_turns(transcript, cursor, flush_pending=False)
    second = adapter.build_new_turns(transcript, cursor, flush_pending=False)

    assert len(first) == 1
    assert second == []


def test_assemble_replay_reconstructs_pydantic_ai_messages() -> None:
    events = [
        _make_event("system_prompt", SystemPromptPayload(text="sys"), 0),
        _make_event("user_message", UserMessagePayload(text="use tool"), 1),
        _make_event(
            "tool_call",
            ToolCallPayload(
                tool_call_id="call-1",
                tool_name="my_tool",
                args={"x": 1},
                turn_id="t1",
            ),
            2,
        ),
        _make_event(
            "tool_result",
            ToolResultPayload(tool_call_id="call-1", tool_name="my_tool", result="42"),
            3,
        ),
        _make_event(
            "thinking",
            ThinkingPayload(text="considering", turn_id="t2"),
            4,
        ),
        _make_event(
            "assistant_text",
            AssistantTextPayload(text="The answer is 42.", turn_id="t2"),
            5,
        ),
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
