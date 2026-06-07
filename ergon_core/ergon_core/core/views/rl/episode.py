"""Canonical RL episode view over sample runtime state."""

from collections import defaultdict
from contextlib import nullcontext
from uuid import UUID

from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.db import get_session
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
from ergon_core.core.views.rl.actor_state import SampleActorReadService
from ergon_core.core.views.rl.models import (
    RlActionStep,
    RlActorIdentity,
    RlEpisode,
    RlEpisodeStep,
    RlEnvironmentStep,
    RlObservationStep,
    RlTaskAttempt,
    RlTaskEpisode,
    RlTokenLogprob,
    RlTokenMetadata,
)
from sqlmodel import Session, col, select


class RlEpisodeReadService:
    """Build a loss-preserving sample episode tree for RL consumers."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def get_episode(
        self,
        sample_id: UUID,
        *,
        root_task_id: UUID | None = None,
        actor_slug: str | None = None,
    ) -> RlEpisode:
        session_context = nullcontext(self._session) if self._session is not None else get_session()
        with session_context as session:
            if session is None:
                raise RuntimeError("RL episode read service requires a database session")
            sample = session.get(SampleRecord, sample_id)
            nodes = _load_nodes(session, sample_id)
            attempts = _load_attempts(session, sample_id)
            events = _load_events(session, sample_id)
            actor_state = SampleActorReadService(session).get_actor_state(sample_id)

        actor_by_task = {
            actor.task_id: RlActorIdentity(
                actor_slug=actor.actor_slug,
                base_worker_slug=actor.base_worker_slug,
                parent_actor_slug=actor.parent_actor_slug,
                task_id=actor.task_id,
                parent_task_id=actor.parent_task_id,
            )
            for actor in actor_state.actors
            if actor.task_id is not None
        }
        events_by_attempt: dict[UUID, list[SampleContextEvent]] = defaultdict(list)
        for event in events:
            events_by_attempt[event.task_attempt_id].append(event)

        attempts_by_task: dict[UUID, list[RlTaskAttempt]] = defaultdict(list)
        attempt_counters: dict[UUID, int] = defaultdict(int)
        for attempt in attempts:
            attempt_counters[attempt.task_id] += 1
            actor = actor_by_task.get(attempt.task_id)
            steps = [
                _step_from_event(
                    event,
                    task_id=attempt.task_id,
                    actor=actor,
                )
                for event in events_by_attempt.get(attempt.id, [])
            ]
            attempts_by_task[attempt.task_id].append(
                RlTaskAttempt(
                    task_attempt_id=attempt.id,
                    attempt_number=attempt_counters[attempt.task_id],
                    worker_binding_key=steps[0].actor.actor_slug
                    if steps and steps[0].actor is not None
                    else None,
                    actor=actor,
                    status=str(attempt.status),
                    started_at=attempt.started_at,
                    completed_at=attempt.completed_at,
                    steps=steps,
                )
            )

        task_by_id: dict[UUID, RlTaskEpisode] = {}
        for node in nodes:
            actor = actor_by_task.get(node.task_id)
            if actor_slug is not None and (actor is None or actor.actor_slug != actor_slug):
                # Keep ancestors needed for nesting only when descendants match below.
                pass
            task_by_id[node.task_id] = RlTaskEpisode(
                task_id=node.task_id,
                parent_task_id=node.parent_task_id,
                task_slug=node.task_slug,
                level=node.level,
                assigned_worker_slug=node.assigned_worker_slug,
                actor=actor,
                attempts=attempts_by_task.get(node.task_id, []),
            )

        roots: list[RlTaskEpisode] = []
        for node in nodes:
            task = task_by_id[node.task_id]
            if node.parent_task_id and node.parent_task_id in task_by_id:
                task_by_id[node.parent_task_id].children.append(task)
            else:
                roots.append(task)

        if root_task_id is not None:
            roots = [task_by_id[root_task_id]] if root_task_id in task_by_id else []
        if actor_slug is not None:
            filtered_roots = [_filter_task_by_actor(root, actor_slug) for root in roots]
            roots = [root for root in filtered_roots if root is not None]

        return RlEpisode(
            sample_id=sample_id,
            experiment_id=sample.experiment_id if sample else None,
            environment_id=sample.environment_id if sample else None,
            sample_key=sample.sample_key if sample else None,
            normalized_reward=_normalized_reward(sample),
            root_tasks=roots,
        )

    def list_steps(
        self,
        sample_id: UUID,
        *,
        actor_slug: str | None = None,
        task_id: UUID | None = None,
        task_attempt_id: UUID | None = None,
        root_task_id: UUID | None = None,
        include_descendants: bool = False,
    ) -> list[RlEpisodeStep]:
        episode = self.get_episode(sample_id, root_task_id=root_task_id)
        tasks = _walk_tasks(episode.root_tasks)
        if task_id is not None:
            selected = {
                task.task_id
                for task in tasks
                if task.task_id == task_id
                or (include_descendants and _has_ancestor(task, task_id, tasks))
            }
        else:
            selected = {task.task_id for task in tasks}

        steps: list[RlEpisodeStep] = []
        for task in tasks:
            if task.task_id not in selected:
                continue
            if actor_slug is not None and (
                task.actor is None or task.actor.actor_slug != actor_slug
            ):
                continue
            for attempt in task.attempts:
                if task_attempt_id is not None and attempt.task_attempt_id != task_attempt_id:
                    continue
                steps.extend(attempt.steps)
        return steps


def _load_nodes(session: Session, sample_id: UUID) -> list[SampleGraphNode]:
    return list(
        session.exec(
            select(SampleGraphNode)
            .where(SampleGraphNode.sample_id == sample_id)
            .order_by(
                col(SampleGraphNode.level),
                col(SampleGraphNode.created_at),
                col(SampleGraphNode.task_id),
            )
        ).all()
    )


def _load_attempts(session: Session, sample_id: UUID) -> list[SampleTaskAttempt]:
    return list(
        session.exec(
            select(SampleTaskAttempt)
            .where(SampleTaskAttempt.sample_id == sample_id)
            .order_by(
                col(SampleTaskAttempt.task_id),
                col(SampleTaskAttempt.started_at),
                col(SampleTaskAttempt.created_at),
                col(SampleTaskAttempt.id),
            )
        ).all()
    )


def _load_events(session: Session, sample_id: UUID) -> list[SampleContextEvent]:
    return list(
        session.exec(
            select(SampleContextEvent)
            .where(SampleContextEvent.sample_id == sample_id)
            .order_by(
                col(SampleContextEvent.task_attempt_id),
                col(SampleContextEvent.sequence),
                col(SampleContextEvent.id),
            )
        ).all()
    )


def _step_from_event(
    event: SampleContextEvent,
    *,
    task_id: UUID,
    actor: RlActorIdentity | None,
) -> RlObservationStep | RlActionStep | RlEnvironmentStep:
    payload = event.parsed_payload()
    text = _payload_text(payload)
    token_metadata = _token_metadata(payload)
    if payload.part.part_kind in {"system_prompt", "user_message"}:
        return RlObservationStep(
            part_kind=payload.part.part_kind,
            text=text,
            sequence=event.sequence,
            sample_id=event.sample_id,
            task_id=task_id,
            task_attempt_id=event.task_attempt_id,
            actor=actor,
            token_metadata=token_metadata,
            created_at=event.created_at,
        )
    if payload.part.part_kind == "tool_result":
        return RlEnvironmentStep(
            part_kind=payload.part.part_kind,
            text=text,
            sequence=event.sequence,
            sample_id=event.sample_id,
            task_id=task_id,
            task_attempt_id=event.task_attempt_id,
            actor=actor,
            token_metadata=token_metadata,
            created_at=event.created_at,
        )
    return RlActionStep(
        part_kind=payload.part.part_kind,
        text=text,
        sequence=event.sequence,
        sample_id=event.sample_id,
        task_id=task_id,
        task_attempt_id=event.task_attempt_id,
        actor=actor,
        token_metadata=token_metadata,
        created_at=event.created_at,
    )


def _payload_text(payload: ContextPartChunkLog) -> str:
    part = payload.part
    if isinstance(part, SystemPromptPart | UserMessagePart | AssistantTextPart | ThinkingPart):
        return part.content
    if isinstance(part, ToolResultPart):
        return part.content
    if isinstance(part, ToolCallPart):
        return str(part.args.get("prompt") or part.args)
    return ""


def _token_metadata(payload: ContextPartChunkLog) -> RlTokenMetadata | None:
    if payload.token_ids is None and payload.logprobs is None:
        return None
    return RlTokenMetadata(
        token_ids=payload.token_ids,
        tokens=[item.token for item in payload.logprobs] if payload.logprobs is not None else None,
        logprobs=_logprobs(payload.logprobs),
    )


def _logprobs(logprobs: list[TokenLogprob] | None) -> list[RlTokenLogprob] | None:
    if logprobs is None:
        return None
    return [
        RlTokenLogprob(
            token=item.token,
            logprob=item.logprob,
            top_logprobs=list(item.top_logprobs),
        )
        for item in logprobs
    ]


def _filter_task_by_actor(task: RlTaskEpisode, actor_slug: str) -> RlTaskEpisode | None:
    children = [_filter_task_by_actor(child, actor_slug) for child in task.children]
    children = [child for child in children if child is not None]
    matches = task.actor is not None and task.actor.actor_slug == actor_slug
    if not matches and not children:
        return None
    if matches:
        return task.model_copy(update={"children": children})
    return task.model_copy(update={"attempts": [], "children": children})


def _walk_tasks(tasks: list[RlTaskEpisode]) -> list[RlTaskEpisode]:
    result: list[RlTaskEpisode] = []
    for task in tasks:
        result.append(task)
        result.extend(_walk_tasks(task.children))
    return result


def _has_ancestor(task: RlTaskEpisode, ancestor_id: UUID, tasks: list[RlTaskEpisode]) -> bool:
    parent_by_task = {item.task_id: item.parent_task_id for item in tasks}
    current = task.parent_task_id
    while current is not None:
        if current == ancestor_id:
            return True
        current = parent_by_task.get(current)
    return False


def _normalized_reward(sample: SampleRecord | None) -> float | None:
    if sample is None:
        return None
    value = sample.summary_json.get("normalized_score")
    return float(value) if value is not None else None
