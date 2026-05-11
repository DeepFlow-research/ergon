"""MLE-Bench archived-submission source parser."""

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
from ergon_ingestion.reducers.mle_bench import default_reducers

Record = dict[str, object]

MISSING_LIVE_FIELDS = [
    "live_reexecution_environment",
    "competition_private_test_runtime",
    "container_image",
]
VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


class MleBenchImporter:
    """Read local JSON/JSONL MLE-Bench archived-submission records."""

    info = ImporterInfo(
        slug="mle_bench",
        display_name="MLE-Bench archived submissions",
        schema_fit_class="artifact-only",
        supported_formats=["json", "jsonl"],
        export_claim="conditional",
        default_reducers=["mle_bench.score", "mle_bench.medal_threshold"],
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
            warnings=["mle_bench has conditional export-claim status"],
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        for idx, record in enumerate(iter_mle_bench_records(source.input_path), start=1):
            yield parse_mle_bench_record(record, fallback_id=f"row-{idx}")


def iter_mle_bench_records(path: Path) -> Iterator[Record]:
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

    raise ValueError(f"unsupported MLE-Bench input format: {path.suffix}")


def parse_mle_bench_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    submission_id = _string_field(record, "submission_id") or fallback_id
    competition_id = _string_field(record, "competition_id") or "unknown-competition"
    source_run_id = _source_run_id(record, competition_id, submission_id)

    return ParsedRun(
        source_run_id=source_run_id,
        instance_key=f"{competition_id}:{submission_id}",
        description=f"MLE-Bench archived submission {submission_id} for {competition_id}",
        schema_fit_class="artifact-only",
        observed_fields=dict(record),
        missing_fields=MISSING_LIVE_FIELDS,
        annotations=[
            ParsedAnnotation(
                namespace="mle_bench.submission",
                payload={
                    "submission_id": submission_id,
                    "competition_id": competition_id,
                    "medal": record.get("medal"),
                },
            )
        ],
        resources=_resources_from_record(record),
        reducers=default_reducers(record),
    )


def _planned_runs(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        return len(data) if isinstance(data, list) else 1
    return 1


def _resources_from_record(record: Record) -> list[ParsedResource]:
    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        )
    ]
    for artifact in _artifact_records(record):
        path = Path(_string_field(artifact, "path") or _string_field(artifact, "file_path"))
        resources.append(
            ParsedResource(
                name=path.name,
                kind=_resource_kind(artifact.get("kind")),
                mime_type=str(artifact.get("mime_type") or _mime_type(path)),
                path=path,
                payload=artifact.get("payload"),
            )
        )
    return resources


def _artifact_records(record: Record) -> list[Record]:
    artifacts = record.get("artifacts") or record.get("files")
    if isinstance(artifacts, list):
        return [item for item in artifacts if isinstance(item, dict)]

    file_path = record.get("file_path") or record.get("path")
    if file_path is None:
        return []
    return [
        {
            "path": file_path,
            "kind": record.get("file_kind") or record.get("kind") or "artifact",
            "mime_type": record.get("mime_type"),
            "payload": record.get("payload"),
        }
    ]


def _resource_kind(value: object) -> str:
    kind = str(value or "artifact")
    if kind in VALID_RESOURCE_KINDS:
        return kind
    return "artifact"


def _source_run_id(record: Record, competition_id: str, submission_id: str) -> str:
    explicit = record.get("source_run_id") or record.get("run_id") or record.get("id")
    if explicit is not None:
        return str(explicit)
    return f"mle:{competition_id}:{submission_id}"


def _string_field(record: Record, key: str) -> str:
    value = record.get(key)
    return "" if value is None else str(value)


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}


def _mime_type(path: Path) -> str:
    if path.suffix == ".ipynb":
        return "application/x-ipynb+json"
    if path.suffix == ".csv":
        return "text/csv"
    if path.suffix == ".json":
        return "application/json"
    return "text/plain"
