"""GAP row-record source parser."""

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
from ergon_ingestion.reducers.gap import text_safety_reducer, tool_call_safety_reducer


class GapImporter:
    """Parse GAP JSONL/JSON/CSV rows into local ingestion contracts."""

    info = ImporterInfo(
        slug="gap",
        display_name="GAP",
        schema_fit_class="row-record",
        supported_formats=["parquet", "jsonl", "json", "csv"],
        export_claim="safe",
        default_reducers=["gap.text_safety", "gap.tool_call_safety"],
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
        yield from self._runs_from_file(source.input_path)

    def parse_row(self, row: dict[str, object], *, fallback_id: str) -> ParsedRun:
        source_id = str(
            row.get("source_run_id")
            or row.get("run_id")
            or row.get("id")
            or row.get("task_id")
            or fallback_id
        )
        labels = {
            key: row[key]
            for key in ["t_safe", "tc_safe", "gap", "forbidden_calls", "refusal_strength"]
            if key in row
        }
        return ParsedRun(
            source_run_id=source_id,
            instance_key=str(row.get("instance_key") or source_id),
            description=str(row.get("description") or f"Imported GAP row {source_id}"),
            schema_fit_class=self.info.schema_fit_class,
            observed_fields=dict(row),
            missing_fields=["tool_channel_transcript"],
            annotations=[ParsedAnnotation(namespace="gap.labels", payload=labels)],
            resources=[
                ParsedResource(
                    name="source-row.json",
                    kind="import",
                    mime_type="application/json",
                    payload=dict(row),
                )
            ],
            reducers=[text_safety_reducer(row), tool_call_safety_reducer(row)],
        )

    def _runs_from_file(self, path: Path) -> Iterator[ParsedRun]:
        if path.suffix == ".jsonl":
            for idx, line in enumerate(path.read_text().splitlines(), start=1):
                if line.strip():
                    yield self.parse_row(json.loads(line), fallback_id=f"row-{idx}")
            return
        if path.suffix == ".json":
            data = json.loads(path.read_text())
            rows = data if isinstance(data, list) else [data]
            for idx, row in enumerate(rows, start=1):
                yield self.parse_row(dict(row), fallback_id=f"row-{idx}")
            return
        if path.suffix == ".csv":
            with path.open(newline="") as handle:
                for idx, row in enumerate(csv.DictReader(handle), start=1):
                    yield self.parse_row(dict(row), fallback_id=f"row-{idx}")
            return
        if path.suffix == ".parquet":
            for idx, row in enumerate(_read_parquet_rows(path), start=1):
                yield self.parse_row(row, fallback_id=f"row-{idx}")
            return
        raise ValueError(f"unsupported GAP input format: {path.suffix}")


def _planned_runs(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        return len(data) if isinstance(data, list) else 1
    if path.suffix == ".csv":
        with path.open(newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    if path.suffix == ".parquet":
        return len(_read_parquet_rows(path))
    return 1


def _read_parquet_rows(path: Path) -> list[dict[str, object]]:
    try:
        import pandas as pd  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("GAP parquet import requires pandas/pyarrow") from exc
    return [dict(row) for row in pd.read_parquet(path).to_dict(orient="records")]
