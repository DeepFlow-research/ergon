"""Contract tests for the experiment cohort query service."""

from h_arcane.core._internal.cohorts import experiment_cohort_service
from h_arcane.core._internal.cohorts.schemas import UpdateCohortRequest
from h_arcane.core._internal.cohorts.stats_service import experiment_cohort_stats_service
from h_arcane.core._internal.db.models import (
    CohortMetadata,
    DispatchConfigSnapshot,
    ExperimentCohortStatus,
    RunStatus,
)
from tests.utils.cohort_helpers import create_experiment, create_run, resolve_cohort


def test_get_detail_returns_mixed_benchmark_runs_with_cohort_context(clean_db):
    cohort = resolve_cohort(
        "mixed-benchmarks",
        metadata=CohortMetadata(
            model_name="gpt-5",
            dispatch_config=DispatchConfigSnapshot(worker_model="gpt-5", max_questions=7),
        ),
    )
    smoke_experiment = create_experiment("smoke_test", "Smoke Workflow")
    research_experiment = create_experiment("researchrubrics", "Research Workflow")

    create_run(
        smoke_experiment.id,
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        status=RunStatus.EXECUTING,
        started_offset_seconds=-30,
        cli_request_id="req-smoke",
    )
    create_run(
        research_experiment.id,
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        status=RunStatus.COMPLETED,
        started_offset_seconds=-120,
        completed_offset_seconds=-60,
        normalized_score=0.82,
        final_score=0.82,
        cli_request_id="req-research",
    )
    experiment_cohort_stats_service.recompute(cohort.id)

    detail = experiment_cohort_service.get_detail(cohort.id)

    assert detail is not None
    assert detail.summary.name == "mixed-benchmarks"
    assert detail.summary.total_runs == 2
    assert detail.summary.status_counts.executing == 1
    assert detail.summary.status_counts.completed == 1
    assert detail.summary.metadata_summary.model_name == "gpt-5"
    assert detail.summary.metadata_summary.dispatch_config.max_questions == 7
    assert {row.benchmark_name.value for row in detail.runs} == {"smoke_test", "researchrubrics"}
    assert {row.experiment_task_id for row in detail.runs} == {"Smoke Workflow", "Research Workflow"}
    assert {row.cohort_name for row in detail.runs} == {"mixed-benchmarks"}
    assert all(row.running_time_ms is None or row.running_time_ms >= 0 for row in detail.runs)


def test_list_summaries_includes_zero_stats_for_new_cohort(clean_db):
    cohort = resolve_cohort("empty-cohort")

    summaries = experiment_cohort_service.list_summaries()

    matching = next(summary for summary in summaries if summary.cohort_id == cohort.id)
    assert matching.total_runs == 0
    assert matching.failure_rate == 0.0
    assert matching.status_counts.completed == 0


def test_get_detail_preserves_logical_task_ids_for_seeded_dataset_runs(clean_db):
    cohort = resolve_cohort("dataset-cohort")
    minif2f_experiment = create_experiment("minif2f", "amc12a_2008_p25")

    create_run(
        minif2f_experiment.id,
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        status=RunStatus.PENDING,
        cli_request_id="req-minif2f",
    )
    experiment_cohort_stats_service.recompute(cohort.id)

    detail = experiment_cohort_service.get_detail(cohort.id)

    assert detail is not None
    assert len(detail.runs) == 1
    assert detail.runs[0].benchmark_name.value == "minif2f"
    assert detail.runs[0].experiment_task_id == "amc12a_2008_p25"


def test_list_summaries_excludes_archived_cohorts_by_default(clean_db):
    visible = resolve_cohort("visible-cohort")
    archived = resolve_cohort("archived-cohort")
    experiment_cohort_service.update_cohort(
        archived.id,
        UpdateCohortRequest(status=ExperimentCohortStatus.ARCHIVED),
    )

    summaries = experiment_cohort_service.list_summaries(include_archived=False)

    summary_ids = {summary.cohort_id for summary in summaries}
    assert visible.id in summary_ids
    assert archived.id not in summary_ids


def test_update_cohort_can_archive_and_restore(clean_db):
    cohort = resolve_cohort("toggle-archive")

    archived = experiment_cohort_service.archive(cohort.id)
    restored = experiment_cohort_service.unarchive(cohort.id)

    assert archived is not None
    assert archived.status == ExperimentCohortStatus.ARCHIVED
    assert restored is not None
    assert restored.status == ExperimentCohortStatus.ACTIVE
