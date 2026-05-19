from datetime import UTC, datetime
from uuid import uuid4

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.application.read_models.cohorts import ExperimentCohortService


def _definition(status: str = "running") -> ExperimentDefinition:
    return ExperimentDefinition(
        id=uuid4(),
        name="ci experiment",
        benchmark_type="ci-benchmark",
        metadata_json={
            "status": status,
            "default_model_target": "openai:gpt-4o",
        },
        created_at=datetime(2026, 4, 27, tzinfo=UTC),
    )


def _run(definition_id, status: RunStatus) -> RunRecord:
    return RunRecord(
        id=uuid4(),
        definition_id=definition_id,
        benchmark_type="ci-benchmark",
        instance_key=str(status),
        worker_team_json={"primary": "ci-worker"},
        evaluator_slug=None,
        model_target="openai:gpt-4o",
        status=status,
        summary_json={},
    )


def test_experiment_row_status_reflects_terminal_run_outcomes() -> None:
    definition = _definition(status="running")

    failed_row = ExperimentCohortService._build_experiment_row(
        definition,
        2,
        [_run(definition.id, RunStatus.FAILED), _run(definition.id, RunStatus.FAILED)],
    )
    completed_row = ExperimentCohortService._build_experiment_row(
        definition,
        2,
        [_run(definition.id, RunStatus.COMPLETED), _run(definition.id, RunStatus.COMPLETED)],
    )
    mixed_row = ExperimentCohortService._build_experiment_row(
        definition,
        2,
        [_run(definition.id, RunStatus.COMPLETED), _run(definition.id, RunStatus.FAILED)],
    )

    assert failed_row.status == "failed"
    assert completed_row.status == "completed"
    assert mixed_row.status == "completed_with_failures"
