"""Reducers for MAESTRO span-trace imports."""

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from ergon_ingestion.models import ParsedDrop, ParsedReducer

OUTCOME_FIELDS = ["attributes.run.outcome", "attributes.run.judgement"]
COORDINATION_FIELDS = [
    "span_id",
    "parent_span_id",
    "agent_name",
    "duration_ms",
    "duration",
    "status",
    "error",
    "token_count",
    "input_tokens",
    "output_tokens",
    "attributes.run.outcome",
    "attributes.run.judgement",
    "attributes.communication.messages",
]


def outcome_reducer(outcome: str | None, judgement: str | None) -> ParsedReducer:
    """Preserve source-level MAESTRO run outcome labels."""

    output = {
        key: value
        for key, value in {"outcome": outcome, "judgement": judgement}.items()
        if value is not None
    }
    return ParsedReducer(
        name="maestro.outcome",
        kind="original",
        output=output,
        implementation_ref="ergon_ingestion.reducers.maestro.outcome_reducer",
        fields_read=OUTCOME_FIELDS,
    )


def coordination_overhead_reducer(spans: Sequence[Mapping[str, Any]]) -> ParsedReducer:
    """Summarize span volume, token volume, duration, and observed status/error signals."""

    status_counts = Counter(str(span.get("status")) for span in spans if span.get("status"))
    token_count = sum(_span_tokens(span) for span in spans)
    duration_ms = sum(_duration_ms(span) for span in spans)
    errors = [span.get("error") for span in spans if span.get("error")]

    return ParsedReducer(
        name="maestro.coordination_overhead",
        kind="recovered",
        output={
            "span_count": len(spans),
            "token_count": token_count,
            "duration_ms": duration_ms,
            "status_counts": dict(status_counts),
            "error_count": len(errors),
        },
        implementation_ref="ergon_ingestion.reducers.maestro.coordination_overhead_reducer",
        fields_read=COORDINATION_FIELDS,
        aggregation={
            "group_by": ["run_id"],
            "span_count": "count(span_id)",
            "token_count": "sum(token_count, input_tokens, output_tokens)",
            "duration_ms": "sum(duration_ms or duration)",
            "status_counts": "count(status)",
        },
        drops=[
            ParsedDrop(
                loss_class="causal_attribution_unobserved",
                reason="coordination causality is not observed in MAESTRO span rows",
                affected_analysis="maestro.coordination_overhead",
            ),
            ParsedDrop(
                loss_class="failure_mechanism_unobserved",
                reason="direct failure mechanism is not observed in MAESTRO span rows",
                affected_analysis="maestro.coordination_overhead",
            ),
        ],
    )


def _span_tokens(span: Mapping[str, Any]) -> int:
    if span.get("token_count") is not None:
        return _int_or_zero(span["token_count"])
    return _int_or_zero(span.get("input_tokens")) + _int_or_zero(span.get("output_tokens"))


def _duration_ms(span: Mapping[str, Any]) -> int:
    if span.get("duration_ms") is not None:
        return _int_or_zero(span["duration_ms"])
    return _int_or_zero(span.get("duration"))


def _int_or_zero(value: Any) -> int:  # slopcop: ignore[no-typing-any]
    if value is None or value == "":
        return 0
    return int(value)
