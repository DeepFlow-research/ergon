# tests/state/test_generation_turn_build.py
"""Tests for the new _build_turns logic in react_worker."""

from ergon_builtins.workers.baselines.react_worker import _build_turns
from ergon_core.api.generation import (
    GenerationTurn,
)
from ergon_core.api.generation import (
    SystemPromptPart as ErgonSystemPromptPart,
)
from ergon_core.api.generation import (
    TextPart as ErgonTextPart,
)
from ergon_core.api.generation import (
    ToolCallPart as ErgonToolCallPart,
)
from ergon_core.api.generation import (
    ToolReturnPart as ErgonToolReturnPart,
)
from ergon_core.api.generation import (
    UserPromptPart as ErgonUserPromptPart,
)
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)


def _make_messages_text_only():
    """One request → one text response (no tools)."""
    return [
        ModelRequest(
            parts=[
                SystemPromptPart(content="You are helpful."),
                UserPromptPart(content="Hello"),
            ]
        ),
        ModelResponse(parts=[TextPart(content="Hi there!")]),
    ]


def _make_messages_with_tool_call():
    """Request → tool-call response → tool-return request → text response."""
    return [
        ModelRequest(parts=[UserPromptPart(content="Search Paris.")]),
        ModelResponse(
            parts=[ToolCallPart(tool_name="search", tool_call_id="c1", args={"q": "Paris"})]
        ),
        ModelRequest(
            parts=[ToolReturnPart(tool_call_id="c1", tool_name="search", content="pop 2M")]
        ),
        ModelResponse(parts=[TextPart(content="Paris has 2M people.")]),
    ]


class TestBuildTurns:
    def test_text_only_produces_one_turn(self):
        turns = _build_turns(_make_messages_text_only())
        assert len(turns) == 1
        t = turns[0]
        assert isinstance(t, GenerationTurn)
        assert any(isinstance(p, ErgonSystemPromptPart) for p in t.messages_in)
        assert any(isinstance(p, ErgonUserPromptPart) for p in t.messages_in)
        assert any(isinstance(p, ErgonTextPart) for p in t.response_parts)
        assert t.tool_results == []

    def test_tool_call_has_tool_results(self):
        turns = _build_turns(_make_messages_with_tool_call())
        assert len(turns) == 2
        first = turns[0]
        assert len(first.tool_results) == 1
        tr = first.tool_results[0]
        assert isinstance(tr, ErgonToolReturnPart)
        assert tr.tool_call_id == "c1"
        assert tr.content == "pop 2M"

    def test_tool_results_not_in_second_turn_messages_in(self):
        """ToolReturnParts must NOT appear in messages_in — they're in tool_results."""
        turns = _build_turns(_make_messages_with_tool_call())
        second = turns[1]
        tool_return_in_messages = [
            p for p in second.messages_in if isinstance(p, ErgonToolReturnPart)
        ]
        assert tool_return_in_messages == []
