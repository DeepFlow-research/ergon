"""GPQA generated-output row-record source parser."""

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
from ergon_ingestion.reducers.gpqa import default_reducers

Record = dict[str, object]


class GpqaImporter:
    """Read local GPQA JSON/JSONL generated-output exports."""

    info = ImporterInfo(
        slug="gpqa",
        display_name="GPQA generated outputs",
        schema_fit_class="row-record",
        supported_formats=["json", "jsonl"],
        export_claim="safe",
        default_reducers=["gpqa.extracted_accuracy", "gpqa.driver_variant"],
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
        for idx, record in enumerate(iter_gpqa_records(source.input_path), start=1):
            yield parse_gpqa_record(record, fallback_id=f"row-{idx}")


def iter_gpqa_records(path: Path) -> Iterator[Record]:
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

    raise ValueError(f"unsupported GPQA input format: {path.suffix}")


def parse_gpqa_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    source_id = _source_run_id(record, fallback_id=fallback_id)
    generation = record.get("generation")
    return ParsedRun(
        source_run_id=source_id,
        instance_key=source_id,
        description=f"Imported GPQA generated output {source_id}",
        schema_fit_class="row-record",
        observed_fields={
            "item_id": record.get("item_id"),
            "question": record.get("question"),
            "gold_answer": record.get("gold_answer"),
            "generation": generation,
            "extracted_answer": record.get("extracted_answer"),
            "driver_mode": record.get("driver_mode"),
            "extractor_mode": record.get("extractor_mode"),
            "passed": record.get("passed"),
            "correct": record.get("correct"),
        },
        missing_fields=["extraction.registry_match"],
        annotations=[
            ParsedAnnotation(
                namespace="gpqa.task",
                payload={
                    "item_id": record.get("item_id"),
                    "question": record.get("question"),
                    "gold_answer": record.get("gold_answer"),
                },
            ),
            ParsedAnnotation(
                namespace="gpqa.extraction",
                payload={
                    "driver_mode": record.get("driver_mode"),
                    "extractor_mode": record.get("extractor_mode"),
                    "extracted_answer": record.get("extracted_answer"),
                    "correct": record.get("correct"),
                    "passed": record.get("passed"),
                },
            ),
        ],
        resources=_resources(record, generation),
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


def _resources(record: Record, generation: object) -> list[ParsedResource]:
    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        )
    ]
    if generation is not None:
        resources.append(
            ParsedResource(
                name="generation.txt",
                kind="output",
                mime_type="text/plain",
                payload=str(generation),
            )
        )
    return resources


def _source_run_id(record: Record, *, fallback_id: str) -> str:
    explicit = record.get("source_run_id") or record.get("run_id") or record.get("id")
    if explicit is not None:
        return str(explicit)
    item_id = record.get("item_id")
    if item_id is not None:
        return str(item_id)
    return fallback_id


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
