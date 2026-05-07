"""BFCL row-record source parser."""

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
from ergon_ingestion.reducers.bfcl import default_reducers

Record = dict[str, object]


class BfclImporter:
    """Read local Berkeley Function Calling Leaderboard JSON/JSONL rows."""

    info = ImporterInfo(
        slug="bfcl",
        display_name="Berkeley Function Calling Leaderboard",
        schema_fit_class="row-record",
        supported_formats=["json", "jsonl"],
        export_claim="conditional",
        default_reducers=["bfcl.call_correctness", "bfcl.tool_call_record"],
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
                "BFCL row records may omit executable tool traces, environments, and judge details."
            ],
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        for idx, record in enumerate(iter_bfcl_records(source.input_path), start=1):
            yield parse_bfcl_record(record, fallback_id=f"row-{idx}")


def iter_bfcl_records(path: Path) -> Iterator[Record]:
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

    raise ValueError(f"unsupported BFCL input format: {path.suffix}")


def parse_bfcl_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    source_id = _source_run_id(record, fallback_id=fallback_id)
    prompt = _first_present(record, ["prompt", "question"])
    tool_schema = _tool_schema(record)
    tool_calls = _tool_calls(record)
    expected_call = _first_present(record, ["expected_call", "ground_truth"])
    return ParsedRun(
        source_run_id=source_id,
        instance_key=source_id,
        description=f"Imported BFCL function-calling row {source_id}",
        schema_fit_class="row-record",
        observed_fields=dict(record),
        missing_fields=_missing_fields(record),
        annotations=[
            ParsedAnnotation(
                namespace="bfcl.task",
                payload={
                    "question_id": source_id,
                    "prompt": prompt,
                    "category": record.get("category"),
                },
            ),
            ParsedAnnotation(namespace="bfcl.tool_schema", payload=tool_schema),
            ParsedAnnotation(
                namespace="bfcl.calls",
                payload={
                    "model_response": record.get("model_response"),
                    "tool_calls": tool_calls,
                    "expected_call": expected_call,
                },
            ),
        ],
        resources=_resources(record, tool_schema, expected_call),
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


def _resources(
    record: Record,
    tool_schema: dict[str, object],
    expected_call: object | None,
) -> list[ParsedResource]:
    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=dict(record),
        )
    ]
    if tool_schema:
        resources.append(
            ParsedResource(
                name="tool-schema.json",
                kind="artifact",
                mime_type="application/json",
                payload=tool_schema,
            )
        )
    if record.get("model_response") is not None:
        resources.append(
            ParsedResource(
                name="model-response.json",
                kind="output",
                mime_type="application/json",
                payload=record.get("model_response"),
            )
        )
    if expected_call is not None:
        resources.append(
            ParsedResource(
                name="expected-call.json",
                kind="report",
                mime_type="application/json",
                payload={"expected_call": expected_call},
            )
        )
    return resources


def _missing_fields(record: Record) -> list[str]:
    missing = []
    if _first_present(record, ["function_execution_trace", "execution_trace"]) is None:
        missing.append("function_execution_trace")
    if _first_present(record, ["function_execution_environment", "execution_environment"]) is None:
        missing.append("function_execution_environment")
    if _first_present(record, ["judge_details", "evaluator_details"]) is None:
        missing.append("evaluator_judge_details")
    return missing


def _tool_schema(record: Record) -> dict[str, object]:
    schema: dict[str, object] = {}
    if "tools" in record:
        schema["tools"] = record["tools"]
    if "functions" in record:
        schema["functions"] = record["functions"]
    return schema


def _tool_calls(record: Record) -> object | None:
    if "tool_calls" in record:
        return record["tool_calls"]
    model_response = record.get("model_response")
    if isinstance(model_response, dict):
        return model_response.get("tool_calls")
    return None


def _source_run_id(record: Record, *, fallback_id: str) -> str:
    explicit = (
        record.get("source_run_id")
        or record.get("run_id")
        or record.get("id")
        or record.get("question_id")
    )
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
