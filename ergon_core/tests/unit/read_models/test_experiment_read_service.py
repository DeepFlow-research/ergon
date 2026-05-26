from datetime import UTC, datetime, timedelta
import json
from uuid import uuid4

import pytest
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
    ExperimentDefinitionTask,
)
from ergon_core.core.persistence.experiments.models import (
    ExperimentEnvironmentRow,
    ExperimentRow,
    ExperimentSamplerInvocationRow,
)
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.core.shared.context_parts import (
    AssistantTextPart,
    ContextPartChunkLog,
    ProviderTokenUsage,
    ToolCallPart,
)
from ergon_core.core.views.experiments import service as module
from ergon_core.core.views.experiments.service import ExperimentReadService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def session_factory():
    _ = ExperimentDefinition
    _ = ExperimentDefinitionInstance
    _ = ExperimentDefinitionTask
    _ = SampleContextEvent
    _ = SampleGraphNode
    _ = ExperimentRow
    _ = ExperimentEnvironmentRow
    _ = ExperimentSamplerInvocationRow
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
        for sample_id, instance_key, status, started, completed, score, cost in [
            (run_a_id, "a", SampleStatus.COMPLETED, now, now + timedelta(seconds=10), 1.0, 0.2),
            (run_b_id, "b", SampleStatus.FAILED, now, now + timedelta(seconds=20), 0.0, 0.3),
            (run_c_id, "c", SampleStatus.EXECUTING, now, None, None, None),
        ]:
            session.add(
                SampleRecord(
                    id=sample_id,
                    definition_id=definition_id,
                    benchmark_type="ci-benchmark",
                    instance_key=instance_key,
                    worker_team_json={"primary": "ci-worker"},
                    evaluator_slug="ci-evaluator",
                    model_target="openai:gpt-4o",
                    status=status,
                    started_at=started,
                    completed_at=completed,
                    summary_json=(
                        {
                            "final_score": score,
                            "total_cost_usd": cost,
                            "cost_observed": True,
                        }
                        if score is not None and cost is not None
                        else {}
                    ),
                )
            )
            for index in range(2):
                session.add(
                    SampleGraphNode(
                        sample_id=sample_id,
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


def test_experiment_run_rows_project_nested_metrics(monkeypatch, session_factory) -> None:
    now = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)
    definition_id = uuid4()
    sample_id = uuid4()
    execution_id = uuid4()

    with session_factory() as session:
        session.add(
            ExperimentDefinition(
                id=definition_id,
                name="metric experiment",
                benchmark_type="metric-benchmark",
                metadata_json={},
                created_at=now,
            )
        )
        session.add(
            SampleRecord(
                id=sample_id,
                definition_id=definition_id,
                benchmark_type="metric-benchmark",
                instance_key="sample-1",
                sample_id="sample label",
                worker_team_json={"primary": "ci-worker"},
                evaluator_slug="metric-evaluator",
                model_target="openai:gpt-4o",
                status=SampleStatus.COMPLETED,
                started_at=now,
                completed_at=now + timedelta(seconds=3),
                summary_json={
                    "normalized_score": 0.75,
                    "total_cost_usd": 0.0,
                    "error_message": "ignored because run succeeded",
                },
            )
        )
        session.add(
            SampleGraphNode(
                sample_id=sample_id,
                instance_key="sample-1",
                task_slug="root",
                description="Task",
                status="completed",
                assigned_worker_slug="ci-worker",
                level=0,
            )
        )
        session.add(
            SampleContextEvent(
                sample_id=sample_id,
                task_execution_id=execution_id,
                worker_binding_key="ci-worker",
                sequence=0,
                event_type="assistant_text",
                payload=ContextPartChunkLog(
                    part=AssistantTextPart(content="answer"),
                    sequence=0,
                    worker_binding_key="ci-worker",
                    provider_usage=ProviderTokenUsage(completion_tokens=9),
                ).model_dump(mode="json"),
            )
        )
        session.add(
            SampleContextEvent(
                sample_id=sample_id,
                task_execution_id=execution_id,
                worker_binding_key="ci-worker",
                sequence=1,
                event_type="tool_call",
                payload=ContextPartChunkLog(
                    part=ToolCallPart(
                        tool_call_id="call-1",
                        tool_name="search",
                        args={"q": "x"},
                    ),
                    token_ids=[1, 2, 3],
                    sequence=1,
                    worker_binding_key="ci-worker",
                ).model_dump(mode="json"),
            )
        )
        session.commit()

    monkeypatch.setattr(module, "get_session", session_factory)

    detail = ExperimentReadService().get_experiment(definition_id)

    assert detail is not None
    row = detail.runs[0]
    assert row.running_time_ms == 3_000
    assert row.total_cost_usd is None
    assert row.metrics.sample_id == sample_id
    assert row.metrics.run_name == "sample label"
    assert row.metrics.status == "completed"
    assert row.metrics.sample_label == "sample label"
    assert row.metrics.instance_key == "sample-1"
    assert row.metrics.score == 0.75
    assert row.metrics.return_value == 0.75
    assert row.metrics.duration_ms == 3_000
    assert row.metrics.total_tasks == 1
    assert row.metrics.tool_call_count == 1
    assert row.metrics.total_tokens == 12
    assert row.metrics.token_breakdown["assistant_text"] == 9
    assert row.metrics.token_breakdown["tool_call"] == 3
    assert row.metrics.total_cost_usd is None
    assert row.metrics.cost_observed is False
    assert row.metrics.model_target == "openai:gpt-4o"
    assert row.metrics.evaluator_slug == "metric-evaluator"
    assert row.metrics.error_summary is None


def test_experiment_state_contains_environments_samples_and_invocations(session_factory) -> None:
    now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    experiment_id = uuid4()
    environment_id = uuid4()
    sample_id = uuid4()

    with session_factory() as session:
        session.add(
            ExperimentRow(
                id=experiment_id,
                name="mixed-training",
                metadata_json={"purpose": "test"},
                created_at=now,
            )
        )
        session.add(
            ExperimentEnvironmentRow(
                id=environment_id,
                experiment_id=experiment_id,
                name="mini-validation",
                source_mode="materialized",
                source_metadata_json={"provider": "records"},
            )
        )
        session.add(
            ExperimentSamplerInvocationRow(
                experiment_id=experiment_id,
                sampler_name="random",
                requested_k=1,
                candidate_pool_size=4,
                selected_count=1,
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
                status=SampleStatus.COMPLETED,
                assignment_json={"source_metadata": {"split": "validation"}},
            )
        )
        session.commit()

        state = ExperimentReadService(session).get_experiment_state(experiment_id)

    assert state is not None
    assert state.experiment_id == experiment_id
    assert state.environments[0].environment_name == "mini-validation"
    assert state.environments[0].sample_count == 1
    assert state.sample_count == 1
    assert state.samples[0].sample_id == sample_id
    assert state.sampler_invocations[0].sampler_name == "random"
    dumped = state.model_dump(mode="json", by_alias=True)
    assert "definitionId" not in json.dumps(dumped)
    assert "runId" not in json.dumps(dumped)


def test_experiment_detail_groups_runs_by_experiment_tag(monkeypatch, session_factory) -> None:
    definition_a = uuid4()
    definition_b = uuid4()
    grouped_run_a = uuid4()
    grouped_run_b = uuid4()
    ungrouped_run = uuid4()

    with session_factory() as session:
        session.add(
            ExperimentDefinition(
                id=definition_a,
                name="arm-a",
                benchmark_type="ci-benchmark",
                metadata_json={"experiment": "group-alpha"},
            )
        )
        session.add(
            ExperimentDefinition(
                id=definition_b,
                name="arm-b",
                benchmark_type="ci-benchmark",
                metadata_json={"experiment": "group-alpha"},
            )
        )
        for sample_id, definition_id, experiment in (
            (grouped_run_a, definition_a, "group-alpha"),
            (grouped_run_b, definition_b, "group-alpha"),
            (ungrouped_run, definition_a, "other-group"),
        ):
            session.add(
                SampleRecord(
                    id=sample_id,
                    definition_id=definition_id,
                    benchmark_type="ci-benchmark",
                    instance_key=str(sample_id),
                    worker_team_json={},
                    experiment=experiment,
                    status=SampleStatus.COMPLETED,
                )
            )
        session.commit()

    monkeypatch.setattr(module, "get_session", session_factory)

    detail = ExperimentReadService().get_experiment(definition_a)

    assert detail is not None
    assert {run.sample_id for run in detail.runs} == {grouped_run_a, grouped_run_b}
    assert detail.experiment.run_count == 2
    assert detail.analytics.total_runs == 2


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


def test_list_experiments_projects_aggregate_lifecycle_status(monkeypatch, session_factory) -> None:
    definition_id = uuid4()
    with session_factory() as session:
        session.add(
            ExperimentDefinition(
                id=definition_id,
                name="finished-with-failure",
                benchmark_type="ci-benchmark",
                metadata_json={},
            )
        )
        for index, status in enumerate(
            (SampleStatus.COMPLETED, SampleStatus.COMPLETED, SampleStatus.FAILED)
        ):
            session.add(
                SampleRecord(
                    definition_id=definition_id,
                    benchmark_type="ci-benchmark",
                    instance_key=f"sample-{index}",
                    worker_team_json={},
                    status=status,
                )
            )
        session.commit()

    monkeypatch.setattr(module, "get_session", session_factory)

    summaries = ExperimentReadService().list_experiments(limit=10)
    matching = [s for s in summaries if s.definition_id == definition_id]

    assert len(matching) == 1
    assert matching[0].status == "failed"
