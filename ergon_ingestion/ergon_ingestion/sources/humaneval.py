"""HumanEval row-record source parser."""

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
from ergon_ingestion.reducers.humaneval import default_reducers

Record = dict[str, object]


class HumanEvalImporter:
    """Read local HumanEval JSON/JSONL completion rows without registry wiring."""

    info = ImporterInfo(
        slug="humaneval",
        display_name="HumanEval",
        schema_fit_class="row-record",
        supported_formats=["json", "jsonl"],
        export_claim="conditional",
        default_reducers=["humaneval.original_pass", "humaneval.evalplus_pass"],
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
            warnings=["EvalPlus/driver results may use escalated test suites."],
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        for idx, record in enumerate(iter_humaneval_records(source.input_path), start=1):
            yield parse_humaneval_record(record, fallback_id=f"row-{idx}")


def iter_humaneval_records(path: Path) -> Iterator[Record]:
    if path.suffix == ".jsonl":
        for line in path.read_text().splitlines():
            if line.strip():
                yield _as_record(json.loads(line))
        return

    if path.suffix != ".json":
        raise ValueError(f"unsupported HumanEval input format: {path.suffix}")

    data = json.loads(path.read_text())
    if isinstance(data, list):
        for item in data:
            yield _as_record(item)
        return
    yield _as_record(data)


def parse_humaneval_record(record: Record, *, fallback_id: str = "row-1") -> ParsedRun:
    task_id = _string_field(record, "task_id") or fallback_id
    completion = _completion_text(record)
    return ParsedRun(
        source_run_id=_source_run_id(record, fallback_id=task_id),
        instance_key=task_id,
        description=f"Imported HumanEval completion {task_id}",
        schema_fit_class="row-record",
        observed_fields=dict(record),
        missing_fields=[
            "original.hidden_tests",
            "evalplus.test_suite_delta",
            "driver.execution_trace",
        ],
        annotations=[
            ParsedAnnotation(
                namespace="humaneval.task",
                payload={"task_id": task_id},
            ),
            ParsedAnnotation(
                namespace="humaneval.caveats",
                payload={
                    "evalplus": "test-suite escalation as well as reporting variance",
                },
            ),
        ],
        resources=[
            ParsedResource(
                name="source-record.json",
                kind="import",
                mime_type="application/json",
                payload=dict(record),
            ),
            ParsedResource(
                name="completion.py",
                kind="output",
                mime_type="text/x-python",
                payload=completion,
            ),
        ],
        reducers=default_reducers(record),
    )


def _planned_runs(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        return len(data) if isinstance(data, list) else 1
    return 1


def _source_run_id(record: Record, *, fallback_id: str) -> str:
    explicit = record.get("source_run_id") or record.get("run_id") or record.get("id")
    if explicit is not None:
        return str(explicit)
    return _string_field(record, "task_id") or fallback_id


def _completion_text(record: Record) -> str:
    completion = record.get("completion")
    if completion is not None:
        return str(completion)
    code = record.get("code")
    return "" if code is None else str(code)


def _string_field(record: Record, key: str) -> str:
    value = record.get(key)
    return "" if value is None else str(value)


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
