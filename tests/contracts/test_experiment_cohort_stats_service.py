"""Contract tests for cohort aggregate stats recomputation."""

from h_arcane.core._internal.cohorts.stats_service import experiment_cohort_stats_service
from h_arcane.core._internal.db.models import RunStatus
from tests.utils.cohort_helpers import create_experiment, create_run, resolve_cohort


def test_recompute_aggregates_status_score_duration_and_benchmark_mix(clean_db):
    cohort = resolve_cohort("stats-cohort")
    smoke_experiment = create_experiment("smoke_test", "Smoke Run")
    research_experiment = create_experiment("researchrubrics", "Research Run")

    create_run(
        smoke_experiment.id,
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        status=RunStatus.COMPLETED,
        started_offset_seconds=-20,
        completed_offset_seconds=-10,
        normalized_score=0.25,
    )
    create_run(
        research_experiment.id,
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        status=RunStatus.FAILED,
        started_offset_seconds=-15,
        completed_offset_seconds=-5,
        error_message="boom",
    )
    create_run(
        research_experiment.id,
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        status=RunStatus.EXECUTING,
        started_offset_seconds=-3,
    )

    stats = experiment_cohort_stats_service.recompute(cohort.id)
    extras = stats.parsed_stats_json()

    assert stats.total_runs == 3
    assert stats.completed_runs == 1
    assert stats.failed_runs == 1
    assert stats.executing_runs == 1
    assert stats.failure_rate == 1 / 3
    assert stats.average_score == 0.25
    assert stats.best_score == 0.25
    assert stats.worst_score == 0.25
    assert stats.average_duration_ms == 10000
    assert extras.benchmark_counts["smoke_test"] == 1
    assert extras.benchmark_counts["researchrubrics"] == 2
    assert extras.latest_run_at is not None
