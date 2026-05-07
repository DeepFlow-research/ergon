"""Reducers for ATBench conditional trace and row-summary records."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

OUTCOME_FIELDS = ["outcome", "success", "score", "evaluator", "evaluator_metadata"]
TRAJECTORY_FIELDS = ["steps", "actions", "tool_calls", "outcome", "success", "score"]


def reduce_outcome(record: Record) -> ParsedReducer:
    """Preserve ATBench's source outcome labels without regrading."""

    return ParsedReducer(
        name="atbench.outcome",
        kind="original",
        output={
            "outcome": record.get("outcome"),
            "success": record.get("success"),
            "score": record.get("score"),
            "evaluator_metadata_present": _has_evaluator_metadata(record),
        },
        implementation_ref="ergon_ingestion.reducers.atbench.reduce_outcome",
        fields_read=OUTCOME_FIELDS,
        drops=[] if _has_evaluator_metadata(record) else [_evaluator_metadata_drop()],
    )


def reduce_trajectory_summary(record: Record) -> ParsedReducer:
    """Recover compact ordered summaries from available trace fields."""

    steps = _records(record.get("steps"))
    actions = _records(record.get("actions"))
    tool_calls = _records(record.get("tool_calls"))
    drops = [_replay_drop()]
    if not _has_full_trace(record):
        drops.append(_missing_full_trace_drop())

    return ParsedReducer(
        name="atbench.trajectory_summary",
        kind="recovered",
        output={
            "step_summaries": [_step_summary(step) for step in steps],
            "action_summaries": [_named_summary(action) for action in actions],
            "tool_call_summaries": [_named_summary(tool_call) for tool_call in tool_calls],
            "step_count": len(steps),
            "action_count": len(actions),
            "tool_call_count": len(tool_calls),
            "has_full_trace": _has_full_trace(record),
            "outcome": record.get("outcome"),
            "success": record.get("success"),
            "score": record.get("score"),
        },
        implementation_ref="ergon_ingestion.reducers.atbench.reduce_trajectory_summary",
        fields_read=TRAJECTORY_FIELDS,
        drops=drops,
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [reduce_outcome(record), reduce_trajectory_summary(record)]


def _records(value: object) -> list[Record]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _has_full_trace(record: Record) -> bool:
    return bool(
        _records(record.get("steps"))
        or _records(record.get("actions"))
        or _records(record.get("tool_calls"))
    )


def _has_evaluator_metadata(record: Record) -> bool:
    return isinstance(record.get("evaluator"), dict) or isinstance(
        record.get("evaluator_metadata"), dict
    )


def _step_summary(step: Record) -> str:
    for key in ("content", "summary", "text", "action", "name"):
        value = step.get(key)
        if value is not None:
            return str(value)
    return ""


def _named_summary(record: Record) -> str:
    for key in ("name", "tool_name", "action", "type"):
        value = record.get(key)
        if value is not None:
            return str(value)
    return ""


def _missing_full_trace_drop() -> ParsedDrop:
    return ParsedDrop(
        loss_class="unavailable_source_field",
        reason="row_summary_missing_full_trace_detail",
        dropped_field_path="steps/actions/tool_calls",
        affected_analysis="atbench.trajectory_summary",
        declaration_kind="source_missing",
    )


def _replay_drop() -> ParsedDrop:
    return ParsedDrop(
        loss_class="unavailable_source_field",
        reason="source_replay_metadata_unavailable",
        dropped_field_path="replay",
        affected_analysis="atbench.trajectory_summary",
        declaration_kind="source_missing",
    )


def _evaluator_metadata_drop() -> ParsedDrop:
    return ParsedDrop(
        loss_class="unavailable_source_field",
        reason="source_evaluator_metadata_unavailable",
        dropped_field_path="evaluator_metadata",
        affected_analysis="atbench.outcome",
        declaration_kind="source_missing",
    )
