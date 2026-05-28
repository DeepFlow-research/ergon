"""Actor-state read model for RL episode reconstruction."""

from collections import defaultdict
from contextlib import nullcontext
from datetime import datetime
from uuid import UUID

from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.samples.models import SampleWorkerEventRow
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.views.rl.models import (
    RlActorEvent,
    RlActorIdentity,
    RlActorRecord,
    RlActorState,
    RlActorTopologyNode,
)
from sqlmodel import Session, col, select


class SampleActorReadService:
    """Derive actor identity and topology from sample runtime rows."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def get_actor_state(
        self,
        sample_id: UUID,
        *,
        at_time: datetime | None = None,
        include_events: bool = False,
    ) -> RlActorState:
        session_context = nullcontext(self._session) if self._session is not None else get_session()
        with session_context as session:
            if session is None:
                raise RuntimeError("RL actor read service requires a database session")
            nodes = _load_nodes(session, sample_id)
            events = _load_worker_events(session, sample_id, at_time=at_time)
            context_worker_slugs = _load_context_worker_slugs(session, sample_id)

        nodes_by_task = {node.task_id: node for node in nodes}
        events_by_slug: dict[str, list[RlActorEvent]] = defaultdict(list)
        for row in events:
            events_by_slug[row.worker_slug].append(
                RlActorEvent(
                    event_type=row.event_type,
                    event_timestamp=row.event_timestamp,
                    worker_slug=row.worker_slug,
                    task_id=row.task_id,
                    worker_type=row.worker_type,
                    model_target=row.model_target,
                    worker_snapshot=row.worker_snapshot_json,
                )
            )

        availability = {
            worker_slug: _availability_for_events(actor_events)
            for worker_slug, actor_events in events_by_slug.items()
        }

        actors: list[RlActorRecord] = []
        for node in nodes:
            actor_slug = (
                node.assigned_worker_slug
                or _first_worker_event_slug_for_task(events, node.task_id)
                or context_worker_slugs.get(node.task_id)
            )
            if actor_slug is None:
                continue
            parent_node = nodes_by_task.get(node.parent_task_id) if node.parent_task_id else None
            parent_actor_slug = (
                parent_node.assigned_worker_slug if parent_node is not None else None
            )
            available, available_since, unavailable_since = availability.get(
                actor_slug,
                (False, None, None),
            )
            actor_events = events_by_slug.get(actor_slug, [])
            actors.append(
                RlActorRecord(
                    actor_slug=actor_slug,
                    base_worker_slug=actor_slug,
                    parent_actor_slug=parent_actor_slug,
                    task_id=node.task_id,
                    parent_task_id=node.parent_task_id,
                    is_available=available,
                    available_since=available_since,
                    unavailable_since=unavailable_since,
                    worker_snapshot=_latest_worker_snapshot(actor_events),
                    events=list(actor_events) if include_events else [],
                )
            )

        roots = _build_topology(actors)
        return RlActorState(sample_id=sample_id, actors=actors, roots=roots)


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


def _load_worker_events(
    session: Session,
    sample_id: UUID,
    *,
    at_time: datetime | None,
) -> list[SampleWorkerEventRow]:
    stmt = select(SampleWorkerEventRow).where(SampleWorkerEventRow.sample_id == sample_id)
    if at_time is not None:
        stmt = stmt.where(SampleWorkerEventRow.event_timestamp <= at_time)
    return list(
        session.exec(
            stmt.order_by(
                col(SampleWorkerEventRow.worker_slug),
                col(SampleWorkerEventRow.event_timestamp),
                col(SampleWorkerEventRow.id),
            )
        ).all()
    )


def _load_context_worker_slugs(session: Session, sample_id: UUID) -> dict[UUID, str]:
    events = list(
        session.exec(
            select(SampleContextEvent)
            .where(SampleContextEvent.sample_id == sample_id)
            .order_by(col(SampleContextEvent.sequence))
        ).all()
    )
    return {event.task_attempt_id: event.worker_binding_key for event in events}


def _first_worker_event_slug_for_task(
    events: list[SampleWorkerEventRow],
    task_id: UUID,
) -> str | None:
    for event in events:
        if event.task_id == task_id:
            return event.worker_slug
    return None


def _availability_for_events(
    events: list[RlActorEvent],
) -> tuple[bool, datetime | None, datetime | None]:
    available = False
    available_since: datetime | None = None
    unavailable_since: datetime | None = None
    for event in sorted(events, key=lambda item: item.event_timestamp):
        if event.event_type.endswith("added"):
            available = True
            available_since = event.event_timestamp
            unavailable_since = None
        elif event.event_type.endswith("removed"):
            available = False
            unavailable_since = event.event_timestamp
    return available, available_since, unavailable_since


def _latest_worker_snapshot(events: list[RlActorEvent]) -> dict:
    for event in reversed(sorted(events, key=lambda item: item.event_timestamp)):
        if event.worker_snapshot:
            return event.worker_snapshot
    return {}


def _build_topology(actors: list[RlActorRecord]) -> list[RlActorTopologyNode]:
    by_task: dict[UUID, RlActorTopologyNode] = {}
    roots: list[RlActorTopologyNode] = []
    for actor in actors:
        if actor.task_id is None:
            continue
        by_task[actor.task_id] = RlActorTopologyNode(
            actor=RlActorIdentity(
                actor_slug=actor.actor_slug,
                base_worker_slug=actor.base_worker_slug,
                parent_actor_slug=actor.parent_actor_slug,
                task_id=actor.task_id,
                parent_task_id=actor.parent_task_id,
            )
        )
    for actor in actors:
        if actor.task_id is None:
            continue
        node = by_task[actor.task_id]
        if actor.parent_task_id is not None and actor.parent_task_id in by_task:
            by_task[actor.parent_task_id].children.append(node)
        else:
            roots.append(node)
    return roots
