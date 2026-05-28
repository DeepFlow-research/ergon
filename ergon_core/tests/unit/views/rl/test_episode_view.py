from datetime import UTC, datetime, timedelta
from uuid import UUID

from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.enums import SampleStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord, SampleTaskAttempt
from ergon_core.core.shared.context_parts import (
    AssistantTextPart,
    ContextPartChunkLog,
    SystemPromptPart,
    ThinkingPart,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)
from ergon_core.core.views.rl.episode import RlEpisodeReadService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


SAMPLE_ID = UUID("10000000-0000-0000-0000-000000000000")
ROOT_TASK_ID = UUID("20000000-0000-0000-0000-000000000000")
CHILD_TASK_ID = UUID("30000000-0000-0000-0000-000000000000")
ROOT_ATTEMPT_1 = UUID("40000000-0000-0000-0000-000000000001")
ROOT_ATTEMPT_2 = UUID("40000000-0000-0000-0000-000000000002")
CHILD_ATTEMPT_1 = UUID("50000000-0000-0000-0000-000000000001")
T0 = datetime(2026, 5, 28, 11, 0, tzinfo=UTC)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _payload(part, sequence: int, worker: str) -> dict:
    return ContextPartChunkLog(
        part=part,
        sequence=sequence,
        worker_binding_key=worker,
        turn_id=f"{worker}-turn-{sequence}",
    ).model_dump(mode="json")


def _event(
    *,
    attempt_id: UUID,
    worker: str,
    sequence: int,
    event_type: str,
    part,
) -> SampleContextEvent:
    return SampleContextEvent(
        sample_id=SAMPLE_ID,
        task_attempt_id=attempt_id,
        worker_binding_key=worker,
        sequence=sequence,
        event_type=event_type,
        payload=_payload(part, sequence, worker),
        created_at=T0 + timedelta(seconds=sequence),
    )


def _seed_episode_fixture(session: Session) -> None:
    session.add(
        SampleRecord(
            id=SAMPLE_ID,
            benchmark_type="unit",
            instance_key="episode-fixture",
            status=SampleStatus.COMPLETED,
        )
    )
    session.add_all(
        [
            SampleGraphNode(
                sample_id=SAMPLE_ID,
                task_id=ROOT_TASK_ID,
                instance_key="episode-fixture",
                task_slug="root",
                description="Root",
                status="completed",
                assigned_worker_slug="planner",
                level=0,
                created_at=T0,
                updated_at=T0,
            ),
            SampleGraphNode(
                sample_id=SAMPLE_ID,
                task_id=CHILD_TASK_ID,
                instance_key="episode-fixture",
                task_slug="child",
                description="Child",
                status="completed",
                assigned_worker_slug="researcher",
                parent_task_id=ROOT_TASK_ID,
                level=1,
                created_at=T0 + timedelta(seconds=1),
                updated_at=T0 + timedelta(seconds=1),
            ),
        ]
    )
    session.add_all(
        [
            SampleTaskAttempt(
                id=ROOT_ATTEMPT_1,
                sample_id=SAMPLE_ID,
                task_id=ROOT_TASK_ID,
                status=TaskExecutionStatus.FAILED,
                started_at=T0,
                completed_at=T0 + timedelta(seconds=10),
            ),
            SampleTaskAttempt(
                id=ROOT_ATTEMPT_2,
                sample_id=SAMPLE_ID,
                task_id=ROOT_TASK_ID,
                status=TaskExecutionStatus.COMPLETED,
                started_at=T0 + timedelta(seconds=11),
                completed_at=T0 + timedelta(seconds=20),
            ),
            SampleTaskAttempt(
                id=CHILD_ATTEMPT_1,
                sample_id=SAMPLE_ID,
                task_id=CHILD_TASK_ID,
                status=TaskExecutionStatus.COMPLETED,
                started_at=T0 + timedelta(seconds=4),
                completed_at=T0 + timedelta(seconds=9),
            ),
        ]
    )
    session.add_all(
        [
            _event(
                attempt_id=ROOT_ATTEMPT_2,
                worker="planner",
                sequence=1,
                event_type="system_prompt",
                part=SystemPromptPart(content="SYSTEM_EPISODE_SENTINEL"),
            ),
            _event(
                attempt_id=ROOT_ATTEMPT_2,
                worker="planner",
                sequence=2,
                event_type="user_message",
                part=UserMessagePart(content="USER_EPISODE_SENTINEL"),
            ),
            _event(
                attempt_id=ROOT_ATTEMPT_2,
                worker="planner",
                sequence=3,
                event_type="thinking",
                part=ThinkingPart(content="THINKING_EPISODE_SENTINEL"),
            ),
            _event(
                attempt_id=ROOT_ATTEMPT_2,
                worker="planner",
                sequence=4,
                event_type="tool_call",
                part=ToolCallPart(
                    tool_call_id="spawn-1",
                    tool_name="spawn_task",
                    args={"prompt": "SPAWN_CHILD_SENTINEL"},
                ),
            ),
            _event(
                attempt_id=ROOT_ATTEMPT_2,
                worker="planner",
                sequence=5,
                event_type="tool_result",
                part=ToolResultPart(
                    tool_call_id="spawn-1",
                    tool_name="spawn_task",
                    content="CHILD_RESULT_PARENT_VISIBLE_SENTINEL",
                ),
            ),
            _event(
                attempt_id=ROOT_ATTEMPT_2,
                worker="planner",
                sequence=6,
                event_type="assistant_text",
                part=AssistantTextPart(content="ASSISTANT_EPISODE_SENTINEL"),
            ),
            _event(
                attempt_id=CHILD_ATTEMPT_1,
                worker="researcher",
                sequence=1,
                event_type="thinking",
                part=ThinkingPart(content="CHILD_INTERNAL_THINKING_SENTINEL"),
            ),
            _event(
                attempt_id=CHILD_ATTEMPT_1,
                worker="researcher",
                sequence=2,
                event_type="assistant_text",
                part=AssistantTextPart(content="CHILD_INTERNAL_ACTION_SENTINEL"),
            ),
        ]
    )
    session.commit()


