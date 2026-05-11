"""Reducers for tau-bench trajectory records."""

from collections.abc import Iterable

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]


def reduce_reward(record: Record) -> ParsedReducer:
    """Preserve tau-bench's original scalar reward and success flag."""

    return ParsedReducer(
        name="tau_bench.reward",
        kind="original",
        output={"reward": record.get("reward"), "success": record.get("success")},
        implementation_ref="ergon_ingestion.reducers.tau_bench.reduce_reward",
        fields_read=["reward", "success"],
        drops=[_autonomy_drop()],
    )


def reduce_db_state(record: Record) -> ParsedReducer:
    """Expose final DB state for RQ2 state-based regrading."""

    return ParsedReducer(
        name="tau_bench.db_state",
        kind="regrade",
        output={"final_state": record.get("final_state")},
        implementation_ref="ergon_ingestion.reducers.tau_bench.reduce_db_state",
        fields_read=["final_state"],
        drops=[_environment_internals_drop()],
    )


def reduce_sequence(record: Record) -> ParsedReducer:
    """Recover ordered message/tool-call sequence features."""

    messages = _messages(record)
    return ParsedReducer(
        name="tau_bench.sequence",
        kind="recovered",
        output={
            "roles": [str(message.get("role", "")) for message in messages],
            "tool_names": _tool_names_in_order(messages),
            "tool_result_names": _tool_result_names_in_order(messages),
        },
        implementation_ref="ergon_ingestion.reducers.tau_bench.reduce_sequence",
        fields_read=["messages"],
        drops=[_autonomy_drop(), _environment_internals_drop()],
    )


def reduce_set(record: Record) -> ParsedReducer:
    """Recover set-style tool-use features without preserving multiplicity."""

    messages = _messages(record)
    return ParsedReducer(
        name="tau_bench.set",
        kind="recovered",
        output={
            "tool_names": sorted(set(_tool_names_in_order(messages))),
            "tool_result_names": sorted(set(_tool_result_names_in_order(messages))),
        },
        implementation_ref="ergon_ingestion.reducers.tau_bench.reduce_set",
        fields_read=["messages"],
        drops=[
            ParsedDrop(
                loss_class="sequence_information_loss",
                reason="set_reducer_discards_tool_order_and_multiplicity",
                dropped_field_path="messages.tool_calls.sequence",
                affected_analysis="rq2_sequence_vs_set_graders",
            ),
            _autonomy_drop(),
            _environment_internals_drop(),
        ],
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [
        reduce_reward(record),
        reduce_db_state(record),
        reduce_sequence(record),
        reduce_set(record),
    ]


def _messages(record: Record) -> list[Record]:
    value = record.get("messages")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _tool_names_in_order(messages: Iterable[Record]) -> list[str]:
    names: list[str] = []
    for message in messages:
        for tool_call in _tool_calls(message):
            name = tool_call.get("name")
            if name is not None:
                names.append(str(name))
    return names


def _tool_result_names_in_order(messages: Iterable[Record]) -> list[str]:
    names: list[str] = []
    for message in messages:
        if message.get("role") == "tool" and message.get("name") is not None:
            names.append(str(message["name"]))
    return names


def _tool_calls(message: Record) -> list[Record]:
    value = message.get("tool_calls")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _autonomy_drop() -> ParsedDrop:
    return ParsedDrop(
        loss_class="unavailable_source_field",
        reason="autonomy_and_user_turn_attribution_not_separable_from_trace",
        dropped_field_path="autonomy.user_turn_contribution",
        affected_analysis="rq1_user_contribution_refusal_process_features",
        declaration_kind="source_missing",
    )


def _environment_internals_drop() -> ParsedDrop:
    return ParsedDrop(
        loss_class="unavailable_source_field",
        reason="environment_internals_unavailable_beyond_final_state",
        dropped_field_path="environment.internal_state_transitions",
        affected_analysis="rq2_db_state_vs_sequence_set_graders",
        declaration_kind="source_missing",
    )
