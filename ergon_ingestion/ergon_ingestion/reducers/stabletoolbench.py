"""Reducers for StableToolBench full-trace tool trajectories."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

WIN_FIELDS = ["is_solved", "win", "pass", "evaluator.status", "evaluator_statuses"]
TOOL_PATH_FIELDS = [
    "answer_steps.tool",
    "answer_steps.tool_name",
    "answer_steps.name",
    "answer_steps.arguments",
    "answer_steps.args",
    "answer_steps.response",
    "answer_steps.status",
    "is_solved",
    "win",
]


def reduce_win(record: Record) -> ParsedReducer:
    """Preserve StableToolBench's source outcome labels without regrading."""

    return ParsedReducer(
        name="stabletoolbench.win",
        kind="original",
        output={
            "win": _win_value(record),
            "is_solved": record.get("is_solved"),
            "pass": record.get("pass"),
            "evaluator_statuses": _evaluator_statuses(record),
        },
        implementation_ref="ergon_ingestion.reducers.stabletoolbench.reduce_win",
        fields_read=WIN_FIELDS,
        drops=[_evaluator_trust_drop()],
    )


def reduce_tool_path(record: Record) -> ParsedReducer:
    """Recover successful-path variation features from ordered answer steps."""

    tool_steps = _tool_steps(record)
    drops = [_evaluator_trust_drop()]
    malformed_count = _malformed_answer_step_count(record)
    if malformed_count:
        drops.append(_malformed_answer_step_drop(malformed_count))

    return ParsedReducer(
        name="stabletoolbench.tool_path",
        kind="recovered",
        output={
            "is_successful": _is_successful(record),
            "tool_path": [step["tool_name"] for step in tool_steps],
            "tool_count": len(tool_steps),
            "unique_tool_names": sorted({step["tool_name"] for step in tool_steps}),
            "tool_argument_keys": [_argument_keys(step["record"]) for step in tool_steps],
            "response_count": sum(1 for step in tool_steps if _has_response(step["record"])),
            "malformed_answer_step_count": malformed_count,
        },
        implementation_ref="ergon_ingestion.reducers.stabletoolbench.reduce_tool_path",
        fields_read=TOOL_PATH_FIELDS,
        drops=drops,
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [reduce_win(record), reduce_tool_path(record)]


def _tool_steps(record: Record) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []
    answer_steps = record.get("answer_steps")
    if not isinstance(answer_steps, list):
        return steps
    for item in answer_steps:
        if not isinstance(item, dict):
            continue
        tool_name = _tool_name(item)
        if tool_name is None:
            continue
        steps.append({"tool_name": tool_name, "record": item})
    return steps


def _malformed_answer_step_count(record: Record) -> int:
    answer_steps = record.get("answer_steps")
    if not isinstance(answer_steps, list):
        return 0
    count = 0
    for item in answer_steps:
        if not isinstance(item, dict) or _tool_name(item) is None:
            count += 1
    return count


def _tool_name(step: Record) -> str | None:
    value = step.get("tool") or step.get("tool_name") or step.get("name")
    if value is None:
        return None
    return str(value)


def _argument_keys(step: Record) -> list[str]:
    arguments = step.get("arguments")
    if arguments is None:
        arguments = step.get("args")
    if not isinstance(arguments, dict):
        return []
    return sorted(str(key) for key in arguments)


def _has_response(step: Record) -> bool:
    return "response" in step and step.get("response") is not None


def _is_successful(record: Record) -> bool | None:
    for key in ("is_solved", "win", "pass"):
        value = record.get(key)
        if isinstance(value, bool):
            return value
    return None


def _win_value(record: Record) -> object:
    if "win" in record:
        return record.get("win")
    return record.get("pass")


def _evaluator_statuses(record: Record) -> list[str]:
    explicit = record.get("evaluator_statuses")
    if isinstance(explicit, list):
        return [str(status) for status in explicit]

    evaluator = record.get("evaluator")
    if not isinstance(evaluator, dict):
        return []

    statuses = evaluator.get("statuses")
    if isinstance(statuses, list):
        return [str(status) for status in statuses]

    status = evaluator.get("status")
    return [] if status is None else [str(status)]


def _evaluator_trust_drop() -> ParsedDrop:
    return ParsedDrop(
        loss_class="source_evaluator_trust",
        reason="trusts_source_evaluator_statuses_without_regrading",
        dropped_field_path="evaluator",
        affected_analysis="stabletoolbench.win",
        declaration_kind="author_declared",
    )


def _malformed_answer_step_drop(count: int) -> ParsedDrop:
    return ParsedDrop(
        loss_class="malformed_source_member",
        reason="skipped_malformed_answer_step_members",
        dropped_field_path="answer_steps[]",
        affected_analysis="stabletoolbench.tool_path",
        declaration_kind="source_malformed",
        evidence={"count": count},
    )
