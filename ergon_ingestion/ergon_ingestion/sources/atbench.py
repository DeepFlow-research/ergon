"""ATBench source parser for conditional full-trace trajectory rows."""

import csv
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
from ergon_ingestion.reducers.atbench import default_reducers

Record = dict[str, object]


class AtBenchImporter:
    """Read local ATBench JSON, JSONL, and CSV trajectory exports."""

    info = ImporterInfo(
        slug="atbench",
        display_name="ATBench",
        schema_fit_class="full-trace",
        supported_formats=["json", "jsonl", "csv"],
        export_claim="conditional",
        default_reducers=["atbench.outcome", "atbench.trajectory_summary"],
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
        for idx, record in enumerate(iter_atbench_records(source.input_path), start=1):
            yield parse_atbench_record(record, fallback_id=f"row-{idx}")


def iter_atbench_records(path: Path) -> Iterator[Record]:
    if path.suffix == ".csv":
        with path.open(newline="") as csv_file:
            for row in csv.DictReader(csv_file):
                yield _coerce_csv_record(row)
        return

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


def parse_atbench_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    source_id = _source_run_id(record, fallback_id=fallback_id)
    task_id = _string_field(record, "task_id")
    steps = _records(record.get("steps"))
    actions = _records(record.get("actions"))
    tool_calls = _records(record.get("tool_calls"))

    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        )
    ]
    resources.extend(_trace_resources(steps, actions, tool_calls))

    return ParsedRun(
        source_run_id=source_id,
        instance_key=task_id or source_id,
        description=f"Imported ATBench trajectory {source_id}",
        schema_fit_class="full-trace",
        observed_fields={
            "trajectory_id": record.get("trajectory_id"),
            "task_id": task_id,
            "steps": steps,
            "actions": actions,
            "tool_calls": tool_calls,
            "score": record.get("score"),
            "success": record.get("success"),
            "outcome": record.get("outcome"),
            "task_metadata": _task_metadata(record),
        },
        missing_fields=_missing_fields(record),
        annotations=[
            ParsedAnnotation(
                namespace="atbench.task",
                payload={
                    "trajectory_id": record.get("trajectory_id"),
                    "task_id": task_id,
                    "task_metadata": _task_metadata(record),
                },
            ),
            ParsedAnnotation(
                namespace="atbench.outcome",
                payload={
                    "score": record.get("score"),
                    "success": record.get("success"),
                    "outcome": record.get("outcome"),
                },
            ),
        ],
        events=_events_from_trace(steps, actions, tool_calls),
        resources=resources,
        reducers=default_reducers(record),
    )


def _planned_runs(path: Path) -> int:
    if path.suffix == ".csv":
        with path.open(newline="") as csv_file:
            return sum(1 for _ in csv.DictReader(csv_file))
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return len(data)
    return 1


def _events_from_trace(
    steps: list[Record],
    actions: list[Record],
    tool_calls: list[Record],
) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    for step_index, step in enumerate(steps):
        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type="step",
                payload={
                    "step_index": step_index,
                    "content": _first_value(step, ["content", "summary", "text"]),
                    "status": step.get("status"),
                },
            )
        )
    for action_index, action in enumerate(actions):
        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type="action",
                payload={
                    "action_index": action_index,
                    "name": _first_value(action, ["name", "action", "type"]),
                    "arguments": _first_value(action, ["arguments", "args"]),
                    "result": action.get("result"),
                    "status": action.get("status"),
                },
            )
        )
    for tool_call_index, tool_call in enumerate(tool_calls):
        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type="tool_call",
                payload={
                    "tool_call_index": tool_call_index,
                    "id": tool_call.get("id"),
                    "name": _first_value(tool_call, ["name", "tool_name", "tool"]),
                    "arguments": _first_value(tool_call, ["arguments", "args"]),
                    "result": tool_call.get("result"),
                    "status": tool_call.get("status"),
                },
            )
        )
    return events


def _trace_resources(
    steps: list[Record],
    actions: list[Record],
    tool_calls: list[Record],
) -> list[ParsedResource]:
    resources: list[ParsedResource] = []
    if steps:
        resources.append(
            ParsedResource(
                name="steps.json",
                kind="artifact",
                mime_type="application/json",
                payload={"steps": steps},
            )
        )
    if actions:
        resources.append(
            ParsedResource(
                name="actions.json",
                kind="artifact",
                mime_type="application/json",
                payload={"actions": actions},
            )
        )
    if tool_calls:
        resources.append(
            ParsedResource(
                name="tool-calls.json",
                kind="artifact",
                mime_type="application/json",
                payload={"tool_calls": tool_calls},
            )
        )
    return resources


def _missing_fields(record: Record) -> list[str]:
    missing = ["replay"]
    if not _has_full_trace(record):
        missing.append("steps/actions/tool_calls")
    if not _has_evaluator_metadata(record):
        missing.append("evaluator_metadata")
    return missing


def _source_run_id(record: Record, *, fallback_id: str) -> str:
    explicit = (
        record.get("trajectory_id")
        or record.get("source_run_id")
        or record.get("run_id")
        or record.get("id")
    )
    if explicit is not None:
        return str(explicit)
    task_id = _string_field(record, "task_id")
    return task_id or fallback_id


def _coerce_csv_record(row: dict[str, str | None]) -> Record:
    return {
        str(key): _coerce_csv_value(key, value)
        for key, value in row.items()
        if key is not None and value not in (None, "")
    }


def _coerce_csv_value(key: str, value: str | None) -> object:
    if value is None:
        return None
    if key in {
        "steps",
        "actions",
        "tool_calls",
        "task_metadata",
        "evaluator",
        "evaluator_metadata",
    }:
        return _json_or_string(value)
    if key == "score":
        return float(value)
    if key == "success":
        return value.lower() in {"1", "true", "yes", "y"}
    return value


def _json_or_string(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _records(value: object) -> list[Record]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _task_metadata(record: Record) -> dict[str, object]:
    value = record.get("task_metadata")
    return value if isinstance(value, dict) else {}


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


def _first_value(record: Record, keys: list[str]) -> object:
    for key in keys:
        if key in record:
            return record.get(key)
    return None


def _string_field(record: Record, key: str) -> str:
    value = record.get(key)
    return "" if value is None else str(value)


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
