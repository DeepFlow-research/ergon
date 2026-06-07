"""Named projections over canonical RL episodes."""

from collections import defaultdict
from collections.abc import Iterable
from typing import Literal

from ergon_core.core.views.rl.models import (
    RlActorTrainingSpan,
    RlEpisode,
    RlEpisodeStep,
    RlJointEpisodeTimeline,
    RlProjectedStep,
    RlTaskAttempt,
    RlTaskAttemptTrajectory,
    RlTaskEpisode,
)


class RlProjectionService:
    """Flatten an `RlEpisode` for specific learning/debugging formalisms."""

    def iter_actor_spans(
        self,
        episode: RlEpisode,
        *,
        group_by: Literal["actor_slug", "base_worker_slug"] = "actor_slug",
    ) -> Iterable[RlActorTrainingSpan]:
        records_by_key: dict[str, list[RlProjectedStep]] = defaultdict(list)
        for task, attempt, step in _iter_steps(episode):
            if task.actor is None:
                continue
            key = task.actor.actor_slug
            if group_by == "base_worker_slug":
                key = task.actor.base_worker_slug or task.actor.actor_slug
            records_by_key[key].append(_project_step(task, attempt, step))

        for key, records in records_by_key.items():
            yield RlActorTrainingSpan(
                key=key,
                group_by=group_by,
                records=sorted(records, key=_step_sort_key),
            )

    def iter_task_attempt_trajectories(
        self,
        episode: RlEpisode,
    ) -> Iterable[RlTaskAttemptTrajectory]:
        for task in _walk_tasks(episode.root_tasks):
            for attempt in task.attempts:
                yield RlTaskAttemptTrajectory(
                    task_id=task.task_id,
                    task_slug=task.task_slug,
                    task_attempt_id=attempt.task_attempt_id,
                    attempt_number=attempt.attempt_number,
                    status=attempt.status,
                    actor=attempt.actor or task.actor,
                    records=[
                        _project_step(task, attempt, step)
                        for step in attempt.steps
                        if task.actor is not None
                    ],
                )

    def get_joint_timeline(self, episode: RlEpisode) -> RlJointEpisodeTimeline:
        records = [
            _project_step(task, attempt, step)
            for task, attempt, step in _iter_steps(episode)
            if task.actor is not None
        ]
        return RlJointEpisodeTimeline(
            sample_id=episode.sample_id,
            records=sorted(records, key=_step_sort_key),
        )


def _iter_steps(
    episode: RlEpisode,
) -> Iterable[tuple[RlTaskEpisode, RlTaskAttempt, RlEpisodeStep]]:
    for task in _walk_tasks(episode.root_tasks):
        for attempt in task.attempts:
            for step in attempt.steps:
                yield task, attempt, step


def _walk_tasks(tasks: list[RlTaskEpisode]) -> list[RlTaskEpisode]:
    result: list[RlTaskEpisode] = []
    for task in tasks:
        result.append(task)
        result.extend(_walk_tasks(task.children))
    return result


def _project_step(
    task: RlTaskEpisode,
    attempt: RlTaskAttempt,
    step: RlEpisodeStep,
) -> RlProjectedStep:
    actor = step.actor or attempt.actor or task.actor
    if actor is None:
        raise ValueError("Cannot project RL step without actor identity")
    return RlProjectedStep(
        text=step.text,
        step_kind=step.step_kind,
        part_kind=step.part_kind,
        sequence=step.sequence,
        sample_id=step.sample_id,
        task_id=task.task_id,
        task_attempt_id=attempt.task_attempt_id,
        attempt_number=attempt.attempt_number,
        status=attempt.status,
        task_slug=task.task_slug,
        actor=actor,
        token_metadata=step.token_metadata,
        created_at=step.created_at,
    )


def _step_sort_key(step: RlProjectedStep) -> tuple:
    return (
        step.created_at is None,
        step.created_at,
        step.sequence,
        str(step.task_id),
        str(step.task_attempt_id),
    )
