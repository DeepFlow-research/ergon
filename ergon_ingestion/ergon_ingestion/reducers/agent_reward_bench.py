"""Reducers for Agent Reward Bench annotated trajectory records."""

from collections.abc import Iterable

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

REWARD_LABEL_FIELDS = [
    "reward_score",
    "preference_label",
    "judge",
    "annotator",
    "annotation_metadata",
]
PROCESS_TRACE_FIELDS = [
    "messages",
    "actions",
    "tool_calls",
    "process_trace",
    "reward_score",
    "preference_label",
]


def reward_label_reducer(record: Record) -> ParsedReducer:
    """Expose source reward/preference labels with available annotation provenance."""

    return ParsedReducer(
        name="agent_reward_bench.reward_label",
        kind="original",
        output={
            "reward_score": record.get("reward_score"),
            "preference_label": record.get("preference_label"),
            "judge": record.get("judge"),
            "annotator": record.get("annotator"),
            "annotation_metadata": record.get("annotation_metadata"),
        },
        implementation_ref="ergon_ingestion.reducers.agent_reward_bench.reward_label_reducer",
        fields_read=REWARD_LABEL_FIELDS,
        drops=_annotation_provenance_caveats(record, "agent_reward_bench.reward_label"),
    )


def process_trace_reducer(record: Record) -> ParsedReducer:
    """Recover compact process features while retaining reward/preference context."""

    messages = _messages(record)
    actions = _actions(record)
    tool_calls = _tool_calls(record, messages)
    return ParsedReducer(
        name="agent_reward_bench.process_trace",
        kind="recovered",
        output={
            "message_count": len(messages),
            "action_count": len(actions),
            "tool_call_count": len(tool_calls),
            "tool_names": _tool_names(tool_calls),
            "process_trace": _process_trace(record),
            "reward_score": record.get("reward_score"),
            "preference_label": record.get("preference_label"),
        },
        implementation_ref="ergon_ingestion.reducers.agent_reward_bench.process_trace_reducer",
        fields_read=PROCESS_TRACE_FIELDS,
        drops=_annotation_provenance_caveats(record, "agent_reward_bench.process_trace"),
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [reward_label_reducer(record), process_trace_reducer(record)]


def _messages(record: Record) -> list[Record]:
    value = record.get("messages")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _actions(record: Record) -> list[Record]:
    value = record.get("actions")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _tool_calls(record: Record, messages: Iterable[Record]) -> list[Record]:
    explicit = record.get("tool_calls")
    if isinstance(explicit, list):
        return [item for item in explicit if isinstance(item, dict)]

    calls: list[Record] = []
    for message in messages:
        value = message.get("tool_calls")
        if isinstance(value, list):
            calls.extend(item for item in value if isinstance(item, dict))
    return calls


def _tool_names(tool_calls: Iterable[Record]) -> list[str]:
    names: list[str] = []
    for tool_call in tool_calls:
        name = tool_call.get("name")
        if name is not None:
            names.append(str(name))
    return names


def _process_trace(record: Record) -> list[object]:
    value = record.get("process_trace")
    if not isinstance(value, list):
        return []
    return value


def _annotation_provenance_caveats(record: Record, affected_analysis: str) -> list[ParsedDrop]:
    drops: list[ParsedDrop] = []
    if _missing(record.get("independent_rejudge")):
        drops.append(
            ParsedDrop(
                loss_class="annotation_provenance_limit",
                reason="missing_independent_rejudge_provenance",
                dropped_field_path="independent_rejudge",
                affected_analysis=affected_analysis,
                declaration_kind="source_missing",
            )
        )
    if _missing(record.get("inter_annotator_agreement")):
        drops.append(
            ParsedDrop(
                loss_class="annotation_provenance_limit",
                reason="missing_inter_annotator_provenance",
                dropped_field_path="inter_annotator_agreement",
                affected_analysis=affected_analysis,
                declaration_kind="source_missing",
            )
        )
    return drops


def _missing(value: object) -> bool:
    return value is None or value == "" or value == []
