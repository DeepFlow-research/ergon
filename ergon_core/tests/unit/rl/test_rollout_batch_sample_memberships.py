from uuid import uuid4

import inngest
import pytest
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import (
    RolloutBatch,
    RolloutBatchSampleMembership,
    SampleRecord,
)
from ergon_core.core.rl.rollout_service import RolloutService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(
        engine,
        tables=[
            ExperimentDefinition.__table__,
            SampleRecord.__table__,
            RolloutBatch.__table__,
            RolloutBatchSampleMembership.__table__,
        ],
    )

    def _get_session() -> Session:
        return Session(engine)

    return _get_session


def _service(session_factory) -> RolloutService:
    sent_events: list[inngest.Event] = []
    return RolloutService(
        session_factory=session_factory,
        inngest_send=sent_events.append,
        tokenizer_name="unused",
    )


def _sample(session: Session, *, status: SampleStatus = SampleStatus.PENDING) -> SampleRecord:
    definition = ExperimentDefinition(
        benchmark_type="ci-rollout-membership",
        name="ci-rollout-membership",
        metadata_json={},
    )
    session.add(definition)
    session.flush()
    sample = SampleRecord(
        definition_id=definition.id,
        benchmark_type=definition.benchmark_type,
        instance_key="sample-1",
        status=status,
    )
    session.add(sample)
    session.flush()
    return sample


def test_rollout_batch_sample_membership_uses_sample_ids(session_factory) -> None:
    with session_factory() as session:
        sample = _sample(session)
        sample_id = sample.id
        summary = _service(session_factory).create_rollout_batch(
            session,
            sample_ids=[sample_id],
            definition_id=uuid4(),
        )
        session.commit()

        members = session.exec(select(RolloutBatchSampleMembership)).all()

    assert summary.sample_ids == [sample_id]
    assert [member.sample_id for member in members] == [sample_id]
    assert not hasattr(members[0], "run_id")


def test_rollout_batch_status_is_loaded_by_sample_membership(session_factory) -> None:
    with session_factory() as session:
        sample = _sample(session, status=SampleStatus.EXECUTING)
        sample_id = sample.id
        summary = _service(session_factory).create_rollout_batch(
            session,
            sample_ids=[sample_id],
        )
        session.commit()

        reloaded = _service(session_factory).get_rollout_batch(session, summary.batch_id)

    assert reloaded is not None
    assert reloaded.sample_ids == [sample_id]
    assert reloaded.status.value in {"pending", "running"}
