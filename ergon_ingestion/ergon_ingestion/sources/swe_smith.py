"""SWE-smith source parser for generated software-engineering patch records."""

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
from ergon_ingestion.reducers.swe_smith import default_reducers

Record = dict[str, object]

MISSING_PATCH_ROW_FIELDS = [
    "interaction_trace",
    "evaluator_reproduction",
    "test_execution_log",
]


class SweSmithImporter:
    """Read local SWE-smith JSON/JSONL/CSV task or patch rows."""

    info = ImporterInfo(
        slug="swe_smith",
        display_name="SWE-smith",
        schema_fit_class="full-trace",
        supported_formats=["json", "jsonl", "csv"],
        export_claim="conditional",
        default_reducers=["swe_smith.resolved", "swe_smith.patch_record"],
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
                "SWE-smith rows may be task/patch records without full agent interaction traces."
            ],
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        for idx, record in enumerate(iter_swe_smith_records(source.input_path), start=1):
            yield parse_swe_smith_record(record, fallback_id=f"row-{idx}")


def iter_swe_smith_records(path: Path) -> Iterator[Record]:
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

    raise ValueError(f"unsupported SWE-smith input format: {path.suffix}")


def parse_swe_smith_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    instance_id = _instance_id(record, fallback_id=fallback_id)
    source_id = _source_run_id(record, instance_id=instance_id)
    problem_statement = _problem_statement(record)

    return ParsedRun(
        source_run_id=source_id,
        instance_key=instance_id,
        description=f"Imported SWE-smith patch record {instance_id}",
        schema_fit_class="full-trace",
        observed_fields=dict(record),
        missing_fields=MISSING_PATCH_ROW_FIELDS,
        annotations=[
            ParsedAnnotation(
                namespace="swe_smith.task",
                payload={
                    "instance_id": instance_id,
                    "repo": record.get("repo"),
                    "base_commit": record.get("base_commit"),
                },
            ),
            ParsedAnnotation(
                namespace="swe_smith.caveats",
                payload={
                    "trace": "public rows may contain task and patch metadata without interaction traces",
                    "evaluation": "source eval status is preserved, not reproduced by this importer",
                },
            ),
        ],
        resources=_resources_from_record(record, problem_statement=problem_statement),
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


def _resources_from_record(record: Record, *, problem_statement: str) -> list[ParsedResource]:
    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        )
    ]

    patch = _patch_text(record)
    if patch:
        resources.append(
            ParsedResource(
                name="candidate.patch",
                kind="artifact",
                mime_type="text/x-diff",
                payload=patch,
            )
        )

    if problem_statement:
        resources.append(
            ParsedResource(
                name="issue.md",
                kind="note",
                mime_type="text/markdown",
                payload=problem_statement,
            )
        )

    return resources


def _source_run_id(record: Record, *, instance_id: str) -> str:
    explicit = record.get("source_run_id") or record.get("run_id") or record.get("id")
    if explicit is not None:
        return str(explicit)
    return f"swe-smith:{instance_id}"


def _instance_id(record: Record, *, fallback_id: str) -> str:
    value = record.get("instance_id") or record.get("task_id")
    return fallback_id if value is None or value == "" else str(value)


def _patch_text(record: Record) -> str:
    value = record.get("patch")
    if value is None or value == "":
        value = record.get("diff")
    return "" if value is None else str(value)


def _problem_statement(record: Record) -> str:
    value = record.get("problem_statement")
    if value is None or value == "":
        value = record.get("issue")
    return "" if value is None else str(value)


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
