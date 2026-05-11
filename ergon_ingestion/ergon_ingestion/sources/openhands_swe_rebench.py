"""OpenHands / SWE-rebench source parser for full-trace SWE trajectories."""

import json
from collections.abc import Iterator
from pathlib import Path

from ergon_ingestion.models import (
    ImporterInfo,
    ImportSource,
    ParsedAnnotation,
    ParsedEvent,
    ParsedResource,
    ParsedRun,
    ValidationReport,
)
from ergon_ingestion.reducers.openhands_swe_rebench import default_reducers

Record = dict[str, object]


class OpenHandsSweRebenchImporter:
    """Read local OpenHands / SWE-rebench JSON/JSONL trajectory exports."""

    info = ImporterInfo(
        slug="openhands_swe_rebench",
        display_name="OpenHands / SWE-rebench",
        schema_fit_class="full-trace",
        supported_formats=["json", "jsonl"],
        export_claim="safe",
        default_reducers=[
            "openhands_swe_rebench.resolved",
            "openhands_swe_rebench.patch_trace",
        ],
    )

    def validate(self, source: ImportSource) -> ValidationReport:
        if not source.input_path.exists():
            return ValidationReport(
                dataset=self.info.slug,
                input_path=source.input_path,
                ok=False,
                errors=[f"input path does not exist: {source.input_path}"],
            )
        return ValidationReport(
            dataset=self.info.slug,
            input_path=source.input_path,
            ok=True,
            planned_runs=_planned_runs(source.input_path),
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        for idx, record in enumerate(
            iter_openhands_swe_rebench_records(source.input_path), start=1
        ):
            yield parse_openhands_swe_rebench_record(record, fallback_id=f"row-{idx}")


def iter_openhands_swe_rebench_records(path: Path) -> Iterator[Record]:
    if path.suffix == ".jsonl":
        for line in path.read_text().splitlines():
            if line.strip():
                yield _as_record(json.loads(line))
        return

    data = json.loads(path.read_text())
    if isinstance(data, list):
        for item in data:
            yield _as_record(item)
        return
    yield _as_record(data)


def parse_openhands_swe_rebench_record(
    record: Record,
    *,
    fallback_id: str = "row-1",
) -> ParsedRun:
    source_id = _source_run_id(record, fallback_id=fallback_id)
    issue = _issue(record)
    patch = _patch(record)

    return ParsedRun(
        source_run_id=source_id,
        instance_key=source_id,
        description=f"Imported OpenHands / SWE-rebench trajectory {source_id}",
        schema_fit_class="full-trace",
        observed_fields={
            "instance_id": record.get("instance_id"),
            "task_id": record.get("task_id"),
            "repo": record.get("repo"),
            "base_commit": record.get("base_commit"),
            "issue": issue,
            "messages": _messages(record),
            "actions": _actions(record),
            "tool_calls": _top_level_tool_calls(record),
            "patch": patch,
            "eval_status": record.get("eval_status"),
            "resolved": record.get("resolved"),
            "pass": record.get("pass"),
            "test_status": record.get("test_status"),
        },
        missing_fields=[
            "evaluation.environment",
            "evaluation.tests",
            "independent_evaluator_regrade",
        ],
        annotations=[
            ParsedAnnotation(
                namespace="openhands_swe_rebench.task",
                payload={
                    "instance_id": record.get("instance_id"),
                    "task_id": record.get("task_id"),
                    "repo": record.get("repo"),
                    "base_commit": record.get("base_commit"),
                    "issue": issue,
                },
            ),
            ParsedAnnotation(
                namespace="openhands_swe_rebench.outcome",
                payload={
                    "resolved": record.get("resolved"),
                    "eval_status": record.get("eval_status"),
                    "pass": record.get("pass"),
                    "test_status": record.get("test_status"),
                },
            ),
        ],
        events=_events_from_trace(record),
        resources=_resources(record, patch),
        reducers=default_reducers(record),
    )


def _planned_runs(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return len(data)
    return 1


def _events_from_trace(record: Record) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    tool_result_messages: list[tuple[int, Record]] = []
    for message_index, message in enumerate(_messages(record)):
        role = str(message.get("role", "unknown"))
        if role == "tool":
            tool_result_messages.append((message_index, message))
            continue

        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type=f"message.{role}",
                payload={key: value for key, value in message.items() if key != "tool_calls"},
            )
        )
        for tool_call in _tool_calls(message):
            events.append(
                ParsedEvent(
                    sequence=len(events),
                    event_type="tool_call",
                    payload={
                        "id": tool_call.get("id"),
                        "name": _tool_name(tool_call),
                        "args": _tool_args(tool_call),
                        "message_index": message_index,
                    },
                )
            )

    for action_index, action in enumerate(_actions(record)):
        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type="action",
                payload={
                    "action_index": action_index,
                    "action": action.get("action") or action.get("type"),
                    "path": action.get("path") or action.get("file") or action.get("filename"),
                    "tool": action.get("tool"),
                },
            )
        )

    for message_index, message in tool_result_messages:
        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type="tool_result",
                payload={
                    "tool_call_id": message.get("tool_call_id"),
                    "name": message.get("name"),
                    "content": message.get("content"),
                    "message_index": message_index,
                },
            )
        )

    for tool_call in _top_level_tool_calls(record):
        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type="tool_call",
                payload={
                    "id": tool_call.get("id"),
                    "name": _tool_name(tool_call),
                    "args": _tool_args(tool_call),
                    "message_index": None,
                },
            )
        )
    return events


def _resources(record: Record, patch: str) -> list[ParsedResource]:
    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        )
    ]
    if patch:
        resources.append(
            ParsedResource(
                name="patch.diff",
                kind="output",
                mime_type="text/x-diff",
                payload=patch,
            )
        )
    if _messages(record) or _actions(record) or _top_level_tool_calls(record):
        resources.append(
            ParsedResource(
                name="trace.json",
                kind="artifact",
                mime_type="application/json",
                payload={
                    "messages": _messages(record),
                    "actions": _actions(record),
                    "tool_calls": _top_level_tool_calls(record),
                },
            )
        )
    return resources


def _source_run_id(record: Record, *, fallback_id: str) -> str:
    explicit = record.get("instance_id") or record.get("task_id") or record.get("source_run_id")
    if explicit is not None:
        return str(explicit)
    return fallback_id


def _issue(record: Record) -> str:
    value = record.get("issue")
    if value is None:
        value = record.get("issue_text")
    return "" if value is None else str(value)


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


def _top_level_tool_calls(record: Record) -> list[Record]:
    value = record.get("tool_calls")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _tool_calls(message: Record) -> list[Record]:
    value = message.get("tool_calls")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _tool_name(tool_call: Record) -> object:
    return tool_call.get("name") or tool_call.get("tool") or tool_call.get("tool_name")


def _tool_args(tool_call: Record) -> object:
    if "args" in tool_call:
        return tool_call.get("args")
    return tool_call.get("arguments")


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
