"""SWE-bench cross-harness source parser for verdict and patch artifacts."""

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
from ergon_ingestion.reducers.swebench_cross_harness import default_reducers

Record = dict[str, object]

MISSING_ARTIFACT_FIELDS = [
    "agent_trace",
    "test_environment",
]


class SwebenchCrossHarnessImporter:
    """Read local SWE-bench cross-harness JSON/JSONL artifact exports."""

    info = ImporterInfo(
        slug="swebench_cross_harness",
        display_name="SWE-bench cross-harness",
        schema_fit_class="artifact-only",
        supported_formats=["json", "jsonl"],
        export_claim="conditional",
        default_reducers=[
            "swebench_cross_harness.verdict",
            "swebench_cross_harness.patch_footprint",
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
            warnings=[
                "SWE-bench cross-harness rows preserve artifacts and verdicts, not full traces."
            ],
        )

    def iter_runs(self, source: ImportSource) -> Iterator[ParsedRun]:
        report = self.validate(source)
        if not report.ok:
            raise FileNotFoundError("; ".join(report.errors))
        for idx, record in enumerate(
            iter_swebench_cross_harness_records(source.input_path), start=1
        ):
            yield parse_swebench_cross_harness_record(
                record,
                source_dir=source.input_path.parent,
                fallback_id=f"row-{idx}",
            )


def iter_swebench_cross_harness_records(path: Path) -> Iterator[Record]:
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

    raise ValueError(f"unsupported SWE-bench cross-harness input format: {path.suffix}")


def parse_swebench_cross_harness_record(
    record: Record,
    *,
    source_dir: Path | None = None,
    fallback_id: str = "row-1",
) -> ParsedRun:
    instance_id = _instance_id(record, fallback_id=fallback_id)
    normalized_record = _record_with_resolved_patch_path(record, source_dir=source_dir)
    harness = _text(record.get("harness")) or "unknown-harness"

    return ParsedRun(
        source_run_id=_source_run_id(record, instance_id=instance_id, harness=harness),
        instance_key=instance_id,
        description=f"Imported SWE-bench cross-harness artifact {instance_id} from {harness}",
        schema_fit_class="artifact-only",
        observed_fields=dict(normalized_record),
        missing_fields=_missing_fields(record),
        annotations=[
            ParsedAnnotation(
                namespace="swebench_cross_harness.task",
                payload={
                    "instance_id": instance_id,
                    "repo": record.get("repo"),
                    "base_commit": record.get("base_commit"),
                },
            ),
            ParsedAnnotation(
                namespace="swebench_cross_harness.harness",
                payload={
                    "harness": record.get("harness"),
                    "harness_version": record.get("harness_version"),
                    "verdict": record.get("verdict"),
                    "resolved": _boolish(record.get("resolved")),
                    "pass": _boolish(record.get("pass")),
                    "fail": _boolish(record.get("fail")),
                },
            ),
        ],
        resources=_resources(normalized_record),
        reducers=default_reducers(normalized_record),
    )


def _planned_runs(path: Path) -> int:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        return len(data) if isinstance(data, list) else 1
    return 1


def _resources(record: Record) -> list[ParsedResource]:
    resources = [
        ParsedResource(
            name="source-record.json",
            kind="import",
            mime_type="application/json",
            payload=record,
        )
    ]

    patch, patch_path = _patch_payload_or_path(record)
    if patch_path is not None:
        resources.append(
            ParsedResource(
                name="candidate.patch",
                kind="artifact",
                mime_type="text/x-diff",
                path=patch_path,
            )
        )
    elif patch:
        resources.append(
            ParsedResource(
                name="candidate.patch",
                kind="artifact",
                mime_type="text/x-diff",
                payload=patch,
            )
        )

    test_output = _text(record.get("test_output"))
    if test_output:
        resources.append(
            ParsedResource(
                name="test-output.txt",
                kind="report",
                mime_type="text/plain",
                payload=test_output,
            )
        )

    test_log = _text(record.get("test_log"))
    if test_log:
        resources.append(
            ParsedResource(
                name="test-log.txt",
                kind="report",
                mime_type="text/plain",
                payload=test_log,
            )
        )

    return resources


def _record_with_resolved_patch_path(record: Record, *, source_dir: Path | None) -> Record:
    value = record.get("patch_path")
    if value in (None, ""):
        return dict(record)

    path = Path(str(value))
    if not path.is_absolute() and source_dir is not None:
        path = source_dir / path

    normalized = dict(record)
    normalized["patch_path"] = str(path)
    return normalized


def _patch_payload_or_path(record: Record) -> tuple[str, Path | None]:
    patch = _patch_text(record)
    if patch:
        return patch, None

    value = record.get("patch_path")
    if value in (None, ""):
        return "", None

    path = Path(str(value))
    if path.exists() and path.is_file():
        return "", path
    return "", None


def _source_run_id(record: Record, *, instance_id: str, harness: str) -> str:
    explicit = record.get("source_run_id") or record.get("run_id") or record.get("id")
    if explicit is not None:
        return str(explicit)
    return f"swebench-cross-harness:{instance_id}:{harness}"


def _instance_id(record: Record, *, fallback_id: str) -> str:
    value = record.get("instance_id") or record.get("task_id")
    return fallback_id if value is None or value == "" else str(value)


def _missing_fields(record: Record) -> list[str]:
    missing = ["agent_trace"]
    if not any(
        key in record and record.get(key) not in (None, "")
        for key in ("test_environment", "environment", "evaluation_environment")
    ):
        missing.append("test_environment")
    return missing


def _patch_text(record: Record) -> str:
    value = record.get("patch")
    if value in (None, ""):
        value = record.get("diff")
    return "" if value is None else str(value)


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _boolish(value: object) -> object:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "resolved", "pass", "passed"}:
            return True
        if normalized in {"false", "0", "no", "n", "unresolved", "fail", "failed"}:
            return False
    return value


def _as_record(value: object) -> Record:
    if isinstance(value, dict):
        return value
    return {"value": value}
