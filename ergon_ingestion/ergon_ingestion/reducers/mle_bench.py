"""Reducers for archived MLE-Bench artifact submissions."""

from ergon_ingestion.models import ParsedDrop, ParsedReducer

Record = dict[str, object]

SCORE_FIELDS = ["submission_id", "competition_id", "score", "score_direction"]
MEDAL_THRESHOLD_FIELDS = ["medal", "medal_thresholds", "score"]


def score_reducer(record: Record) -> ParsedReducer:
    """Preserve the archived leaderboard score without re-executing the submission."""

    return ParsedReducer(
        name="mle_bench.score",
        kind="original",
        output={
            "submission_id": record.get("submission_id"),
            "competition_id": record.get("competition_id"),
            "score": record.get("score"),
            "score_direction": record.get("score_direction"),
            "convention": "archived_artifact_score",
        },
        implementation_ref="ergon_ingestion.reducers.mle_bench.score_reducer",
        fields_read=SCORE_FIELDS,
        drops=_live_execution_drops(),
    )


def medal_threshold_reducer(record: Record) -> ParsedReducer:
    """Expose archived medal and threshold conventions for artifact-only analysis."""

    return ParsedReducer(
        name="mle_bench.medal_threshold",
        kind="recovered",
        output={
            "medal": record.get("medal"),
            "thresholds": record.get("medal_thresholds"),
            "score": record.get("score"),
            "convention": "archived_leaderboard_thresholds",
        },
        implementation_ref="ergon_ingestion.reducers.mle_bench.medal_threshold_reducer",
        fields_read=MEDAL_THRESHOLD_FIELDS,
        drops=_live_execution_drops(),
    )


def default_reducers(record: Record) -> list[ParsedReducer]:
    return [score_reducer(record), medal_threshold_reducer(record)]


def _live_execution_drops() -> list[ParsedDrop]:
    return [
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="live_execution_env_unavailable_for_archived_artifact",
            dropped_field_path="live_reexecution_environment",
            affected_analysis="mle_bench.live_reexecution",
            declaration_kind="source_missing",
        ),
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="live_execution_env_unavailable_for_archived_artifact",
            dropped_field_path="competition_private_test_runtime",
            affected_analysis="mle_bench.live_reexecution",
            declaration_kind="source_missing",
        ),
        ParsedDrop(
            loss_class="unavailable_source_field",
            reason="live_execution_env_unavailable_for_archived_artifact",
            dropped_field_path="container_image",
            affected_analysis="mle_bench.live_reexecution",
            declaration_kind="source_missing",
        ),
    ]
