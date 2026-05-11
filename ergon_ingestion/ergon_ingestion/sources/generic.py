"""Generic local-file importer used by dataset-specific modules."""

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ergon_ingestion.models import (
    ImporterInfo,
    ImportSource,
    ParsedAnnotation,
    ParsedDrop,
    ParsedReducer,
    ParsedResource,
    ParsedRun,
    ValidationReport,
)


class FileDatasetImporter:
    """Parse common local public artifact shapes into conservative run records."""

    def __init__(self, info: ImporterInfo) -> None:
        self.info = info

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
            planned_runs=self._planned_runs(source.input_path),
            warnings=self._warnings(),
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        if source.input_path.is_dir():
            for path in sorted(p for p in source.input_path.iterdir() if p.is_file()):
                yield self._run_from_file(path)
            return
        yield from self._runs_from_file(source.input_path)

    def _planned_runs(self, path: Path) -> int:
        if path.is_dir():
            return len([child for child in path.iterdir() if child.is_file()])
        if path.suffix == ".jsonl":
            return sum(1 for line in path.read_text().splitlines() if line.strip())
        if path.suffix == ".csv":
            with path.open(newline="") as handle:
                return sum(1 for _ in csv.DictReader(handle))
        return 1

    def _runs_from_file(self, path: Path) -> Iterator[ParsedRun]:
        if path.suffix == ".jsonl":
            for idx, line in enumerate(path.read_text().splitlines(), start=1):
                if line.strip():
                    yield self._run_from_mapping(json.loads(line), fallback_id=f"row-{idx}")
            return
        if path.suffix == ".json":
            data = json.loads(path.read_text())
            if isinstance(data, list):
                for idx, item in enumerate(data, start=1):
                    yield self._run_from_mapping(_as_mapping(item), fallback_id=f"row-{idx}")
            else:
                yield self._run_from_mapping(_as_mapping(data), fallback_id=path.stem)
            return
        if path.suffix == ".csv":
            with path.open(newline="") as handle:
                for idx, row in enumerate(csv.DictReader(handle), start=1):
                    yield self._run_from_mapping(row, fallback_id=f"row-{idx}")
            return
        yield self._run_from_file(path)

    def _run_from_file(self, path: Path) -> ParsedRun:
        source_id = path.stem
        return ParsedRun(
            source_run_id=source_id,
            instance_key=source_id,
            description=f"Imported {self.info.slug} artifact {path.name}",
            schema_fit_class=self.info.schema_fit_class,
            observed_fields={"file_name": path.name},
            missing_fields=[],
            annotations=[
                ParsedAnnotation(
                    namespace=f"{self.info.slug}.source",
                    payload={"file_name": path.name, "source_kind": "file"},
                )
            ],
            resources=[
                ParsedResource(
                    name=path.name,
                    kind="import",
                    mime_type=_mime_type(path),
                    path=path,
                )
            ],
            reducers=self._default_reducers({"file_name": path.name}),
        )

    def _run_from_mapping(self, record: dict[str, Any], *, fallback_id: str) -> ParsedRun:
        source_id = str(
            record.get("source_run_id")
            or record.get("instance_key")
            or record.get("id")
            or record.get("run_id")
            or fallback_id
        )
        instance_key = str(record.get("instance_key") or source_id)
        description = str(
            record.get("description") or f"Imported {self.info.slug} record {source_id}"
        )
        return ParsedRun(
            source_run_id=source_id,
            instance_key=instance_key,
            description=description,
            schema_fit_class=self.info.schema_fit_class,
            observed_fields=record,
            missing_fields=[],
            annotations=[
                ParsedAnnotation(namespace=f"{self.info.slug}.source", payload=dict(record))
            ],
            resources=[
                ParsedResource(
                    name="source-record.json",
                    kind="import",
                    mime_type="application/json",
                    payload=record,
                )
            ],
            reducers=self._default_reducers(record),
        )

    def _default_reducers(self, record: dict[str, Any]) -> list[ParsedReducer]:
        if not self.info.default_reducers:
            return []
        fields = sorted(str(key) for key in record.keys())
        return [
            ParsedReducer(
                name=name,
                kind="original" if idx == 0 else "recovered",
                output={"source_observed": True},
                implementation_ref=f"ergon_ingestion.sources.{self.info.slug}",
                fields_read=fields,
                drops=[
                    ParsedDrop(
                        loss_class="unavailable_source_field",
                        reason="unavailable_in_source",
                        declaration_kind="source_missing",
                    )
                ],
            )
            for idx, name in enumerate(self.info.default_reducers)
        ]

    def _warnings(self) -> list[str]:
        if self.info.export_claim == "conditional":
            return [f"{self.info.slug} has conditional export-claim status"]
        if self.info.export_claim == "not_now":
            return [f"{self.info.slug} should not be included in the artifact claim"]
        return []


def _as_mapping(value: Any) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    if isinstance(value, dict):
        return value
    return {"value": value}


def _mime_type(path: Path) -> str:
    if path.suffix in {".json", ".jsonl"}:
        return "application/json"
    if path.suffix == ".csv":
        return "text/csv"
    return "text/plain"
