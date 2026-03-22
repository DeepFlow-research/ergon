from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.usage import RunUsage

from h_arcane.benchmarks.common.workers.config import WorkerConfig
from h_arcane.benchmarks.common.workers.react_worker import ReActWorker
from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.core.worker import WorkerContext


def test_extract_actions_uses_tool_call_and_return_timestamps():
    worker = ReActWorker(
        model="gpt-4o-mini",
        config=WorkerConfig(
            benchmark_name=BenchmarkName.SMOKE_TEST,
            system_prompt="You are a test worker.",
        ),
    )
    context = WorkerContext(
        run_id=uuid4(),
        task_id=uuid4(),
        agent_config_id=uuid4(),
    )
    started_at = datetime(2026, 3, 19, 18, 48, 23, tzinfo=timezone.utc)
    completed_at = started_at + timedelta(milliseconds=1250)
    tool_call_id = "call-123"

    messages = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="search_lemmas",
                    args={"query": "nat.succ"},
                    tool_call_id=tool_call_id,
                )
            ],
            timestamp=started_at,
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="search_lemmas",
                    content={"matches": ["Nat.succ_eq_add_one"]},
                    tool_call_id=tool_call_id,
                    timestamp=completed_at,
                )
            ],
            timestamp=completed_at,
        ),
    ]

    actions = worker._extract_actions_from_messages(
        messages=messages,
        usage=RunUsage(input_tokens=10, output_tokens=5),
        context=context,
    )

    assert len(actions) == 1
    action = actions[0]
    assert action.action_type == "search_lemmas"
    assert action.started_at == started_at
    assert action.completed_at == completed_at
    assert action.duration_ms == 1250
