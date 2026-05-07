"""Reducers for SWE-smith patch-row records."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

RESOLVED_FIELDS = [
    "instance_id",
    "task_id",
    "eval_status",
    "resolved",
    "evaluation.resolved",
    "evaluation.status",
]
PATCH_RECORD_FIELDS = [
    "instance_id",
    "task_id",
    "repo",
    "base_commit",
    "patch",
    "diff",
    "generator",
    "generator_metadata",
]


def resolved_reducer(record: Record) -> ParsedReducer:
    """Preserve source-reported SWE-smith outcome labels without reproducing evaluation."""

    return ParsedReducer(
        name="swe_smith.resolved",
        kind="original",
        output={
            "instance_id": _instance_id(record),
            "resolved": _resolved_value(record),
            "eval_status": _eval_status(record),
            "convention": "source_reported_outcome",
        },
        implementation_ref="ergon_ingestion.reducers.swe_smith.resolved_reducer",
        fields_read=RESOLVED_FIELDS,
        drops=_common_drops(),
    )


def patch_record_reducer(record: Record) -> ParsedReducer:
    """Recover repo/base/patch metadata from public task or patch rows."""

    patch = _patch_text(record)
    return ParsedReducer(
        name="swe_smith.patch_record",
        kind="recovered",
        output={
            "instance_id": _instance_id(record),
            "repo": record.get("repo"),
            "base_commit": record.get("base_commit"),
            "has_patch": bool(patch),
            "patch_bytes": len(patch.encode()),
            "generator": _generator_metadata(record),
            "convention": "patch_row_record",
        },
        implementation_ref="ergon_ingestion.reducers.swe_smith.patch_record_reducer",
        fields_read=PATCH_RECORD_FIELDS,
        drops=_common_drops(),
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [resolved_reducer(record), patch_record_reducer(record)]


def _common_drops() -> list[ParsedDrop]:
    return [
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="full_interaction_trace_absent_from_patch_row",
            dropped_field_path="interaction_trace",
            affected_analysis="swe_smith.full_trace_analysis",
            declaration_kind="source_missing",
        ),
        ParsedDrop(
            loss_class="unreproduced_evaluation",
            reason="trusts_source_eval_status_without_reproducing_evaluator",
            dropped_field_path="evaluation",
            affected_analysis="swe_smith.resolved",
            declaration_kind="author_declared",
        ),
    ]


def _instance_id(record: Record) -> str:
    value = record.get("instance_id") or record.get("task_id")
    return "" if value is None else str(value)


def _patch_text(record: Record) -> str:
    value = record.get("patch")
    if value is None:
        value = record.get("diff")
    return "" if value is None else str(value)


def _generator_metadata(record: Record) -> object:
    if "generator" in record:
        return record.get("generator")
    return record.get("generator_metadata")


def _eval_status(record: Record) -> object:
    if "eval_status" in record:
        return record.get("eval_status")

    evaluation = record.get("evaluation")
    if isinstance(evaluation, dict):
        return evaluation.get("status")
    return None


def _resolved_value(record: Record) -> object:
    if "resolved" in record:
        return _boolish(record.get("resolved"))

    evaluation = record.get("evaluation")
    if isinstance(evaluation, dict) and "resolved" in evaluation:
        return _boolish(evaluation.get("resolved"))
    return None


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
