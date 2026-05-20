from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.views.runs import service as module
from ergon_core.core.views.runs.service import RunReadService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def session_factory():
    _ = ExperimentDefinition
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


def test_list_runs_filters_offsets_and_projects_index_summary(monkeypatch, session_factory) -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    definition_id = uuid4()
    skipped_definition_id = uuid4()
    older_run_id = uuid4()
    matching_run_id = uuid4()
    skipped_run_id = uuid4()

    with session_factory() as session:
        session.add(
            ExperimentDefinition(
                id=definition_id,
                name="MiniWob comparison",
                benchmark_type="miniwob",
                metadata_json={"experiment": "alpha"},
            )
        )
        session.add(
            ExperimentDefinition(
                id=skipped_definition_id,
                name="Other experiment",
                benchmark_type="math",
                metadata_json={},
            )
        )
        session.add(
            RunRecord(
                id=older_run_id,
                definition_id=definition_id,
                benchmark_type="miniwob",
                instance_key="task-old",
                sample_id="sample-old",
                experiment="alpha",
                status=RunStatus.COMPLETED,
                created_at=now - timedelta(hours=2),
            )
        )
        session.add(
            RunRecord(
                id=matching_run_id,
                definition_id=definition_id,
                benchmark_type="miniwob",
                instance_key="task-1",
                sample_id="sample-1",
                experiment="alpha",
                evaluator_slug="judge-v1",
                model_target="openai:gpt-4.1",
                status=RunStatus.COMPLETED,
                created_at=now - timedelta(hours=1),
                started_at=now - timedelta(minutes=55),
                completed_at=now - timedelta(minutes=5),
                summary_json={
                    "name": "alpha task 1",
                    "normalized_score": 0.88,
                    "return": 12.5,
                    "total_cost_usd": 0.42,
                    "metrics": {"pass_rate": 0.9},
                },
            )
        )
        session.add(
            RunRecord(
                id=skipped_run_id,
                definition_id=skipped_definition_id,
                benchmark_type="math",
                instance_key="math-1",
                experiment="beta",
                status=RunStatus.FAILED,
                created_at=now,
            )
        )
        for status in ("completed", "failed", "running"):
            session.add(
                RunGraphNode(
                    run_id=matching_run_id,
                    instance_key="task-1",
                    task_slug=status,
                    description="Task",
                    status=status,
                    created_at=now - timedelta(minutes=50),
                    updated_at=now - timedelta(minutes=10),
                )
            )
        session.commit()

    monkeypatch.setattr(module, "get_session", session_factory)

    summaries = RunReadService().list_runs(
        limit=1,
        offset=0,
        status="completed",
        definition_id=definition_id,
        experiment="alpha",
    )

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.id == matching_run_id
    assert summary.name == "alpha task 1"
    assert summary.definition_id == definition_id
    assert summary.definition_name == "MiniWob comparison"
    assert summary.experiment == "alpha"
    assert summary.benchmark_type == "miniwob"
    assert summary.sample_id == "sample-1"
    assert summary.sample_label == "sample-1"
    assert summary.latest_activity_at == (now - timedelta(minutes=5)).replace(tzinfo=None)
    assert summary.duration_seconds == 3000
    assert summary.final_score == 0.88
    assert summary.return_value == 12.5
    assert summary.total_cost_usd == 0.42
    assert summary.total_tasks == 3
    assert summary.completed_tasks == 1
    assert summary.failed_tasks == 1
    assert summary.running_tasks == 1
    assert summary.evaluator_slug == "judge-v1"
    assert summary.model_target == "openai:gpt-4.1"
    assert summary.metrics == {"pass_rate": 0.9}
