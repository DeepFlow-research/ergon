"""Reducers for OpenHands / SWE-rebench full-trace software-engineering runs."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

RESOLVED_FIELDS = ["resolved", "eval_status", "pass", "test_status"]
PATCH_TRACE_FIELDS = [
    "patch",
    "messages",
    "actions",
    "tool_calls",
    "resolved",
    "eval_status",
]


def reduce_resolved(record: Record) -> ParsedReducer:
    """Preserve source outcome labels without claiming to rerun the evaluator."""

    return ParsedReducer(
        name="openhands_swe_rebench.resolved",
        kind="original",
        output={
            "resolved": record.get("resolved"),
            "eval_status": record.get("eval_status"),
            "pass": record.get("pass"),
            "test_status": record.get("test_status"),
        },
        implementation_ref="ergon_ingestion.reducers.openhands_swe_rebench.reduce_resolved",
        fields_read=RESOLVED_FIELDS,
        drops=[_environment_drop()],
    )


def reduce_patch_trace(record: Record) -> ParsedReducer:
    """Recover compact patch and process features from preserved trace fields."""

    patch = _patch(record)
    messages = _messages(record)
    actions = _actions(record)
    tool_calls = _all_tool_calls(record)

    return ParsedReducer(
        name="openhands_swe_rebench.patch_trace",
        kind="recovered",
        output={
            "resolved": record.get("resolved"),
            "eval_status": record.get("eval_status"),
            "patch_line_count": len(patch.splitlines()) if patch else 0,
            "patch_added_lines": _patch_added_lines(patch),
            "patch_removed_lines": _patch_removed_lines(patch),
            "message_count": len(messages),
            "action_count": len(actions),
            "tool_call_count": len(tool_calls),
            "tool_names": _tool_names(tool_calls),
            "touched_files": _touched_files(record),
        },
        implementation_ref="ergon_ingestion.reducers.openhands_swe_rebench.reduce_patch_trace",
        fields_read=PATCH_TRACE_FIELDS,
        drops=[_tests_drop()],
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [reduce_resolved(record), reduce_patch_trace(record)]


def _patch(record: Record) -> str:
    value = record.get("patch") or record.get("diff")
    return "" if value is None else str(value)


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


def _all_tool_calls(record: Record) -> list[Record]:
    calls: list[Record] = []
    top_level = record.get("tool_calls")
    if isinstance(top_level, list):
        calls.extend(item for item in top_level if isinstance(item, dict))
    for message in _messages(record):
        value = message.get("tool_calls")
        if isinstance(value, list):
            calls.extend(item for item in value if isinstance(item, dict))
    return calls


def _tool_names(tool_calls: list[Record]) -> list[str]:
    names = []
    for call in tool_calls:
        name = call.get("name") or call.get("tool") or call.get("tool_name")
        if name is not None:
            names.append(str(name))
    return sorted(set(names))


def _touched_files(record: Record) -> list[str]:
    files = []
    for action in _actions(record):
        path = action.get("path") or action.get("file") or action.get("filename")
        if path is not None:
            files.append(str(path))
    files.extend(_patch_files(_patch(record)))
    return sorted(set(files))


def _patch_files(patch: str) -> list[str]:
    files = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                files.append(parts[3].removeprefix("b/"))
    return files


def _patch_added_lines(patch: str) -> int:
    return sum(
        1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")
    )


def _patch_removed_lines(patch: str) -> int:
    return sum(
        1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---")
    )


def _environment_drop() -> ParsedDrop:
    return ParsedDrop(
        loss_class="unavailable_source_field",
        reason="evaluator_environment_and_tests_not_reproduced",
        dropped_field_path="evaluation.environment",
        affected_analysis="openhands_swe_rebench.resolved",
        declaration_kind="source_missing",
    )


def _tests_drop() -> ParsedDrop:
    return ParsedDrop(
        loss_class="unavailable_source_field",
        reason="evaluator_environment_and_tests_not_reproduced",
        dropped_field_path="evaluation.tests",
        affected_analysis="openhands_swe_rebench.patch_trace",
        declaration_kind="source_missing",
    )
