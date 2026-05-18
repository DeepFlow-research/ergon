from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.application.read_models import experiments as module
from ergon_core.core.application.read_models.experiments import ExperimentReadService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def session_factory():
    _ = ExperimentDefinition
    _ = ExperimentDefinitionInstance
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
    definition_id = uuid4()
    run_a_id = uuid4()
    run_b_id = uuid4()
    run_c_id = uuid4()

    with session_factory() as session:
        session.add(
            ExperimentDefinition(
                id=definition_id,
                name="ci experiment",
                benchmark_type="ci-benchmark",
                metadata_json={
                    "default_worker_team": {"primary": "ci-worker"},
                    "default_evaluator_slug": "ci-evaluator",
                    "default_model_target": "openai:gpt-4o",
                    "status": "running",
                },
                created_at=now,
            )
        )
        for instance_key in ("a", "b", "c"):
            session.add(
                ExperimentDefinitionInstance(
                    experiment_definition_id=definition_id,
                    instance_key=instance_key,
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
                    definition_id=definition_id,
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

    detail = ExperimentReadService().get_experiment(definition_id)

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


def test_read_service_returns_definition_metadata_without_benchmark_definition_record(
    monkeypatch, session_factory
) -> None:
    """``get_experiment`` resolves directly from ``ExperimentDefinition``."""

    definition_id = uuid4()
    with session_factory() as session:
        session.add(
            ExperimentDefinition(
                id=definition_id,
                benchmark_type="mini",
                name="mini-experiment",
                description="smoke for read model",
                metadata_json={"created_by": "test"},
            )
        )
        session.commit()

    monkeypatch.setattr(module, "get_session", session_factory)

    detail = ExperimentReadService().get_experiment(definition_id)

    assert detail is not None
    assert detail.definition_id == definition_id
    assert detail.name == "mini-experiment"
    assert detail.description == "smoke for read model"
    assert detail.benchmark_type == "mini"
    assert detail.metadata.get("created_by") == "test"


def test_read_service_returns_none_for_unknown_definition(monkeypatch, session_factory) -> None:
    monkeypatch.setattr(module, "get_session", session_factory)

    detail = ExperimentReadService().get_experiment(uuid4())
    assert detail is None


def test_list_experiments_reads_definition_rows(monkeypatch, session_factory) -> None:
    definition_id = uuid4()
    with session_factory() as session:
        session.add(
            ExperimentDefinition(
                id=definition_id,
                name="definition-name",
                benchmark_type="definition-type",
                metadata_json={},
            )
        )
        session.commit()

    monkeypatch.setattr(module, "get_session", session_factory)

    summaries = ExperimentReadService().list_experiments(limit=10)
    matching = [s for s in summaries if s.definition_id == definition_id]
    assert len(matching) == 1
    assert matching[0].name == "definition-name"
    assert matching[0].benchmark_type == "definition-type"
