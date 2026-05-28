from datetime import UTC, datetime
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
    TokenLogprob,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)
from ergon_core.core.views.rl.episode import RlEpisodeReadService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


TOKEN_LOGPROB_SAMPLE_ID = UUID("60000000-0000-0000-0000-000000000000")
TOKEN_LOGPROB_ROOT_TASK_ID = UUID("70000000-0000-0000-0000-000000000000")
TOKEN_LOGPROB_ATTEMPT_ID = UUID("80000000-0000-0000-0000-000000000000")
T0 = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _event(sequence: int, event_type: str, part, *, token_ids=None, logprobs=None):
    payload = ContextPartChunkLog(
        part=part,
        token_ids=token_ids,
        logprobs=logprobs,
        sequence=sequence,
        worker_binding_key="planner",
        turn_id=f"turn-{sequence}",
    )
    return SampleContextEvent(
        sample_id=TOKEN_LOGPROB_SAMPLE_ID,
        task_attempt_id=TOKEN_LOGPROB_ATTEMPT_ID,
        worker_binding_key="planner",
        sequence=sequence,
        event_type=event_type,
        payload=payload.model_dump(mode="json"),
        created_at=T0,
    )


def _seed_token_fixture(session: Session) -> None:
    session.add(
        SampleRecord(
            id=TOKEN_LOGPROB_SAMPLE_ID,
            benchmark_type="unit",
            instance_key="token-roundtrip",
            status=SampleStatus.COMPLETED,
        )
    )
    session.add(
        SampleGraphNode(
            sample_id=TOKEN_LOGPROB_SAMPLE_ID,
            task_id=TOKEN_LOGPROB_ROOT_TASK_ID,
            instance_key="token-roundtrip",
            task_slug="root",
            description="Root",
            status="completed",
            assigned_worker_slug="planner",
        )
    )
    session.add(
        SampleTaskAttempt(
            id=TOKEN_LOGPROB_ATTEMPT_ID,
            sample_id=TOKEN_LOGPROB_SAMPLE_ID,
            task_id=TOKEN_LOGPROB_ROOT_TASK_ID,
            status=TaskExecutionStatus.COMPLETED,
        )
    )
    session.add_all(
        [
            _event(
                1,
                "system_prompt",
                SystemPromptPart(content="SYSTEM_SENTINEL_alpha"),
            ),
            _event(
                2,
                "user_message",
                UserMessagePart(content="USER_SENTINEL_beta"),
            ),
            _event(
                3,
                "thinking",
                ThinkingPart(content="THINKING_SENTINEL_gamma"),
                token_ids=[101, 102],
                logprobs=[
                    TokenLogprob(
                        token="THINK",
                        logprob=-0.11,
                        top_logprobs=[
                            {"token": "THINK", "logprob": -0.11, "rank": 1},
                            {"token": "PLAN", "logprob": -1.25, "rank": 2},
                        ],
                    ),
                    TokenLogprob(token="ING", logprob=-0.23),
                ],
            ),
            _event(
                4,
                "tool_call",
                ToolCallPart(
                    tool_call_id="call-1",
                    tool_name="spawn_task",
                    args={"prompt": "TOOL_CALL_SENTINEL_delta"},
                ),
                token_ids=[201],
                logprobs=None,
            ),
            _event(
                5,
                "tool_result",
                ToolResultPart(
                    tool_call_id="call-1",
                    tool_name="spawn_task",
                    content="TOOL_RESULT_SENTINEL_epsilon",
                ),
            ),
            _event(
                6,
                "assistant_text",
                AssistantTextPart(content="ASSISTANT_SENTINEL_zeta"),
                token_ids=[301, 302],
                logprobs=[
                    TokenLogprob(token="ASSISTANT", logprob=-0.41),
                    TokenLogprob(token="_zeta", logprob=-0.52),
                ],
            ),
        ]
    )
    session.commit()


def _actions(session: Session):
    episode = RlEpisodeReadService(session).get_episode(TOKEN_LOGPROB_SAMPLE_ID)
    return [step for step in episode.root_tasks[0].attempts[0].steps if step.step_kind == "action"]


def test_rl_episode_roundtrips_token_ids_logprobs_and_top_logprobs() -> None:
    session = _session()
    _seed_token_fixture(session)

    thinking = next(step for step in _actions(session) if step.text == "THINKING_SENTINEL_gamma")
    assistant = next(step for step in _actions(session) if step.text == "ASSISTANT_SENTINEL_zeta")

    assert thinking.token_metadata.token_ids == [101, 102]
    assert thinking.token_metadata.tokens == ["THINK", "ING"]
    assert [item.logprob for item in thinking.token_metadata.logprobs] == [-0.11, -0.23]
    assert thinking.token_metadata.logprobs[0].top_logprobs[1]["token"] == "PLAN"
    assert assistant.token_metadata.token_ids == [301, 302]
    assert [item.logprob for item in assistant.token_metadata.logprobs] == [-0.41, -0.52]


def test_missing_logprobs_remain_absent_not_zero_padded() -> None:
    session = _session()
    _seed_token_fixture(session)

    tool_call = next(step for step in _actions(session) if step.text == "TOOL_CALL_SENTINEL_delta")

    assert tool_call.token_metadata.token_ids == [201]
    assert tool_call.token_metadata.logprobs is None


def test_roundtrip_asserts_through_episode_view_not_raw_tables() -> None:
    session = _session()
    _seed_token_fixture(session)

    episode = RlEpisodeReadService(session).get_episode(TOKEN_LOGPROB_SAMPLE_ID)

    texts = [
        step.text
        for task in episode.root_tasks
        for attempt in task.attempts
        for step in attempt.steps
    ]
    assert "SYSTEM_SENTINEL_alpha" in texts
    assert "ASSISTANT_SENTINEL_zeta" in texts
