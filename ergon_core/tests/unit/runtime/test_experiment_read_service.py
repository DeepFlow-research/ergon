from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionTask,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord, RunRecord
from ergon_core.core.application.read_models import experiments as module
from ergon_core.core.application.read_models.experiments import ExperimentReadService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture()
def session_factory():
    _ = BenchmarkDefinitionRecord
    _ = ExperimentDefinition
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
            BenchmarkDefinitionRecord(
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
                    definition_id=experiment_id,
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


def test_read_service_returns_definition_metadata_without_benchmark_definition_record(
    monkeypatch, session_factory
) -> None:
    """``get_experiment`` selects ``ExperimentDefinition`` first.

    A definition row alone (no legacy ``BenchmarkDefinitionRecord``)
    resolves cleanly via the new definition-first path Task 4 added,
    with name/description/metadata sourced from the columns Task 1
    introduced.
    """

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

        # Sanity check: no BenchmarkDefinitionRecord exists for this id.
        assert (
            session.exec(
                select(BenchmarkDefinitionRecord).where(
                    BenchmarkDefinitionRecord.id == definition_id
                )
            ).first()
            is None
        )

    monkeypatch.setattr(module, "get_session", session_factory)

    detail = ExperimentReadService().get_experiment(definition_id)

    assert detail is not None
    assert detail.experiment_id == definition_id
    assert detail.name == "mini-experiment"
    assert detail.description == "smoke for read model"
    assert detail.benchmark_type == "mini"
    assert detail.metadata.get("created_by") == "test"


def test_read_service_falls_back_to_benchmark_definition_record_for_legacy_rows(
    monkeypatch, session_factory
) -> None:
    """Old rows with a ``BenchmarkDefinitionRecord`` but no ``ExperimentDefinition``
    name still resolve via the legacy path until PR 11 deletes the legacy table."""

    legacy_id = uuid4()
    with session_factory() as session:
        session.add(
            BenchmarkDefinitionRecord(
                id=legacy_id,
                name="legacy-only",
                benchmark_type="mini",
                sample_count=0,
            )
        )
        session.commit()

    monkeypatch.setattr(module, "get_session", session_factory)

    detail = ExperimentReadService().get_experiment(legacy_id)
    assert detail is not None
    assert detail.name == "legacy-only"


def test_list_experiments_dedups_definition_and_legacy_with_same_id(
    monkeypatch, session_factory
) -> None:
    """When an ``ExperimentDefinition`` and a ``BenchmarkDefinitionRecord`` share
    an id (transitional state during PR 7 → PR 11), ``list_experiments`` prefers
    the definition's fields and emits a single merged row.
    """

    shared_id = uuid4()
    with session_factory() as session:
        session.add(
            BenchmarkDefinitionRecord(
                id=shared_id,
                name="legacy-name",
                benchmark_type="legacy-type",
                sample_count=0,
            )
        )
        session.add(
            ExperimentDefinition(
                id=shared_id,
                name="definition-name",
                benchmark_type="definition-type",
                metadata_json={},
            )
        )
        session.commit()

    monkeypatch.setattr(module, "get_session", session_factory)

    summaries = ExperimentReadService().list_experiments(limit=10)
    matching = [s for s in summaries if s.experiment_id == shared_id]
    assert len(matching) == 1, "duplicate id should be merged into a single row"
    assert matching[0].name == "definition-name", "definition wins on collision"
    assert matching[0].benchmark_type == "definition-type"
