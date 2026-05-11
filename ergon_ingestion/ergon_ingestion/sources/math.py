"""MATH fixed-completion row-record source parser."""

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
from ergon_ingestion.reducers.math import default_reducers, missing_judge_fields

Record = dict[str, object]


class MathImporter:
    """Read local MATH JSON/JSONL fixed-completion exports."""

    info = ImporterInfo(
        slug="math",
        display_name="MATH fixed completions",
        schema_fit_class="row-record",
        supported_formats=["json", "jsonl"],
        export_claim="safe",
        default_reducers=[
            "math.extracted_accuracy",
            "math.normalization_convention",
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
        for idx, record in enumerate(iter_math_records(source.input_path), start=1):
            yield parse_math_record(record, fallback_id=f"row-{idx}")


def iter_math_records(path: Path) -> Iterator[Record]:
    if path.suffix == ".jsonl":
        for line in path.read_text().splitlines():
            if line.strip():
                yield _as_record(json.loads(line))
        return

    if path.suffix == ".json":
        data = json.loads(path.read_text())
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            yield _as_record(row)
        return

    raise ValueError(f"unsupported MATH input format: {path.suffix}")


def parse_math_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    source_id = _source_run_id(record, fallback_id=fallback_id)
    completion = _first_present(record, ["completion", "model_answer"])
    return ParsedRun(
        source_run_id=source_id,
        instance_key=source_id,
        description=f"Imported MATH fixed completion {source_id}",
        schema_fit_class="row-record",
        observed_fields={
            "problem_id": record.get("problem_id"),
            "problem": record.get("problem"),
            "solution": record.get("solution"),
            "gold_answer": record.get("gold_answer"),
            "completion": record.get("completion"),
            "model_answer": record.get("model_answer"),
            "extracted_answer": record.get("extracted_answer"),
            "boxed": record.get("boxed"),
            "normalization_mode": record.get("normalization_mode"),
            "convention": record.get("convention"),
        },
        missing_fields=missing_judge_fields(record),
        annotations=[
            ParsedAnnotation(
                namespace="math.task",
                payload={
                    "problem_id": record.get("problem_id"),
                    "problem": record.get("problem"),
                    "gold_answer": _first_present(record, ["gold_answer", "solution"]),
                },
            ),
            ParsedAnnotation(
                namespace="math.extraction",
                payload={
                    "extracted_answer": record.get("extracted_answer"),
                    "boxed": record.get("boxed"),
                    "normalization_mode": record.get("normalization_mode"),
                    "convention": record.get("convention"),
                },
            ),
        ],
        resources=_resources(record, completion),
        reducers=default_reducers(record),
    )


def _planned_runs(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        return len(data) if isinstance(data, list) else 1
    return 1


def _resources(record: Record, completion: object) -> list[ParsedResource]:
    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        )
    ]
    if completion is not None:
        resources.append(
            ParsedResource(
                name="completion.txt",
                kind="output",
                mime_type="text/plain",
                payload=str(completion),
            )
        )
    return resources


def _source_run_id(record: Record, *, fallback_id: str) -> str:
    explicit = _first_present(record, ["source_run_id", "run_id", "problem_id", "id"])
    if explicit is not None:
        return str(explicit)
    return fallback_id


def _first_present(record: Record, keys: list[str]) -> object | None:
    for key in keys:
        if key in record:
            return record[key]
    return None


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
