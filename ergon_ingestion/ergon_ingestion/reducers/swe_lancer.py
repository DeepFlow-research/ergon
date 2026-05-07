"""Reducers for SWE-Lancer metadata-only task and aggregate records."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

AGGREGATE_FIELDS = [
    "task_id",
    "instance_id",
    "repo",
    "score",
    "resolved",
    "aggregate_metric",
    "rank",
]
TASK_METADATA_FIELDS = [
    "task_id",
    "instance_id",
    "repo",
    "category",
    "difficulty",
    "price",
    "task_prompt",
    "problem_statement",
]


def aggregate_metric_reducer(record: Record) -> ParsedReducer:
    """Preserve source-reported SWE-Lancer aggregate labels without replaying evaluation."""

    return ParsedReducer(
        name="swe_lancer.aggregate_metric",
        kind="original",
        output={
            "task_id": _task_id(record),
            "instance_id": _instance_id(record),
            "repo": record.get("repo"),
            "score": _number_or_none(record.get("score")),
            "resolved": _boolish(record.get("resolved")),
            "aggregate_metric": _number_or_none(record.get("aggregate_metric")),
            "rank": _int_or_none(record.get("rank")),
            "convention": "source_reported_metadata_only_aggregate",
        },
        implementation_ref="ergon_ingestion.reducers.swe_lancer.aggregate_metric_reducer",
        fields_read=AGGREGATE_FIELDS,
        drops=_metadata_only_drops(),
    )


def task_metadata_reducer(record: Record) -> ParsedReducer:
    """Recover task metadata that is useful without importing trajectories or patches."""

    return ParsedReducer(
        name="swe_lancer.task_metadata",
        kind="recovered",
        output={
            "task_id": _task_id(record),
            "instance_id": _instance_id(record),
            "repo": record.get("repo"),
            "category": record.get("category"),
            "difficulty": record.get("difficulty"),
            "price": _number_or_none(record.get("price")),
            "has_task_prompt": bool(_task_prompt(record)),
            "convention": "task_metadata_without_trajectory_or_patch",
        },
        implementation_ref="ergon_ingestion.reducers.swe_lancer.task_metadata_reducer",
        fields_read=TASK_METADATA_FIELDS,
        drops=_metadata_only_drops(),
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [aggregate_metric_reducer(record), task_metadata_reducer(record)]


def _metadata_only_drops() -> list[ParsedDrop]:
    return [
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="swe_lancer_metadata_only_no_full_run_trace",
            dropped_field_path="full_run_trace",
            affected_analysis="swe_lancer.full_trace_analysis",
            declaration_kind="source_missing",
        ),
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="swe_lancer_metadata_only_no_patch_artifact",
            dropped_field_path="patch",
            affected_analysis="swe_lancer.patch_analysis",
            declaration_kind="source_missing",
        ),
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="swe_lancer_metadata_only_no_process_actions",
            dropped_field_path="process_actions",
            affected_analysis="swe_lancer.process_analysis",
            declaration_kind="source_missing",
        ),
        ParsedDrop(
            loss_class="unreproduced_evaluation",
            reason="swe_lancer_metadata_only_no_evaluator_environment",
            dropped_field_path="evaluator_environment",
            affected_analysis="swe_lancer.evaluator_reproduction",
            declaration_kind="author_declared",
        ),
    ]


def _task_id(record: Record) -> str:
    value = record.get("task_id") or record.get("instance_id")
    return "" if value is None else str(value)


def _instance_id(record: Record) -> str:
    value = record.get("instance_id") or record.get("task_id")
    return "" if value is None else str(value)


def _task_prompt(record: Record) -> str:
    value = record.get("task_prompt")
    if value is None or value == "":
        value = record.get("problem_statement")
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
        if normalized == "":
            return None
    return value


def _number_or_none(value: object) -> object:
    if value is None or isinstance(value, int | float):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return None
        try:
            return float(stripped)
        except ValueError:
            return value
    return value


def _int_or_none(value: object) -> object:
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return None
        try:
            return int(stripped)
        except ValueError:
            return value
    return value
