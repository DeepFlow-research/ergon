from datetime import UTC, datetime
from uuid import UUID, uuid4

import inngest
import pytest
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.enums import SampleStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RolloutBatch,
    RolloutBatchSampleMembership,
    SampleRecord,
    SampleTaskAttempt,
)
from ergon_core.core.rl.rollout_service import RolloutService
from ergon_core.core.shared.context_parts import (
    AssistantTextPart,
    ContextPartChunkLog,
    TokenLogprob,
    UserMessagePart,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


TRAINER_SAMPLE_ID = UUID("90000000-0000-0000-0000-000000000000")
TRAINER_TASK_ID = UUID("90000000-0000-0000-0000-000000000001")
TRAINER_ATTEMPT_ID = UUID("90000000-0000-0000-0000-000000000002")
T0 = datetime(2026, 5, 28, 14, 0, tzinfo=UTC)


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

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


def _payload(part, sequence: int, *, token_ids=None, logprobs=None) -> dict:
    return ContextPartChunkLog(
        part=part,
        token_ids=token_ids,
        logprobs=logprobs,
        sequence=sequence,
        worker_binding_key="planner",
        turn_id=f"trainer-{sequence}",
    ).model_dump(mode="json")


def _seed_completed_sample(session: Session) -> None:
    session.add(
        SampleRecord(
            id=TRAINER_SAMPLE_ID,
            benchmark_type="unit",
            instance_key="trainer",
            status=SampleStatus.COMPLETED,
            summary_json={"normalized_score": 0.75},
        )
    )
    session.add(
        SampleGraphNode(
            sample_id=TRAINER_SAMPLE_ID,
            task_id=TRAINER_TASK_ID,
            instance_key="trainer",
            task_slug="root",
            description="Root",
            status="completed",
            assigned_worker_slug="planner",
        )
    )
    session.add(
        SampleTaskAttempt(
            id=TRAINER_ATTEMPT_ID,
            sample_id=TRAINER_SAMPLE_ID,
            task_id=TRAINER_TASK_ID,
            status=TaskExecutionStatus.COMPLETED,
        )
    )
    session.add_all(
        [
            SampleContextEvent(
                sample_id=TRAINER_SAMPLE_ID,
                task_attempt_id=TRAINER_ATTEMPT_ID,
                worker_binding_key="planner",
                sequence=1,
                event_type="user_message",
                payload=_payload(
                    UserMessagePart(content="parent prompt"),
                    1,
                    token_ids=[11, 12, 13],
                ),
                created_at=T0,
            ),
            SampleContextEvent(
                sample_id=TRAINER_SAMPLE_ID,
                task_attempt_id=TRAINER_ATTEMPT_ID,
                worker_binding_key="planner",
                sequence=2,
                event_type="assistant_text",
                payload=_payload(
                    AssistantTextPart(content="parent answer"),
                    2,
                    token_ids=[21, 22],
                    logprobs=[
                        TokenLogprob(token="parent", logprob=-0.31),
                        TokenLogprob(token=" answer", logprob=-0.42),
                    ],
                ),
                created_at=T0,
            ),
        ]
    )
    session.commit()


def test_rollout_poll_returns_projected_parent_visible_training_records(session_factory) -> None:
    with session_factory() as session:
        _seed_completed_sample(session)
        summary = _service(session_factory).create_rollout_batch(
            session,
            sample_ids=[TRAINER_SAMPLE_ID],
        )
        session.commit()

    response = _service(session_factory).poll(summary.batch_id)

    assert response is not None
    assert not hasattr(response, "trajectories")
    assert len(response.training_records) == 1
    record = response.training_records[0]
    assert record.sample_id == TRAINER_SAMPLE_ID
    assert record.actor.actor_slug == "planner"
    assert record.prompt_ids == [11, 12, 13]
    assert record.completion_ids == [21, 22]
    assert record.logprobs == [-0.31, -0.42]
    assert record.reward == 0.75


def test_rollout_poll_uses_sample_level_normalized_reward(session_factory) -> None:
    with session_factory() as session:
        _seed_completed_sample(session)
        summary = _service(session_factory).create_rollout_batch(
            session,
            sample_ids=[TRAINER_SAMPLE_ID],
        )
        session.commit()

    response = _service(session_factory).poll(summary.batch_id)

    assert response is not None
    assert {record.reward for record in response.training_records} == {0.75}
