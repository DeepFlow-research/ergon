"""SWE-Lancer source parser for metadata-only task and aggregate records."""

import csv
import json
from collections.abc import Iterator
from pathlib import Path

from ergon_ingestion.models import (
    ImporterInfo,
    ImportSource,
    ParsedAnnotation,
    ParsedResource,
    ParsedRun,
    ValidationReport,
)
from ergon_ingestion.reducers.swe_lancer import default_reducers

Record = dict[str, object]

MISSING_METADATA_ONLY_FIELDS = [
    "full_run_trace",
    "patch_artifact",
    "process_actions",
    "evaluator_environment",
]


class SweLancerImporter:
    """Read local SWE-Lancer CSV/JSON/JSONL metadata and aggregate rows."""

    info = ImporterInfo(
        slug="swe_lancer",
        display_name="SWE-Lancer",
        schema_fit_class="metadata-only",
        supported_formats=["csv", "json", "jsonl"],
        export_claim="conditional",
        default_reducers=["swe_lancer.aggregate_metric", "swe_lancer.task_metadata"],
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
            warnings=[
                "SWE-Lancer rows are metadata-only: no full trace, patch, process actions, "
                "or evaluator environment is imported."
            ],
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        for idx, record in enumerate(iter_swe_lancer_records(source.input_path), start=1):
            yield parse_swe_lancer_record(record, fallback_id=f"row-{idx}")


def iter_swe_lancer_records(path: Path) -> Iterator[Record]:
    if path.suffix == ".jsonl":
        for line in path.read_text().splitlines():
            if line.strip():
                yield _as_record(json.loads(line))
        return

    if path.suffix == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, list):
            for item in data:
                yield _as_record(item)
            return
        yield _as_record(data)
        return

    if path.suffix == ".csv":
        with path.open(newline="") as handle:
            yield from (dict(row) for row in csv.DictReader(handle))
        return

    raise ValueError(f"unsupported SWE-Lancer input format: {path.suffix}")


def parse_swe_lancer_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    instance_id = _instance_id(record, fallback_id=fallback_id)
    source_id = _source_run_id(record, instance_id=instance_id)
    prompt = _task_prompt(record)

    return ParsedRun(
        source_run_id=source_id,
        instance_key=instance_id,
        description=f"Imported SWE-Lancer metadata-only record {instance_id}",
        schema_fit_class="metadata-only",
        observed_fields=dict(record),
        missing_fields=MISSING_METADATA_ONLY_FIELDS,
        annotations=_annotations(record),
        resources=_resources_from_record(record, task_prompt=prompt),
        reducers=default_reducers(record),
    )


def _planned_runs(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        return len(data) if isinstance(data, list) else 1
    if path.suffix == ".csv":
        with path.open(newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    return 1


def _annotations(record: Record) -> list[ParsedAnnotation]:
    return [
        ParsedAnnotation(
            namespace="swe_lancer.task",
            payload={
                "task_id": _task_id(record),
                "instance_id": _instance_id(record, fallback_id=""),
                "repo": record.get("repo"),
                "category": record.get("category"),
                "difficulty": record.get("difficulty"),
                "price": _number_or_none(record.get("price")),
            },
        ),
        ParsedAnnotation(
            namespace="swe_lancer.aggregate",
            payload={
                "score": _number_or_none(record.get("score")),
                "resolved": _boolish(record.get("resolved")),
                "aggregate_metric": _number_or_none(record.get("aggregate_metric")),
                "rank": _int_or_none(record.get("rank")),
            },
        ),
        ParsedAnnotation(
            namespace="swe_lancer.caveats",
            payload={
                "schema_fit_class": "metadata-only",
                "trace": "no_full_run_trace_or_process_actions_in_source_record",
                "patch": "no_patch_artifact_imported",
                "evaluation": "aggregate labels are preserved without evaluator reproduction",
            },
        ),
    ]


def _resources_from_record(record: Record, *, task_prompt: str) -> list[ParsedResource]:
    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        )
    ]
    if task_prompt:
        resources.append(
            ParsedResource(
                name="task-prompt.md",
                kind="note",
                mime_type="text/markdown",
                payload=task_prompt,
            )
        )
    return resources


def _source_run_id(record: Record, *, instance_id: str) -> str:
    explicit = record.get("source_run_id") or record.get("run_id") or record.get("id")
    if explicit is not None and explicit != "":
        return str(explicit)
    return f"swe-lancer:{instance_id}"


def _task_id(record: Record) -> str:
    value = record.get("task_id") or record.get("instance_id")
    return "" if value is None else str(value)


def _instance_id(record: Record, *, fallback_id: str) -> str:
    value = record.get("instance_id") or record.get("task_id")
    return fallback_id if value is None or value == "" else str(value)


def _task_prompt(record: Record) -> str:
    value = record.get("task_prompt")
    if value is None or value == "":
        value = record.get("problem_statement")
    return "" if value is None else str(value)


def _boolish(value: object) -> object:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "resolved", "pass", "passed"}:
            return True
        if normalized in {"false", "0", "no", "n", "unresolved", "fail", "failed"}:
            return False
        if normalized == "":
            return None
    return value


def _number_or_none(value: object) -> object:
    if value is None or isinstance(value, int | float):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return None
        try:
            return float(stripped)
        except ValueError:
            return value
    return value


def _int_or_none(value: object) -> object:
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return None
        try:
            return int(stripped)
        except ValueError:
            return value
    return value


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
