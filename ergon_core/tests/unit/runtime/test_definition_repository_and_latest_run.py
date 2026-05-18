"""Unit tests for latest_run_for_definition."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from ergon_core.core.application.workflows import runs as runs_module
from ergon_core.core.application.workflows.runs import latest_run_for_definition
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord, RunRecord
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def session_factory():
    _ = BenchmarkDefinitionRecord
    _ = ExperimentDefinition
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _get_session() -> Session:
        return Session(engine)

    return _get_session


def _run(
    *,
    experiment_id: object,
    workflow_definition_id: object,
    created_at: datetime | None = None,
) -> RunRecord:
    return RunRecord(
        id=uuid4(),
        experiment_id=experiment_id,
        workflow_definition_id=workflow_definition_id,
        benchmark_type="ci-benchmark",
        instance_key="k",
        worker_team_json={},
        status=RunStatus.PENDING,
        created_at=created_at or datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_latest_run_for_definition_returns_most_recent(monkeypatch, session_factory) -> None:
    definition_id = uuid4()
    experiment_id = uuid4()

    now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    older = _run(
        experiment_id=experiment_id,
        workflow_definition_id=definition_id,
        created_at=now - timedelta(hours=1),
    )
    newest = _run(
        experiment_id=experiment_id,
        workflow_definition_id=definition_id,
        created_at=now,
    )
    newest_id = newest.id

    with session_factory() as session:
        session.add(
            BenchmarkDefinitionRecord(
                id=experiment_id,
                name="ci",
                benchmark_type="ci-benchmark",
                sample_count=1,
            )
        )
        session.add(
            ExperimentDefinition(
                id=definition_id,
                benchmark_type="ci-benchmark",
                name="ci",
                metadata_json={},
            )
        )
        session.add(older)
        session.add(newest)
        session.commit()

    monkeypatch.setattr(runs_module, "get_session", session_factory)

    result = latest_run_for_definition(definition_id)

    assert result is not None
    assert result.id == newest_id


def test_latest_run_for_definition_ignores_other_definitions(monkeypatch, session_factory) -> None:
    def_a = uuid4()
    def_b = uuid4()
    experiment_id = uuid4()

    now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    run_a = _run(experiment_id=experiment_id, workflow_definition_id=def_a, created_at=now)
    run_b = _run(
        experiment_id=experiment_id,
        workflow_definition_id=def_b,
        created_at=now + timedelta(hours=1),
    )
    run_a_id = run_a.id

    with session_factory() as session:
        session.add(
            BenchmarkDefinitionRecord(
                id=experiment_id,
                name="ci",
                benchmark_type="ci-benchmark",
                sample_count=1,
            )
        )
        session.add(
            ExperimentDefinition(
                id=def_a,
                benchmark_type="ci-benchmark",
                name="ci-a",
                metadata_json={},
            )
        )
        session.add(
            ExperimentDefinition(
                id=def_b,
                benchmark_type="ci-benchmark",
                name="ci-b",
                metadata_json={},
            )
        )
        session.add(run_a)
        session.add(run_b)
        session.commit()

    monkeypatch.setattr(runs_module, "get_session", session_factory)

    result = latest_run_for_definition(def_a)

    assert result is not None
    assert result.id == run_a_id


def test_latest_run_for_definition_returns_none_when_no_runs(monkeypatch, session_factory) -> None:
    definition_id = uuid4()

    monkeypatch.setattr(runs_module, "get_session", session_factory)

    result = latest_run_for_definition(definition_id)

    assert result is None
