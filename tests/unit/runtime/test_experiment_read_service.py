from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from ergon_core.core.persistence.definitions.models import ExperimentDefinitionTask
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import ExperimentRecord, RunRecord
from ergon_core.core.runtime.services import experiment_read_service as module
from ergon_core.core.runtime.services.experiment_read_service import ExperimentReadService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def session_factory():
    _ = ExperimentRecord
    _ = ExperimentDefinitionTask
    _ = RunGraphNode
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _get_session() -> Session:
        return Session(engine)

    return _get_session


def test_experiment_detail_aggregates_run_analytics(monkeypatch, session_factory) -> None:
    now = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)
    experiment_id = uuid4()
    definition_id = uuid4()
    run_a_id = uuid4()
    run_b_id = uuid4()
    run_c_id = uuid4()

    with session_factory() as session:
        session.add(
            ExperimentRecord(
                id=experiment_id,
                name="ci experiment",
                benchmark_type="ci-benchmark",
                sample_count=3,
                sample_selection_json={"instance_keys": ["a", "b", "c"]},
                default_worker_team_json={"primary": "ci-worker"},
                default_evaluator_slug="ci-evaluator",
                default_model_target="openai:gpt-4o",
                design_json={},
                metadata_json={},
                status="running",
                created_at=now,
            )
        )
        for run_id, instance_key, status, started, completed, score, cost in [
            (run_a_id, "a", RunStatus.COMPLETED, now, now + timedelta(seconds=10), 1.0, 0.2),
            (run_b_id, "b", RunStatus.FAILED, now, now + timedelta(seconds=20), 0.0, 0.3),
            (run_c_id, "c", RunStatus.EXECUTING, now, None, None, None),
        ]:
            session.add(
                RunRecord(
                    id=run_id,
                    experiment_id=experiment_id,
                    workflow_definition_id=definition_id,
                    benchmark_type="ci-benchmark",
                    instance_key=instance_key,
                    worker_team_json={"primary": "ci-worker"},
                    evaluator_slug="ci-evaluator",
                    model_target="openai:gpt-4o",
                    status=status,
                    started_at=started,
                    completed_at=completed,
                    summary_json=(
                        {"final_score": score, "total_cost_usd": cost}
                        if score is not None and cost is not None
                        else {}
                    ),
                )
            )
            for index in range(2):
                session.add(
                    RunGraphNode(
                        run_id=run_id,
                        instance_key=instance_key,
                        task_slug=f"{instance_key}-{index}",
                        description="Task",
                        status="completed",
                        assigned_worker_slug="ci-worker",
                        level=index,
                    )
                )
        session.commit()

    monkeypatch.setattr(module, "get_session", session_factory)

    detail = ExperimentReadService().get_experiment(experiment_id)

    assert detail is not None
    assert detail.analytics.total_runs == 3
    assert detail.analytics.status_counts.completed == 1
    assert detail.analytics.status_counts.failed == 1
    assert detail.analytics.status_counts.executing == 1
    assert detail.analytics.average_score == 0.5
    assert detail.analytics.average_duration_ms == 15_000
    assert detail.analytics.average_tasks == 2.0
    assert detail.analytics.total_cost_usd == 0.5
    assert detail.runs[0].running_time_ms == 10_000
    assert detail.runs[0].total_tasks == 2
