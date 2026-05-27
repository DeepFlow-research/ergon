from datetime import UTC, datetime, timedelta
import json
from typing import Literal, get_args, get_origin
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from ergon_core.core.application.samples.event_views import (
    ALL_SAMPLE_RUNTIME_EVENT_TYPES,
    ROW_MODEL_EVENT_TYPES,
    VIEW_EVENT_TYPES,
    SampleRuntimeEventView,
)
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.experiments.models import ExperimentEnvironmentRow, ExperimentRow
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.samples.models import SampleStatusEventRow, SampleTaskEventRow
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.core.views.samples import service as module
from ergon_core.core.views.samples.service import SampleReadService, SampleSnapshotReadService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


def _sample_runtime_event_view_types() -> tuple[type, ...]:
    union_type = get_args(SampleRuntimeEventView)[0]
    return get_args(union_type)


def _literal_values(annotation: object) -> set[str]:
    if get_origin(annotation) is Literal:
        return set(get_args(annotation))
    return set()


@pytest.fixture()
def session_factory():
    _ = ExperimentDefinition
    _ = ExperimentRow
    _ = ExperimentEnvironmentRow
    _ = SampleGraphNode
    _ = SampleStatusEventRow
    _ = SampleTaskEventRow
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
            SampleRecord(
                id=older_run_id,
                definition_id=definition_id,
                benchmark_type="miniwob",
                instance_key="task-old",
                sample_id="sample-old",
                experiment="alpha",
                status=SampleStatus.COMPLETED,
                created_at=now - timedelta(hours=2),
            )
        )
        session.add(
            SampleRecord(
                id=matching_run_id,
                definition_id=definition_id,
                benchmark_type="miniwob",
                instance_key="task-1",
                sample_id="sample-1",
                experiment="alpha",
                evaluator_slug="judge-v1",
                model_target="openai:gpt-4.1",
                status=SampleStatus.COMPLETED,
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
            SampleRecord(
                id=skipped_run_id,
                definition_id=skipped_definition_id,
                benchmark_type="math",
                instance_key="math-1",
                experiment="beta",
                status=SampleStatus.FAILED,
                created_at=now,
            )
        )
        for status in ("completed", "failed", "running"):
            session.add(
                SampleGraphNode(
                    sample_id=matching_run_id,
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

    summaries = SampleSnapshotReadService().list_samples(
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


def test_failed_run_snapshot_preserves_persisted_final_score(monkeypatch, session_factory) -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    definition_id = uuid4()
    sample_id = uuid4()

    with session_factory() as session:
        session.add(
            ExperimentDefinition(
                id=definition_id,
                name="Failed score experiment",
                benchmark_type="smoke",
                metadata_json={},
            )
        )
        session.add(
            SampleRecord(
                id=sample_id,
                definition_id=definition_id,
                benchmark_type="smoke",
                instance_key="sad-path",
                status=SampleStatus.FAILED,
                started_at=now,
                completed_at=now + timedelta(seconds=9),
                summary_json={"final_score": 0.5},
            )
        )
        session.add(
            SampleGraphNode(
                sample_id=sample_id,
                instance_key="sad-path",
                task_slug="root",
                description="Root task",
                status="failed",
                level=0,
            )
        )
        session.commit()

    monkeypatch.setattr(module, "get_session", session_factory)

    snapshot = SampleSnapshotReadService().build_snapshot(sample_id)

    assert snapshot is not None
    assert snapshot.status == "failed"
    assert snapshot.final_score == 0.5


def test_sample_state_uses_typed_wal_and_graph_projection(session_factory) -> None:
    now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    experiment_id = uuid4()
    environment_id = uuid4()
    sample_id = uuid4()
    task_id = uuid4()

    with session_factory() as session:
        session.add(ExperimentRow(id=experiment_id, name="mixed-training", created_at=now))
        session.add(
            ExperimentEnvironmentRow(
                id=environment_id,
                experiment_id=experiment_id,
                name="mini-validation",
                source_mode="materialized",
            )
        )
        session.add(
            SampleRecord(
                id=sample_id,
                experiment_id=experiment_id,
                environment_id=environment_id,
                sample_key="problem-1",
                sample_ref_json={"id": "problem-1"},
                benchmark_type="experiment",
                instance_key="problem-1",
                status=SampleStatus.PENDING,
                assignment_json={"source_metadata": {"provider": "records"}},
                created_at=now,
            )
        )
        session.add(
            SampleGraphNode(
                sample_id=sample_id,
                task_id=task_id,
                instance_key="problem-1",
                task_slug="solve",
                description="Solve problem 1",
                status="pending",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SampleStatusEventRow(
                sample_id=sample_id,
                event_timestamp=now,
                event_type="sample.status_changed",
                status="pending",
                actor="test",
            )
        )
        session.add(
            SampleTaskEventRow(
                sample_id=sample_id,
                task_id=task_id,
                task_slug="solve",
                event_timestamp=now + timedelta(seconds=1),
                event_type="task.added",
                status="pending",
            )
        )
        session.commit()

        state = SampleReadService(session).get_sample_state(sample_id)

    assert state is not None
    assert state.sample_id == sample_id
    assert state.experiment_id == experiment_id
    assert state.environment_id == environment_id
    assert state.environment_name == "mini-validation"
    assert state.graph.nodes[0].task_slug == "solve"
    assert [event.event_type for event in state.events] == [
        "sample.status_changed",
        "task.added",
    ]
    dumped = state.model_dump(mode="json", by_alias=True)
    assert "GraphMutation" not in json.dumps(dumped)
    assert "runId" not in json.dumps(dumped)


def test_sample_runtime_event_view_union_covers_every_typed_wal_event() -> None:
    union_event_types = {
        event_type
        for view_type in _sample_runtime_event_view_types()
        for event_type in _literal_values(view_type.model_fields["event_type"].annotation)
    }

    assert ROW_MODEL_EVENT_TYPES == ALL_SAMPLE_RUNTIME_EVENT_TYPES
    assert VIEW_EVENT_TYPES == ALL_SAMPLE_RUNTIME_EVENT_TYPES
    assert union_event_types == ALL_SAMPLE_RUNTIME_EVENT_TYPES


def test_sample_runtime_event_view_is_discriminated_by_event_type() -> None:
    schema = TypeAdapter(SampleRuntimeEventView).json_schema(by_alias=True)

    assert schema["discriminator"]["propertyName"] == "eventType"
    assert set(schema["discriminator"]["mapping"]) == ALL_SAMPLE_RUNTIME_EVENT_TYPES
