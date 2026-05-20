"""Run metric aggregation helpers for read models."""

from dataclasses import dataclass, field
from typing import Any

from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.shared.context_parts import ContextPartChunkLog, ProviderTokenUsage

TOKEN_BREAKDOWN_KEYS = (
    "prompt",
    "assistant_text",
    "thinking",
    "tool_call",
    "tool_result",
    "cached",
    "unknown",
)


@dataclass(frozen=True)
class AggregatedRunMetrics:
    tool_call_count: int = 0
    total_tokens: int | None = None
    token_breakdown: dict[str, int] = field(
        default_factory=lambda: {key: 0 for key in TOKEN_BREAKDOWN_KEYS}
    )
    total_cost_usd: float | None = None
    cost_observed: bool = False


def aggregate_run_metrics(
    events: list[RunContextEvent],
    *,
    summary: dict[str, Any],
) -> AggregatedRunMetrics:
    """Aggregate persisted event metrics without tokenizing rendered text."""
    breakdown = {key: 0 for key in TOKEN_BREAKDOWN_KEYS}
    provider_cost_total = 0.0
    provider_cost_observed = False

    for event in events:
        payload = event.parsed_payload()
        provider_cost = _add_token_counts(breakdown, payload)
        if provider_cost is not None:
            provider_cost_total += provider_cost
            provider_cost_observed = True

    total_tokens = sum(breakdown.values())
    summary_cost, summary_cost_observed = observed_cost_from_summary(summary)
    total_cost_usd: float | None
    cost_observed: bool
    if summary_cost_observed:
        total_cost_usd = summary_cost
        cost_observed = True
    elif provider_cost_observed:
        total_cost_usd = provider_cost_total
        cost_observed = True
    else:
        total_cost_usd = None
        cost_observed = False

    return AggregatedRunMetrics(
        tool_call_count=sum(1 for event in events if event.event_type == "tool_call"),
        total_tokens=total_tokens if total_tokens > 0 else None,
        token_breakdown=breakdown,
        total_cost_usd=total_cost_usd,
        cost_observed=cost_observed,
    )


def observed_cost_from_summary(summary: dict[str, Any]) -> tuple[float | None, bool]:
    """Return observed run cost, never treating historical default zero as observed."""
    nested = summary.get("cost")
    if isinstance(nested, dict) and nested.get("observed") is True:
        value = nested.get("total_cost_usd")
        return (_number(value), True) if _number(value) is not None else (None, False)

    if summary.get("cost_observed") is True:
        value = summary.get("total_cost_usd")
        return (_number(value), True) if _number(value) is not None else (None, False)

    fallback_value = _number(summary.get("total_cost_usd"))
    if fallback_value is not None and fallback_value != 0:
        return fallback_value, True

    return None, False


def _add_token_counts(
    breakdown: dict[str, int],
    payload: ContextPartChunkLog,
) -> float | None:
    usage = payload.provider_usage
    if usage is None:
        _add_local_token_ids(breakdown, payload)
        return None

    _add_provider_usage(breakdown, payload, usage)
    return usage.total_cost_usd


def _add_local_token_ids(
    breakdown: dict[str, int],
    payload: ContextPartChunkLog,
) -> None:
    if payload.token_ids is None:
        return
    count = len(payload.token_ids)
    if count == 0:
        return
    breakdown[_semantic_bucket(payload.part.part_kind)] += count


def _add_provider_usage(
    breakdown: dict[str, int],
    payload: ContextPartChunkLog,
    usage: ProviderTokenUsage,
) -> None:
    before = sum(breakdown.values())
    _add_if_present(breakdown, "prompt", usage.prompt_tokens)
    _add_if_present(breakdown, "cached", usage.cached_tokens)
    _add_if_present(breakdown, "thinking", usage.reasoning_tokens)
    _add_if_present(breakdown, "tool_call", usage.tool_call_tokens)
    _add_if_present(breakdown, "tool_result", usage.tool_result_tokens)
    _add_if_present(
        breakdown,
        _completion_bucket(payload.part.part_kind),
        usage.completion_tokens,
    )

    event_known_total = sum(breakdown.values()) - before
    if usage.total_tokens is not None and usage.total_tokens > event_known_total:
        breakdown["unknown"] += usage.total_tokens - event_known_total


def _semantic_bucket(part_kind: str) -> str:
    if part_kind in ("assistant_text", "thinking", "tool_call", "tool_result"):
        return part_kind
    if part_kind in ("system_prompt", "user_message"):
        return "prompt"
    return "unknown"


def _completion_bucket(part_kind: str) -> str:
    if part_kind == "thinking":
        return "thinking"
    if part_kind == "tool_call":
        return "tool_call"
    return "assistant_text"


def _add_if_present(breakdown: dict[str, int], key: str, value: int | None) -> None:
    if value is not None and value > 0:
        breakdown[key] += value


def _number(value: Any) -> float | None:  # slopcop: ignore[no-typing-any]
    if isinstance(value, int | float):
        return float(value)
    return None
