from pydantic import TypeAdapter

from ergon_core.core.shared.context_parts import (
    AssistantTextPart,
    ContextPart,
    ContextPartChunk,
    ContextPartChunkLog,
    SystemPromptPart,
    ThinkingPart,
    TokenLogprob,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)


def test_context_part_discriminates_all_part_kinds() -> None:
    adapter = TypeAdapter(ContextPart)

    cases = [
        SystemPromptPart(content="sys"),
        UserMessagePart(content="hi"),
        AssistantTextPart(content="hello"),
        ToolCallPart(tool_call_id="call-1", tool_name="search", args={"q": "x"}),
        ToolResultPart(tool_call_id="call-1", tool_name="search", content="ok"),
        ThinkingPart(content="reasoning"),
    ]

    for part in cases:
        dumped = part.model_dump(mode="json")
        parsed = adapter.validate_python(dumped)
        assert parsed == part


def test_context_part_chunk_wraps_part_with_optional_token_metadata() -> None:
    chunk = ContextPartChunk(
        part=AssistantTextPart(content="answer"),
        token_ids=[1, 2],
        logprobs=[TokenLogprob(token="answer", logprob=-0.1)],
    )

    dumped = chunk.model_dump(mode="json")

    assert dumped["part"]["part_kind"] == "assistant_text"
    assert dumped["token_ids"] == [1, 2]
    assert dumped["logprobs"][0]["token"] == "answer"


def test_context_part_chunk_log_adds_core_enrichment() -> None:
    log = ContextPartChunkLog(
        part=ThinkingPart(content="hmm"),
        sequence=7,
        worker_binding_key="researcher",
        turn_id="turn-1",
        token_ids=None,
        logprobs=None,
    )

    dumped = log.model_dump(mode="json")

    assert dumped["part"]["part_kind"] == "thinking"
    assert dumped["sequence"] == 7
    assert dumped["worker_binding_key"] == "researcher"
    assert dumped["turn_id"] == "turn-1"
