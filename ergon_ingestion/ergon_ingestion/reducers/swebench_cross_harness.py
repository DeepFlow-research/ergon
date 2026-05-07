"""Reducers for SWE-bench cross-harness artifact records."""

from pathlib import Path

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

VERDICT_FIELDS = [
    "instance_id",
    "repo",
    "base_commit",
    "harness",
    "harness_version",
    "verdict",
    "resolved",
    "pass",
    "fail",
    "test_output",
    "test_log",
]
PATCH_FOOTPRINT_FIELDS = [
    "instance_id",
    "harness",
    "patch",
    "diff",
    "patch_path",
    "test_output",
    "test_log",
]


def verdict_reducer(record: Record) -> ParsedReducer:
    """Preserve source-reported cross-harness verdict labels."""

    return ParsedReducer(
        name="swebench_cross_harness.verdict",
        kind="original",
        output={
            "instance_id": _instance_id(record),
            "repo": record.get("repo"),
            "base_commit": record.get("base_commit"),
            "harness": record.get("harness"),
            "harness_version": record.get("harness_version"),
            "verdict": record.get("verdict"),
            "resolved": _boolish(record.get("resolved")),
            "pass": _boolish(record.get("pass")),
            "fail": _boolish(record.get("fail")),
            "has_test_output": bool(_text(record.get("test_output"))),
            "has_test_log": bool(_text(record.get("test_log"))),
            "convention": "source_reported_cross_harness_verdict",
        },
        implementation_ref="ergon_ingestion.reducers.swebench_cross_harness.verdict_reducer",
        fields_read=VERDICT_FIELDS,
        drops=_artifact_drops(record, affected_analysis="swebench_cross_harness.verdict"),
    )


def patch_footprint_reducer(record: Record) -> ParsedReducer:
    """Recover compact patch and test-log footprint fields."""

    patch, patch_source = _patch_with_source(record)
    return ParsedReducer(
        name="swebench_cross_harness.patch_footprint",
        kind="recovered",
        output={
            "instance_id": _instance_id(record),
            "harness": record.get("harness"),
            "has_patch": bool(patch or record.get("patch_path")),
            "patch_source": patch_source,
            "patch_line_count": len(patch.splitlines()) if patch else 0,
            "patch_added_lines": _patch_added_lines(patch),
            "patch_removed_lines": _patch_removed_lines(patch),
            "touched_files": _patch_files(patch),
            "has_test_output": bool(_text(record.get("test_output"))),
            "has_test_log": bool(_text(record.get("test_log"))),
        },
        implementation_ref=(
            "ergon_ingestion.reducers.swebench_cross_harness.patch_footprint_reducer"
        ),
        fields_read=PATCH_FOOTPRINT_FIELDS,
        drops=_artifact_drops(
            record,
            affected_analysis="swebench_cross_harness.patch_footprint",
        ),
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [verdict_reducer(record), patch_footprint_reducer(record)]


def _artifact_drops(record: Record, *, affected_analysis: str) -> list[ParsedDrop]:
    drops = [
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="full_agent_trace_absent_from_cross_harness_artifact",
            dropped_field_path="agent_trace",
            affected_analysis=affected_analysis,
            declaration_kind="source_missing",
        )
    ]
    if not _has_test_environment(record):
        drops.append(
            ParsedDrop(
                loss_class="unavailable_source_field",
                reason="test_environment_metadata_absent_from_record",
                dropped_field_path="test_environment",
                affected_analysis=affected_analysis,
                declaration_kind="source_missing",
            )
        )
    return drops


def _has_test_environment(record: Record) -> bool:
    return any(
        key in record and record.get(key) not in (None, "")
        for key in ("test_environment", "environment", "evaluation_environment")
    )


def _instance_id(record: Record) -> str:
    value = record.get("instance_id") or record.get("task_id")
    return "" if value is None else str(value)


def _patch_with_source(record: Record) -> tuple[str, str | None]:
    value = record.get("patch")
    if value not in (None, ""):
        return str(value), "patch"

    value = record.get("diff")
    if value not in (None, ""):
        return str(value), "diff"

    patch_path = record.get("patch_path")
    if patch_path in (None, ""):
        return "", None

    path = Path(str(patch_path))
    if path.exists() and path.is_file():
        return path.read_text(), "patch_path"
    return "", "patch_path"


def _patch_files(patch: str) -> list[str]:
    files = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                files.append(parts[3].removeprefix("b/"))
    return sorted(set(files))


def _patch_added_lines(patch: str) -> int:
    return sum(
        1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")
    )


def _patch_removed_lines(patch: str) -> int:
    return sum(
        1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---")
    )


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
