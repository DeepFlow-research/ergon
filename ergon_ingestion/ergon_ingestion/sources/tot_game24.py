"""Tree-of-Thought Game24 search trace importer."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ergon_ingestion.models import (
    ImporterInfo,
    ImportSource,
    ParsedAnnotation,
    ParsedEvent,
    ParsedResource,
    ParsedRun,
    ValidationReport,
)
from ergon_ingestion.reducers.tot import (
    game24_final_answer,
    game24_value_trace,
    missing_game24_fields,
)


class TotGame24Importer:
    """Parse Tree-of-Thought Game24 JSON search traces."""

    info = ImporterInfo(
        slug="tot_game24",
        display_name="Tree-of-Thought Game24 search traces",
        schema_fit_class="full-trace",
        supported_formats=["json"],
        export_claim="safe",
        paper_result_ids=["rq1.tot_game24.final_answer", "rq1.tot_game24.value_trace"],
        default_reducers=["tot.game24_final_answer", "tot.game24_value_trace"],
    )

    def validate(self, source: ImportSource) -> ValidationReport:
        if not source.input_path.exists():
            return ValidationReport(
                dataset=self.info.slug,
                input_path=source.input_path,
                ok=False,
                errors=[f"input path does not exist: {source.input_path}"],
            )
        try:
            planned_runs = len(_load_trace_records(source.input_path))
        except (OSError, ValueError, TypeError) as exc:
            return ValidationReport(
                dataset=self.info.slug,
                input_path=source.input_path,
                ok=False,
                errors=[f"could not parse ToT Game24 traces: {exc}"],
            )
        return ValidationReport(
            dataset=self.info.slug,
            input_path=source.input_path,
            ok=True,
            planned_runs=planned_runs,
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise ValueError("; ".join(report.errors))
        for record in _load_trace_records(source.input_path):
            yield parsed_run_from_trace(record)


def parsed_run_from_trace(record: dict[str, Any]) -> ParsedRun:
    puzzle_id = str(record["puzzle_id"])
    source_run_id = _source_run_id(record, puzzle_id)
    return ParsedRun(
        source_run_id=source_run_id,
        instance_key=puzzle_id,
        description=f"Tree-of-Thought Game24 trace {source_run_id}",
        schema_fit_class="full-trace",
        observed_fields=record,
        missing_fields=missing_game24_fields(record),
        annotations=[
            ParsedAnnotation(
                namespace="tot.game24.trace_identity",
                payload={"puzzle_id": puzzle_id, "source_run_id": source_run_id},
            ),
            ParsedAnnotation(
                namespace="tot.game24.puzzle",
                payload={"numbers": record.get("numbers")},
            ),
        ],
        events=_events_from_trace(record, puzzle_id=puzzle_id),
        resources=[
            ParsedResource(
                name="tot-game24-trace.json",
                kind="artifact",
                mime_type="application/json",
                payload=record,
            )
        ],
        reducers=[game24_final_answer(record), game24_value_trace(record)],
    )


def _load_trace_records(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if isinstance(data, dict) and isinstance(data.get("traces"), list):
        records = data["traces"]
    elif isinstance(data, dict) and isinstance(data.get("logs"), list):
        records = data["logs"]
    elif isinstance(data, list):
        records = data
    else:
        records = [data]
    return [_as_record(record) for record in records]


def _as_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("ToT Game24 trace records must be JSON objects")
    if "puzzle_id" not in value or "numbers" not in value:
        raise ValueError("ToT Game24 trace records require puzzle_id and numbers")
    return value


def _events_from_trace(record: dict[str, Any], *, puzzle_id: str) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    for step in _list(record.get("steps")):
        events.append(_event(events, "tot.game24.step", _payload(step, key="step"), puzzle_id))
    for action in _list(record.get("actions")):
        events.append(
            _event(events, "tot.game24.action", _payload(action, key="action"), puzzle_id)
        )
    for value in _list(record.get("values")):
        events.append(_event(events, "tot.game24.value", _payload(value, key="value"), puzzle_id))
    for info in _infos(record):
        events.append(_event(events, "tot.game24.info", info, puzzle_id))
    return events


def _event(
    events: list[ParsedEvent],
    event_type: str,
    payload: dict[str, Any],
    puzzle_id: str,
) -> ParsedEvent:
    return ParsedEvent(
        sequence=len(events) + 1,
        event_type=event_type,
        payload=payload | {"puzzle_id": puzzle_id},
    )


def _source_run_id(record: dict[str, Any], puzzle_id: str) -> str:
    segment_id = record.get("segment_id") or record.get("run_id") or record.get("log_id")
    if segment_id is None:
        return puzzle_id
    return f"{puzzle_id}:{segment_id}"


def _infos(record: dict[str, Any]) -> list[dict[str, Any]]:
    infos = [info for info in _list(record.get("infos")) if isinstance(info, dict)]
    if infos:
        return infos
    correctness = record.get("correctness")
    if isinstance(correctness, list):
        return [{"correct": value} for value in correctness]
    return [
        {"correct": step["correct"]}
        for step in _list(record.get("steps"))
        if isinstance(step, dict) and "correct" in step
    ]


def _payload(value: Any, *, key: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {key: value}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