def _texts(steps) -> list[str]:
    return [step.text for step in steps]


def test_get_episode_returns_one_root_task_for_sample() -> None:
    session = _session()
    _seed_episode_fixture(session)

    episode = RlEpisodeReadService(session).get_episode(SAMPLE_ID)

    assert episode.sample_id == SAMPLE_ID
    assert len(episode.root_tasks) == 1


def test_child_graph_node_is_nested_under_parent_task() -> None:
    session = _session()
    _seed_episode_fixture(session)

    root = RlEpisodeReadService(session).get_episode(SAMPLE_ID).root_tasks[0]

    assert [child.task_id for child in root.children] == [CHILD_TASK_ID]
    assert root.children[0].actor.actor_slug == "researcher"


def test_multiple_attempts_remain_distinct_under_one_task() -> None:
    session = _session()
    _seed_episode_fixture(session)

    root = RlEpisodeReadService(session).get_episode(SAMPLE_ID).root_tasks[0]

    assert [attempt.task_attempt_id for attempt in root.attempts] == [
        ROOT_ATTEMPT_1,
        ROOT_ATTEMPT_2,
    ]


def test_context_parts_map_to_observation_action_environment_steps() -> None:
    session = _session()
    _seed_episode_fixture(session)

    root = RlEpisodeReadService(session).get_episode(SAMPLE_ID).root_tasks[0]
    steps = root.attempts[1].steps

    assert [step.step_kind for step in steps] == [
        "observation",
        "observation",
        "action",
        "action",
        "environment",
        "action",
    ]


def test_child_task_records_parent_causing_actor_from_parent_task() -> None:
    session = _session()
    _seed_episode_fixture(session)

    child = RlEpisodeReadService(session).get_episode(SAMPLE_ID).root_tasks[0].children[0]

    assert child.actor.parent_actor_slug == "planner"


def test_list_steps_filters_over_canonical_episode_model() -> None:
    session = _session()
    _seed_episode_fixture(session)
    service = RlEpisodeReadService(session)

    planner_steps = service.list_steps(SAMPLE_ID, actor_slug="planner")
    researcher_steps = service.list_steps(SAMPLE_ID, actor_slug="researcher")

    assert "CHILD_RESULT_PARENT_VISIBLE_SENTINEL" in _texts(planner_steps)
    assert "CHILD_INTERNAL_THINKING_SENTINEL" not in _texts(planner_steps)
    assert _texts(researcher_steps) == [
        "CHILD_INTERNAL_THINKING_SENTINEL",
        "CHILD_INTERNAL_ACTION_SENTINEL",
    ]
