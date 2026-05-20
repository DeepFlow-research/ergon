from uuid import uuid4

from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.shared.context_parts import (
    AssistantTextPart,
    ContextPartChunkLog,
    ProviderTokenUsage,
    ThinkingPart,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)
from ergon_core.core.views.runs.metrics import (
    aggregate_run_metrics,
    observed_cost_from_summary,
)


def _event(event_type: str, payload: ContextPartChunkLog) -> RunContextEvent:
    return RunContextEvent(
        run_id=uuid4(),
        task_execution_id=uuid4(),
        worker_binding_key="worker",
        sequence=payload.sequence,
        event_type=event_type,
        payload=payload.model_dump(mode="json"),
    )


def test_run_metric_aggregation_counts_tools_and_token_breakdown() -> None:
    events = [
        _event(
            "user_message",
            ContextPartChunkLog(
                part=UserMessagePart(content="question"),
                sequence=0,
                worker_binding_key="worker",
                provider_usage=ProviderTokenUsage(prompt_tokens=8, cached_tokens=3),
            ),
        ),
        _event(
            "assistant_text",
            ContextPartChunkLog(
                part=AssistantTextPart(content="answer"),
                token_ids=[101, 102],
                sequence=1,
                worker_binding_key="worker",
            ),
        ),
        _event(
            "thinking",
            ContextPartChunkLog(
                part=ThinkingPart(content="private reasoning"),
                sequence=2,
                worker_binding_key="worker",
                provider_usage=ProviderTokenUsage(reasoning_tokens=5),
            ),
        ),
        _event(
            "tool_call",
            ContextPartChunkLog(
                part=ToolCallPart(tool_call_id="call-1", tool_name="search", args={"q": "x"}),
                sequence=3,
                worker_binding_key="worker",
                provider_usage=ProviderTokenUsage(tool_call_tokens=7),
            ),
        ),
        _event(
            "tool_result",
            ContextPartChunkLog(
                part=ToolResultPart(tool_call_id="call-1", tool_name="search", content="ok"),
                token_ids=[201, 202, 203, 204],
                sequence=4,
                worker_binding_key="worker",
            ),
        ),
    ]

    metrics = aggregate_run_metrics(events, summary={})

    assert metrics.tool_call_count == 1
    assert metrics.total_tokens == 29
    assert metrics.token_breakdown == {
        "prompt": 8,
        "assistant_text": 2,
        "thinking": 5,
        "tool_call": 7,
        "tool_result": 4,
        "cached": 3,
        "unknown": 0,
    }


def test_provider_usage_completion_tokens_fall_back_to_event_semantics() -> None:
    events = [
        _event(
            "assistant_text",
            ContextPartChunkLog(
                part=AssistantTextPart(content="answer"),
                sequence=0,
                worker_binding_key="worker",
                provider_usage=ProviderTokenUsage(completion_tokens=11),
            ),
        )
    ]

    metrics = aggregate_run_metrics(events, summary={})

    assert metrics.total_tokens == 11
    assert metrics.token_breakdown["assistant_text"] == 11


def test_default_summary_zero_cost_is_not_observed() -> None:
    assert observed_cost_from_summary({"total_cost_usd": 0.0}) == (None, False)
    assert observed_cost_from_summary({"total_cost_usd": 0.42}) == (0.42, True)
    assert observed_cost_from_summary({"total_cost_usd": 0.0, "cost_observed": True}) == (
        0.0,
        True,
    )
    assert observed_cost_from_summary({"cost": {"total_cost_usd": 1.25, "observed": True}}) == (
        1.25,
        True,
    )
