from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ergon_core.core.views.rl.models import (
    RlActionStep,
    RlActorIdentity,
    RlEnvironmentStep,
    RlEpisode,
    RlObservationStep,
    RlTaskAttempt,
    RlTaskEpisode,
)
from ergon_core.core.views.rl.projections import RlProjectionService


T0 = datetime(2026, 5, 28, 13, 0, tzinfo=UTC)


def _step(cls, text: str, *, task_id, attempt_id, actor, sequence: int):
    return cls(
        part_kind="user_message" if cls is RlObservationStep else "assistant_text",
        text=text,
        sequence=sequence,
        sample_id=uuid4(),
        task_id=task_id,
        task_attempt_id=attempt_id,
        actor=actor,
        created_at=T0 + timedelta(seconds=sequence),
    )


def _episode() -> RlEpisode:
    sample_id = uuid4()
    root_task_id = uuid4()
    child_task_id = uuid4()
    retry_task_id = uuid4()
    root_attempt_id = uuid4()
    child_attempt_id = uuid4()
    retry_attempt_1 = uuid4()
    retry_attempt_2 = uuid4()
    planner = RlActorIdentity(
        actor_slug="planner",
        base_worker_slug="agent",
        task_id=root_task_id,
    )
    researcher = RlActorIdentity(
        actor_slug="researcher",
        base_worker_slug="agent",
        parent_actor_slug="planner",
        task_id=child_task_id,
        parent_task_id=root_task_id,
    )
    retry_actor = RlActorIdentity(
        actor_slug="planner",
        base_worker_slug="agent",
        task_id=retry_task_id,
    )
    return RlEpisode(
        sample_id=sample_id,
        root_tasks=[
            RlTaskEpisode(
                task_id=root_task_id,
                task_slug="root",
                level=0,
                assigned_worker_slug="planner",
                actor=planner,
                attempts=[
                    RlTaskAttempt(
                        task_attempt_id=root_attempt_id,
                        attempt_number=1,
                        actor=planner,
                        status="completed",
                        steps=[
                            _step(
                                RlObservationStep,
                                "USER_PARENT_REQUEST",
                                task_id=root_task_id,
                                attempt_id=root_attempt_id,
                                actor=planner,
                                sequence=1,
                            ),
                            _step(
                                RlActionStep,
                                "SPAWN_CHILD_ACTION",
                                task_id=root_task_id,
                                attempt_id=root_attempt_id,
                                actor=planner,
                                sequence=2,
                            ),
                            _step(
                                RlEnvironmentStep,
                                "CHILD_RESULT_PARENT_VISIBLE",
                                task_id=root_task_id,
                                attempt_id=root_attempt_id,
                                actor=planner,
                                sequence=5,
                            ),
                            _step(
                                RlActionStep,
                                "FINAL_PARENT_ANSWER",
                                task_id=root_task_id,
                                attempt_id=root_attempt_id,
                                actor=planner,
                                sequence=6,
                            ),
                        ],
                    )
                ],
                children=[
                    RlTaskEpisode(
                        task_id=child_task_id,
                        parent_task_id=root_task_id,
                        task_slug="child",
                        level=1,
                        assigned_worker_slug="researcher",
                        actor=researcher,
                        attempts=[
                            RlTaskAttempt(
                                task_attempt_id=child_attempt_id,
                                attempt_number=1,
                                actor=researcher,
                                status="completed",
                                steps=[
                                    _step(
                                        RlObservationStep,
                                        "CHILD_TASK_PROMPT",
                                        task_id=child_task_id,
                                        attempt_id=child_attempt_id,
                                        actor=researcher,
                                        sequence=3,
                                    ),
                                    _step(
                                        RlActionStep,
                                        "CHILD_INTERNAL_THINKING",
                                        task_id=child_task_id,
                                        attempt_id=child_attempt_id,
                                        actor=researcher,
                                        sequence=4,
                                    ),
                                    _step(
                                        RlActionStep,
                                        "CHILD_INTERNAL_ANSWER",
                                        task_id=child_task_id,
                                        attempt_id=child_attempt_id,
                                        actor=researcher,
                                        sequence=5,
                                    ),
                                ],
                            )
                        ],
                    )
                ],
            ),
            RlTaskEpisode(
                task_id=retry_task_id,
                task_slug="retry",
                level=0,
                assigned_worker_slug="planner",
                actor=retry_actor,
                attempts=[
                    RlTaskAttempt(
                        task_attempt_id=retry_attempt_1,
                        attempt_number=1,
                        actor=retry_actor,
                        status="failed",
                        steps=[],
                    ),
                    RlTaskAttempt(
                        task_attempt_id=retry_attempt_2,
                        attempt_number=2,
                        actor=retry_actor,
                        status="completed",
                        steps=[],
                    ),
                ],
            ),
        ],
    )


def test_parent_actor_span_excludes_child_internal_rollout() -> None:
    span = next(
        span for span in RlProjectionService().iter_actor_spans(_episode()) if span.key == "planner"
    )

    assert "CHILD_INTERNAL_THINKING" not in [record.text for record in span.records]
    assert "CHILD_INTERNAL_ANSWER" not in [record.text for record in span.records]


def test_parent_actor_span_includes_parent_visible_child_result() -> None:
    span = next(
        span for span in RlProjectionService().iter_actor_spans(_episode()) if span.key == "planner"
    )

    assert "CHILD_RESULT_PARENT_VISIBLE" in [record.text for record in span.records]


def test_base_worker_grouping_pools_dynamic_actors_but_preserves_metadata() -> None:
    span = next(RlProjectionService().iter_actor_spans(_episode(), group_by="base_worker_slug"))

    assert span.key == "agent"
    assert {"planner", "researcher"} <= {record.actor.actor_slug for record in span.records}
    assert all(record.task_id is not None for record in span.records)


def test_task_attempt_projection_preserves_retry_boundaries() -> None:
    trajectories = list(RlProjectionService().iter_task_attempt_trajectories(_episode()))

    retry = [trajectory for trajectory in trajectories if trajectory.task_slug == "retry"]
    assert [trajectory.attempt_number for trajectory in retry] == [1, 2]
    assert [trajectory.status for trajectory in retry] == ["failed", "completed"]


def test_joint_timeline_preserves_global_order_and_actor_task_metadata() -> None:
    timeline = RlProjectionService().get_joint_timeline(_episode())

    assert [record.text for record in timeline.records[:4]] == [
        "USER_PARENT_REQUEST",
        "SPAWN_CHILD_ACTION",
        "CHILD_TASK_PROMPT",
        "CHILD_INTERNAL_THINKING",
    ]
    assert all(record.actor is not None for record in timeline.records)
    assert all(record.task_id is not None for record in timeline.records)
