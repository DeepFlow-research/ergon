from datetime import UTC, datetime
import json
from uuid import uuid4

import pytest
from ergon_core.core.persistence.experiments.models import (
    ExperimentEnvironmentRow,
    ExperimentRow,
    ExperimentSamplerInvocationRow,
)
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.core.views.experiments.service import ExperimentReadService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def session_factory():
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
    assert state.environments[0].environment_id == environment_id
    assert state.environments[0].environment_name == "mini-validation"
    assert state.environments[0].sample_count == 1
    assert state.environments[0].selected_count == 1
    assert state.sample_count == 1
    assert state.samples[0].sample_id == sample_id
    assert state.samples[0].experiment_id == experiment_id
    assert state.samples[0].environment_id == environment_id
    assert state.samples[0].sample_key == "problem-1"
    assert state.samples[0].sample_ref == {"id": "problem-1"}
    assert state.samples[0].source_metadata == {"split": "validation"}
    assert state.sampler_invocations[0].sampler_name == "random"
    dumped = state.model_dump(mode="json", by_alias=True)
    assert "definitionId" not in json.dumps(dumped)
    assert "runId" not in json.dumps(dumped)


def test_list_experiment_states_reads_experiment_rows_without_sample_payloads(
    session_factory,
) -> None:
    now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    experiment_id = uuid4()
    environment_id = uuid4()
    sample_id = uuid4()

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
                benchmark_type="experiment",
                instance_key="problem-1",
                status=SampleStatus.COMPLETED,
            )
        )
        session.commit()

        states = ExperimentReadService(session).list_experiment_states(limit=10)

    assert len(states.items) == 1
    state = states.items[0]
    assert state.experiment_id == experiment_id
    assert state.name == "mixed-training"
    assert state.sample_count == 1
    assert state.environments[0].environment_id == environment_id
    assert state.samples == []


def test_list_experiment_samples_returns_none_for_unknown_experiment(session_factory) -> None:
    with session_factory() as session:
        samples = ExperimentReadService(session).list_experiment_samples(uuid4())

    assert samples is None
