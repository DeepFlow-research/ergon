"""GSM8K row-record source parser."""

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
from ergon_ingestion.reducers.gsm8k import default_reducers

Record = dict[str, object]


class Gsm8kImporter:
    """Read local GSM8K JSON/JSONL fixed-completion exports."""

    info = ImporterInfo(
        slug="gsm8k",
        display_name="GSM8K fixed completions",
        schema_fit_class="row-record",
        supported_formats=["json", "jsonl"],
        export_claim="safe",
        default_reducers=[
            "gsm8k.extracted_accuracy",
            "gsm8k.answer_format_convention",
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
        for idx, record in enumerate(iter_gsm8k_records(source.input_path), start=1):
            yield parse_gsm8k_record(record, fallback_id=f"row-{idx}")


def iter_gsm8k_records(path: Path) -> Iterator[Record]:
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

    raise ValueError(f"unsupported GSM8K input format: {path.suffix}")


def parse_gsm8k_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    source_id = _source_run_id(record, fallback_id=fallback_id)
    completion = record.get("completion")
    return ParsedRun(
        source_run_id=source_id,
        instance_key=source_id,
        description=f"Imported GSM8K fixed completion {source_id}",
        schema_fit_class="row-record",
        observed_fields={
            "item_id": record.get("item_id"),
            "question_id": record.get("question_id"),
            "question": record.get("question"),
            "gold_answer": record.get("gold_answer"),
            "answer": record.get("answer"),
            "completion": completion,
            "extracted_answer": record.get("extracted_answer"),
            "convention": record.get("convention"),
            "mode": record.get("mode"),
            "extractor_mode": record.get("extractor_mode"),
            "correct": record.get("correct"),
            "passed": record.get("passed"),
        },
        missing_fields=_missing_fields(record),
        annotations=[
            ParsedAnnotation(
                namespace="gsm8k.task",
                payload={
                    "item_id": record.get("item_id") or record.get("question_id"),
                    "question": record.get("question"),
                    "gold_answer": record.get("gold_answer") or record.get("answer"),
                },
            ),
            ParsedAnnotation(
                namespace="gsm8k.extraction",
                payload={
                    "completion": completion,
                    "extracted_answer": record.get("extracted_answer"),
                    "convention": record.get("convention"),
                    "mode": record.get("mode"),
                    "extractor_mode": record.get("extractor_mode"),
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
        if isinstance(data, list):
            return len(data)
        return 1
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


def _missing_fields(record: Record) -> list[str]:
    missing = ["answer.normalization_provenance"]
    if record.get("convention") is None:
        missing.append("answer.format_convention")
    return missing


def _source_run_id(record: Record, *, fallback_id: str) -> str:
    explicit = (
        record.get("source_run_id")
        or record.get("run_id")
        or record.get("id")
        or record.get("item_id")
        or record.get("question_id")
    )
    if explicit is not None:
        return str(explicit)
    return fallback_id


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
