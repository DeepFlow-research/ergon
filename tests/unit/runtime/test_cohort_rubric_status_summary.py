"""Cohort row rubric status summaries."""

from uuid import uuid4

import ergon_core.api as _ergon_api
from ergon_core.core.persistence.telemetry.evaluation_summary import (
    CriterionResultEntry,
    EvaluationSummary,
)
from ergon_core.core.persistence.telemetry.models import ExperimentCohort, RunRecord
from ergon_core.core.runtime.services.cohort_service import (
    ExperimentCohortService,
    _rubric_status_summary,
)


def _summary(
    evaluator_name: str,
    statuses: list[str],
) -> EvaluationSummary:
    return EvaluationSummary(
        evaluator_name=evaluator_name,
        max_score=float(len(statuses)),
        normalized_score=0.0,
        stages_evaluated=1,
        stages_passed=0,
        criterion_results=[
            CriterionResultEntry(
                criterion_name=f"{status}-criterion",
                criterion_type="test-criterion",
                stage_num=0,
                stage_name="default",
                criterion_num=index,
                status=status,
                score=1.0 if status == "passed" else 0.0,
                max_score=1.0,
                passed=status == "passed",
                weight=1.0,
                contribution=1.0 if status == "passed" else 0.0,
                criterion_description=f"{status} criterion",
            )
            for index, status in enumerate(statuses)
        ],
    )


def test_rubric_status_summary_prioritizes_errors_then_failures() -> None:
    summary = _rubric_status_summary(
        [
            _summary("default", ["passed", "failed"]),
            _summary("post-root", ["errored", "skipped"]),
        ]
    )

    assert summary.status == "errored"
    assert summary.total_criteria == 4
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.errored == 1
    assert summary.skipped == 1
    assert summary.criterion_statuses == ["passed", "failed", "errored", "skipped"]
    assert summary.evaluator_names == ["default", "post-root"]


def test_rubric_status_summary_reports_none_for_no_criteria() -> None:
    summary = _rubric_status_summary([])

    assert summary.status == "none"
    assert summary.total_criteria == 0
    assert summary.criterion_statuses == []
    assert summary.evaluator_names == []


def test_cohort_run_row_requires_rubric_status_summary() -> None:
    cohort = ExperimentCohort(name="cohort")
    run = RunRecord(
        id=uuid4(),
        experiment_definition_id=uuid4(),
        cohort_id=cohort.id,
        status="completed",
    )
    summary = _rubric_status_summary([_summary("default", ["failed"])])

    row = ExperimentCohortService._build_run_row(
        cohort,
        run,
        total_tasks=1,
        rubric_status_summary=summary,
    )

    assert row.rubric_status_summary.status == "failing"
    assert row.rubric_status_summary.total_criteria == 1
    assert row.rubric_status_summary.failed == 1
