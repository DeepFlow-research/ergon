from datetime import UTC, datetime
from uuid import uuid4

from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import ExperimentRecord, RunRecord
from ergon_core.core.runtime.services.cohort_service import ExperimentCohortService


def _experiment(status: str = "running") -> ExperimentRecord:
    return ExperimentRecord(
        id=uuid4(),
        name="ci experiment",
        benchmark_type="ci-benchmark",
        sample_count=2,
        sample_selection_json={"instance_keys": ["a", "b"]},
        default_worker_team_json={"primary": "ci-worker"},
        default_evaluator_slug=None,
        default_model_target="openai:gpt-4o",
        design_json={},
        metadata_json={},
        status=status,
        created_at=datetime(2026, 4, 27, tzinfo=UTC),
    )


def _run(experiment_id, status: RunStatus) -> RunRecord:
    return RunRecord(
        id=uuid4(),
        experiment_id=experiment_id,
        workflow_definition_id=uuid4(),
        benchmark_type="ci-benchmark",
        instance_key=str(status),
        worker_team_json={"primary": "ci-worker"},
        evaluator_slug=None,
        model_target="openai:gpt-4o",
        status=status,
        summary_json={},
    )


def test_experiment_row_status_reflects_terminal_run_outcomes() -> None:
    experiment = _experiment(status="running")

    failed_row = ExperimentCohortService._build_experiment_row(
        experiment,
        [_run(experiment.id, RunStatus.FAILED), _run(experiment.id, RunStatus.FAILED)],
    )
    completed_row = ExperimentCohortService._build_experiment_row(
        experiment,
        [_run(experiment.id, RunStatus.COMPLETED), _run(experiment.id, RunStatus.COMPLETED)],
    )
    mixed_row = ExperimentCohortService._build_experiment_row(
        experiment,
        [_run(experiment.id, RunStatus.COMPLETED), _run(experiment.id, RunStatus.FAILED)],
    )

    assert failed_row.status == "failed"
    assert completed_row.status == "completed"
    assert mixed_row.status == "completed_with_failures"
