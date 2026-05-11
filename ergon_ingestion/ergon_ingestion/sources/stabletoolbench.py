"""StableToolBench source parser for full-trace tool-use trajectories."""

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
from ergon_ingestion.reducers.stabletoolbench import default_reducers

Record = dict[str, object]


class StableToolBenchImporter:
    """Read local StableToolBench JSON/JSONL trajectory exports."""

    info = ImporterInfo(
        slug="stabletoolbench",
        display_name="StableToolBench",
        schema_fit_class="full-trace",
        supported_formats=["json", "jsonl"],
        export_claim="safe",
        default_reducers=["stabletoolbench.win", "stabletoolbench.tool_path"],
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
        for idx, record in enumerate(iter_stabletoolbench_records(source.input_path), start=1):
            yield parse_stabletoolbench_record(record, fallback_id=f"row-{idx}")


def iter_stabletoolbench_records(path: Path) -> Iterator[Record]:
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


def parse_stabletoolbench_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    source_id = _source_run_id(record, fallback_id=fallback_id)
    task_id = _string_field(record, "task_id")
    answer_steps = record.get("answer_steps")
    observed_answer_steps = answer_steps if isinstance(answer_steps, list) else []

    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        )
    ]
    if isinstance(answer_steps, list):
        resources.append(
            ParsedResource(
                name="answer-steps.json",
                kind="artifact",
                mime_type="application/json",
                payload={"answer_steps": answer_steps},
            )
        )

    return ParsedRun(
        source_run_id=source_id,
        instance_key=task_id or source_id,
        description=f"Imported StableToolBench trajectory {source_id}",
        schema_fit_class="full-trace",
        observed_fields={
            "trajectory_id": record.get("trajectory_id"),
            "task_id": task_id,
            "answer_steps": observed_answer_steps,
            "is_solved": record.get("is_solved"),
            "win": record.get("win"),
            "pass": record.get("pass"),
            "evaluator_statuses": _evaluator_statuses(record),
        },
        missing_fields=["independent_evaluator_regrade"],
        annotations=[
            ParsedAnnotation(
                namespace="stabletoolbench.task",
                payload={"trajectory_id": record.get("trajectory_id"), "task_id": task_id},
            ),
            ParsedAnnotation(
                namespace="stabletoolbench.outcome",
                payload={
                    "is_solved": record.get("is_solved"),
                    "win": record.get("win"),
                    "pass": record.get("pass"),
                    "evaluator_statuses": _evaluator_statuses(record),
                },
            ),
        ],
        events=_events_from_answer_steps(record),
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


def _events_from_answer_steps(record: Record) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    answer_steps = record.get("answer_steps")
    if not isinstance(answer_steps, list):
        return events
    for step_index, step in enumerate(answer_steps):
        if not isinstance(step, dict):
            continue
        tool_name = _tool_name(step)
        if tool_name is None:
            continue
        events.append(
            ParsedEvent(
                sequence=len(events),
                event_type="tool_step",
                payload={
                    "step_index": step_index,
                    "tool_name": tool_name,
                    "arguments": _arguments(step),
                    "response": step.get("response"),
                    "status": step.get("status"),
                },
            )
        )
    return events


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


def _string_field(record: Record, key: str) -> str:
    value = record.get(key)
    return "" if value is None else str(value)


def _tool_name(step: Record) -> str | None:
    value = step.get("tool") or step.get("tool_name") or step.get("name")
    if value is None:
        return None
    return str(value)


def _arguments(step: Record) -> object:
    if "arguments" in step:
        return step.get("arguments")
    return step.get("args")


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


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
