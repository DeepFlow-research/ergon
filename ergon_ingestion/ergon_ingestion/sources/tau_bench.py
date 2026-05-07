"""tau-bench source parser for full tool-call trajectories."""

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
from ergon_ingestion.reducers.tau_bench import default_reducers

Record = dict[str, object]


class TauBenchImporter:
    """Read local tau-bench JSON/JSONL trajectory exports."""

    info = ImporterInfo(
        slug="tau_bench",
        display_name="tau-bench",
        schema_fit_class="full-trace",
        supported_formats=["json", "jsonl"],
        export_claim="safe",
        paper_result_ids=["rq1", "rq2"],
        default_reducers=[
            "tau_bench.reward",
            "tau_bench.db_state",
            "tau_bench.sequence",
            "tau_bench.set",
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
        for idx, record in enumerate(iter_tau_bench_records(source.input_path), start=1):
            yield parse_tau_bench_record(record, fallback_id=f"row-{idx}")


def iter_tau_bench_records(path: Path) -> Iterator[Record]:
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


def parse_tau_bench_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    source_id = _source_run_id(record, fallback_id=fallback_id)
    domain = _string_field(record, "domain")
    task_id = _string_field(record, "task_id")
    final_state = record.get("final_state")

    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        )
    ]
    if isinstance(final_state, dict):
        resources.append(
            ParsedResource(
                name="final-state.json",
                kind="artifact",
                mime_type="application/json",
                payload=final_state,
            )
        )

    return ParsedRun(
        source_run_id=source_id,
        instance_key=source_id,
        description=f"Imported tau-bench trajectory {source_id}",
        schema_fit_class="full-trace",
        observed_fields={
            **record,
            "domain": domain,
            "task_id": task_id,
            "reward": record.get("reward"),
            "success": record.get("success"),
        },
        missing_fields=[
            "autonomy.user_turn_contribution",
            "environment.internal_state_transitions",
        ],
        annotations=[
            ParsedAnnotation(
                namespace="tau_bench.task",
                payload={"domain": domain, "task_id": task_id},
            ),
            ParsedAnnotation(
                namespace="tau_bench.outcome",
                payload={"reward": record.get("reward"), "success": record.get("success")},
            ),
        ],
        events=_events_from_messages(record),
        resources=resources,
        reducers=default_reducers(record),
    )


def _planned_runs(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return len(data)
    return 1


def _events_from_messages(record: Record) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    for message_index, message in enumerate(_messages(record)):
        role = str(message.get("role", "unknown"))
        if role == "tool":
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
                        "name": tool_call.get("name"),
                        "args": tool_call.get("args"),
                        "message_index": message_index,
                    },
                )
            )
    return events


def _source_run_id(record: Record, *, fallback_id: str) -> str:
    explicit = record.get("source_run_id") or record.get("run_id") or record.get("id")
    if explicit is not None:
        return str(explicit)
    domain = _string_field(record, "domain")
    task_id = _string_field(record, "task_id")
    if domain and task_id:
        return f"{domain}:{task_id}"
    return fallback_id


def _string_field(record: Record, key: str) -> str:
    value = record.get(key)
    return "" if value is None else str(value)


def _messages(record: Record) -> list[Record]:
    value = record.get("messages")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _tool_calls(message: Record) -> list[Record]:
    value = message.get("tool_calls")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
