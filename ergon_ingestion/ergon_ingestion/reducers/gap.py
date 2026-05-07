"""Reducer helpers for GAP row-record imports."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

TEXT_SAFETY_FIELDS = ["t_safe", "refusal_strength"]
TOOL_CALL_SAFETY_FIELDS = [
    "tc_safe",
    "gap",
    "forbidden_calls",
    "tool_call_count",
    "forbidden_tool_call_count",
]


def text_safety_reducer(row: dict[str, object]) -> ParsedReducer:
    return ParsedReducer(
        name="gap.text_safety",
        kind="original",
        output={
            "safe": row.get("t_safe"),
            "refusal_strength": row.get("refusal_strength"),
        },
        implementation_ref="ergon_ingestion.reducers.gap.text_safety_reducer",
        fields_read=TEXT_SAFETY_FIELDS,
        drops=[
            ParsedDrop(
                loss_class="channel_excluded",
                reason="text_safety reducer intentionally excludes recovered tool-call channel",
                dropped_field_path="tool_channel_transcript",
                affected_analysis="gap.text_safety",
            )
        ],
    )


def tool_call_safety_reducer(row: dict[str, object]) -> ParsedReducer:
    return ParsedReducer(
        name="gap.tool_call_safety",
        kind="recovered",
        output={
            "safe": row.get("tc_safe"),
            "gap": row.get("gap"),
            "forbidden_calls": row.get("forbidden_calls"),
            "tool_call_count": row.get("tool_call_count"),
            "forbidden_tool_call_count": row.get("forbidden_tool_call_count"),
        },
        implementation_ref="ergon_ingestion.reducers.gap.tool_call_safety_reducer",
        fields_read=TOOL_CALL_SAFETY_FIELDS,
        drops=[
            ParsedDrop(
                loss_class="unavailable_source_field",
                reason="source row preserves labels and counts but not the full tool transcript",
                dropped_field_path="tool_channel_transcript",
                affected_analysis="gap.tool_call_safety",
                declaration_kind="source_missing",
            )
        ],
    )
