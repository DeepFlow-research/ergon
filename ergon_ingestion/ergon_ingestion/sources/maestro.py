"""MAESTRO span-trace source parser."""

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from ergon_ingestion.models import (
    ImporterInfo,
    ImportSource,
    ParsedAnnotation,
    ParsedEvent,
    ParsedResource,
    ParsedRun,
    ValidationReport,
)
from ergon_ingestion.reducers.maestro import (
    coordination_overhead_reducer,
    outcome_reducer,
)


class MaestroImporter:
    """Parse MAESTRO public span rows into one run per ``run_id``."""

    info = ImporterInfo(
        slug="maestro",
        display_name="MAESTRO multi-agent trace parquet",
        schema_fit_class="span-trace",
        supported_formats=["parquet", "jsonl", "json"],
        export_claim="conditional",
        paper_result_ids=["rq1.maestro.coordination_overhead"],
        default_reducers=["maestro.outcome", "maestro.coordination_overhead"],
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
            planned_runs=len({str(row["run_id"]) for row in _read_rows(source.input_path)}),
            warnings=[f"{self.info.slug} has conditional export-claim status"],
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        yield from parse_maestro_runs(_read_rows(source.input_path))


def parse_maestro_runs(rows: Iterable[Mapping[str, Any]]) -> list[ParsedRun]:
    """Group MAESTRO span rows by ``run_id`` and emit parsed run contracts."""

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        record = dict(row)
        grouped[str(record["run_id"])].append(record)

    return [_run_from_spans(run_id, spans) for run_id, spans in sorted(grouped.items())]


def _run_from_spans(run_id: str, spans: list[dict[str, Any]]) -> ParsedRun:
    outcome = _first_present(spans, "attributes.run.outcome", "run.outcome")
    judgement = _first_present(spans, "attributes.run.judgement", "run.judgement")
    trace_ids = sorted({str(span["trace_id"]) for span in spans if span.get("trace_id")})
    agent_names = sorted({str(span["agent_name"]) for span in spans if span.get("agent_name")})
    coordination = coordination_overhead_reducer(spans)
    observed_fields = {
        "run_id": run_id,
        "trace_ids": trace_ids,
        "span_count": len(spans),
        "agent_names": agent_names,
        "duration_ms": coordination.output["duration_ms"],
        "token_count": coordination.output["token_count"],
        "status_counts": coordination.output["status_counts"],
        "error_count": coordination.output["error_count"],
        "outcome": outcome,
        "judgement": judgement,
    }

    return ParsedRun(
        source_run_id=run_id,
        instance_key=run_id,
        description=f"Imported MAESTRO span trace {run_id}",
        schema_fit_class="span-trace",
        observed_fields=observed_fields,
        annotations=[
            ParsedAnnotation(namespace="maestro.source", payload=observed_fields),
            ParsedAnnotation(
                namespace="maestro.outcome",
                payload={
                    key: value
                    for key, value in {"outcome": outcome, "judgement": judgement}.items()
                    if value is not None
                },
            ),
        ],
        events=[
            ParsedEvent(
                sequence=sequence,
                event_type="maestro.span",
                payload=span,
                worker_binding_key=str(span.get("agent_name") or "imported"),
            )
            for sequence, span in enumerate(spans, start=1)
        ],
        resources=[
            ParsedResource(
                name=f"{run_id}-spans.json",
                kind="artifact",
                mime_type="application/json",
                payload={"spans": spans},
            )
        ],
        reducers=[outcome_reducer(outcome, judgement), coordination],
    )


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return [_as_mapping(item) for item in data]
        return [_as_mapping(data)]
    if path.suffix == ".parquet":
        try:
            import pandas as pd  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError("MAESTRO parquet import requires pandas/pyarrow") from exc
        return [dict(row) for row in pd.read_parquet(path).to_dict(orient="records")]
    raise ValueError(f"unsupported MAESTRO input format: {path.suffix}")


def _first_present(spans: Iterable[Mapping[str, Any]], *paths: str) -> str | None:
    for span in spans:
        for path in paths:
            value = _lookup(span, path)
            if value is not None:
                return str(value)
    return None


def _lookup(record: Mapping[str, Any], path: str) -> Any | None:  # slopcop: ignore[no-typing-any]
    parts = path.split(".")
    value: Any = record
    for idx, part in enumerate(parts):
        if not isinstance(value, Mapping):
            return None
        remaining = ".".join(parts[idx:])
        if remaining in value:
            return value[remaining]
        if part not in value:
            return None
        value = value[part]
    return value


def _as_mapping(value: Any) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    if isinstance(value, dict):
        return value
    return {"value": value}
