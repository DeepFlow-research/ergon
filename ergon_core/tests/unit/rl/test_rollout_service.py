from uuid import uuid4

import inngest
import pytest
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.telemetry.models import (
    BenchmarkDefinitionRecord,
    RolloutBatch,
    RolloutBatchRun,
    RunRecord,
)
from ergon_core.core.rl.rollout_service import RolloutService
from ergon_core.core.rl.rollout_types import SubmitRequest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture()
def session_factory():
    _ = BenchmarkDefinitionRecord
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(
        engine,
        tables=[
            ExperimentDefinition.__table__,
            RunRecord.__table__,
            RolloutBatch.__table__,
            RolloutBatchRun.__table__,
            BenchmarkDefinitionRecord.__table__,
        ],
    )

    def _get_session() -> Session:
        return Session(engine)

    return _get_session


def test_rollout_submit_uses_rollout_batch_and_run_definition_without_legacy_record(
    session_factory,
) -> None:
    sent_events: list[inngest.Event] = []
    definition_id = uuid4()
    with session_factory() as session:
        session.add(
            ExperimentDefinition(
                id=definition_id,
                benchmark_type="ci-benchmark",
                name="ci definition",
                metadata_json={},
            )
        )
        session.commit()

    service = RolloutService(
        session_factory=session_factory,
        inngest_send=sent_events.append,
        tokenizer_name="unused-in-submit",
    )

    response = service.submit(
        SubmitRequest(
            definition_id=definition_id,
            num_episodes=2,
            model_target_override="openai:test",
        )
    )

    with session_factory() as session:
        legacy_rows = list(session.exec(select(BenchmarkDefinitionRecord)).all())
        batch = session.get(RolloutBatch, response.batch_id)
        runs = list(session.exec(select(RunRecord)).all())

    assert legacy_rows == []
    assert batch is not None
    assert batch.definition_id == definition_id
    assert {run.definition_id for run in runs} == {definition_id}
    assert {run.model_target for run in runs} == {"openai:test"}
    assert len(sent_events) == 2
