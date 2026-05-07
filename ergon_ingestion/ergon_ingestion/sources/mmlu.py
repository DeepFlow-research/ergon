"""MMLU row-record source parser."""

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
from ergon_ingestion.reducers.mmlu import (
    answer_accuracy_reducer,
    missing_full_context_fields,
    prompt_extraction_convention_reducer,
)

Record = dict[str, object]


class MmluImporter:
    """Parse MMLU JSON/JSONL rows into one run per model/subject/item row."""

    info = ImporterInfo(
        slug="mmlu",
        display_name="MMLU",
        schema_fit_class="row-record",
        supported_formats=["jsonl", "json"],
        export_claim="safe",
        default_reducers=[
            "mmlu.answer_accuracy",
            "mmlu.prompt_extraction_convention",
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
        for idx, row in enumerate(iter_mmlu_rows(source.input_path), start=1):
            yield parse_mmlu_row(row, fallback_id=f"row-{idx}")


def iter_mmlu_rows(path: Path) -> Iterator[Record]:
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

    raise ValueError(f"unsupported MMLU input format: {path.suffix}")


def parse_mmlu_row(row: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    model = _model_name(row)
    subject = _string_or_none(row.get("subject")) or "unknown_subject"
    item_id = _item_id(row, fallback_id=fallback_id)
    source_id = _source_run_id(row, model=model, subject=subject, item_id=item_id)
    labels = {
        "subject": subject,
        "item_id": item_id,
        "model": model,
    }
    return ParsedRun(
        source_run_id=source_id,
        instance_key=f"{subject}:{item_id}",
        description=f"Imported MMLU row {source_id}",
        schema_fit_class="row-record",
        observed_fields=dict(row),
        missing_fields=missing_full_context_fields(row),
        annotations=[ParsedAnnotation(namespace="mmlu.labels", payload=labels)],
        resources=[
            ParsedResource(
                name="source-row.json",
                kind="import",
                mime_type="application/json",
                payload=dict(row),
            )
        ],
        reducers=[
            answer_accuracy_reducer(row),
            prompt_extraction_convention_reducer(row),
        ],
    )


def _planned_runs(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        return len(data) if isinstance(data, list) else 1
    return 1


def _source_run_id(row: Record, *, model: str, subject: str, item_id: str) -> str:
    explicit = _first_present(row, ["source_run_id", "run_id"])
    if explicit is not None:
        return str(explicit)
    return f"{model}:{subject}:{item_id}"


def _item_id(row: Record, *, fallback_id: str) -> str:
    value = _first_present(row, ["item_id", "id", "question_id"])
    if value is None:
        return fallback_id
    return str(value)


def _model_name(row: Record) -> str:
    return (
        _string_or_none(_first_present(row, ["model", "model_name", "model_id"])) or "unknown_model"
    )


def _first_present(row: Record, keys: list[str]) -> object | None:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
