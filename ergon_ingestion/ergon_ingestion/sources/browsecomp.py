"""BrowseComp row-record source parser."""

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
from ergon_ingestion.reducers.browsecomp import default_reducers

Record = dict[str, object]

ANSWER_FIELDS = ["question_id", "gold_answer", "predicted_answer", "status"]
JUDGE_FIELDS = ["judge_result", "judge_explanation"]
METADATA_FIELDS = ["canary", "canary_note", "decryption_note", "decryption_notes"]


class BrowseCompImporter:
    """Read local BrowseComp JSON/JSONL answer and judge rows."""

    info = ImporterInfo(
        slug="browsecomp",
        display_name="BrowseComp",
        schema_fit_class="row-record",
        supported_formats=["json", "jsonl"],
        export_claim="safe",
        default_reducers=["browsecomp.exact_match", "browsecomp.llm_judge"],
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
        for idx, record in enumerate(iter_browsecomp_records(source.input_path), start=1):
            yield parse_browsecomp_record(record, fallback_id=f"row-{idx}")


def iter_browsecomp_records(path: Path) -> Iterator[Record]:
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

    raise ValueError(f"unsupported BrowseComp input format: {path.suffix}")


def parse_browsecomp_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    source_id = _source_run_id(record, fallback_id=fallback_id)
    judge_payload = _payload_for_fields(record, JUDGE_FIELDS)
    resources = [
        ParsedResource(
            name="source-row.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        )
    ]
    if judge_payload:
        resources.append(
            ParsedResource(
                name="judge-output.json",
                kind="report",
                mime_type="application/json",
                payload=judge_payload,
            )
        )

    return ParsedRun(
        source_run_id=source_id,
        instance_key=source_id,
        description=f"Imported BrowseComp answer row {source_id}",
        schema_fit_class="row-record",
        observed_fields=dict(record),
        missing_fields=_missing_fields(record),
        annotations=_annotations(record),
        resources=resources,
        reducers=default_reducers(record),
    )


def _planned_runs(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        return len(data) if isinstance(data, list) else 1
    return 1


def _annotations(record: Record) -> list[ParsedAnnotation]:
    annotations = [
        ParsedAnnotation(
            namespace="browsecomp.answers",
            payload=_payload_for_fields(record, ANSWER_FIELDS),
        ),
        ParsedAnnotation(
            namespace="browsecomp.judge",
            payload=_payload_for_fields(record, JUDGE_FIELDS),
        ),
    ]
    metadata = _payload_for_fields(record, METADATA_FIELDS)
    if metadata:
        annotations.append(ParsedAnnotation(namespace="browsecomp.metadata", payload=metadata))
    return annotations


def _payload_for_fields(record: Record, fields: list[str]) -> dict[str, object]:
    return {field: record[field] for field in fields if field in record}


def _missing_fields(record: Record) -> list[str]:
    missing: list[str] = []
    if "browsing_trace" not in record and "browser_trace" not in record:
        missing.append("browsing_trace")
    return missing


def _source_run_id(record: Record, *, fallback_id: str) -> str:
    explicit = (
        record.get("question_id")
        or record.get("source_run_id")
        or record.get("run_id")
        or record.get("id")
    )
    return str(explicit) if explicit is not None else fallback_id


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
