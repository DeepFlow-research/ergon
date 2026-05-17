"""Application service for append-only worker context events.

The service maintains per-execution sequence counters in memory. This is safe
because each execution runs in a single Inngest invocation.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from ergon_core.core.domain.generation.context_parts import (
    AssistantTextPart,
    ContextPartChunk,
    ContextPartChunkLog,
    SystemPromptPart,
    ThinkingPart,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)
from ergon_core.core.persistence.context.models import RunContextEvent
from sqlmodel import Session, select

logger = logging.getLogger(__name__)


class ContextEventService:
    """Append-only write and read path for ``run_context_events``."""

    def __init__(self) -> None:
        self._listeners: list[Callable[[RunContextEvent], Awaitable[None]]] = []
        self._sequence_counters: dict[UUID, int] = {}
        self._active_turn_ids: dict[UUID, str] = {}

    def add_listener(self, listener: Callable[[RunContextEvent], Awaitable[None]]) -> None:
        self._listeners.append(listener)

    def _next_sequence(self, execution_id: UUID) -> int:
        return self._sequence_counters.get(execution_id, 0)

    def _make_event(
        self,
        run_id: UUID,
        execution_id: UUID,
        worker_binding_key: str,
        sequence: int,
        payload: ContextPartChunkLog,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        policy_version: str | None = None,
    ) -> RunContextEvent:
        return RunContextEvent(
            run_id=run_id,
            task_execution_id=execution_id,
            worker_binding_key=worker_binding_key,
            sequence=sequence,
            event_type=payload.part.part_kind,
            payload=payload.model_dump(mode="json"),
            started_at=started_at,
            completed_at=completed_at,
            policy_version=policy_version,
        )

    def _turn_id_for_chunk(self, execution_id: UUID, chunk: ContextPartChunk) -> str | None:
        part = chunk.part
        if isinstance(part, (AssistantTextPart, ThinkingPart, ToolCallPart)):
            turn_id = self._active_turn_ids.get(execution_id)
            if turn_id is None:
                turn_id = str(uuid4())
                self._active_turn_ids[execution_id] = turn_id
            return turn_id
        if isinstance(part, (SystemPromptPart, UserMessagePart, ToolResultPart)):
            self._active_turn_ids.pop(execution_id, None)
            return None
        return None

    async def persist_chunk(
        self,
        session: Session,
        *,
        run_id: UUID,
        execution_id: UUID,
        worker_binding_key: str,
        chunk: ContextPartChunk,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        policy_version: str | None = None,
    ) -> RunContextEvent:
        """Enrich and persist one worker-emitted context stream chunk."""
        seq = self._next_sequence(execution_id)
        now = datetime.now(UTC)
        event_started_at = started_at or now
        event_completed_at = completed_at or now
        payload = ContextPartChunkLog(
            part=chunk.part,
            token_ids=chunk.token_ids,
            logprobs=chunk.logprobs,
            sequence=seq,
            worker_binding_key=worker_binding_key,
            turn_id=self._turn_id_for_chunk(execution_id, chunk),
            started_at=event_started_at,
            completed_at=event_completed_at,
            policy_version=policy_version,
        )
        event = self._make_event(
            run_id,
            execution_id,
            worker_binding_key,
            seq,
            payload,
            started_at=payload.started_at,
            completed_at=payload.completed_at,
            policy_version=payload.policy_version,
        )
        self._sequence_counters[execution_id] = seq + 1

        session.add(event)
        session.commit()

        for listener in self._listeners:
            try:
                # TODO: the return of this function should probably be a DTO detailing which of the listeners were actuallly called and which ones failed
                await listener(event)
            except Exception:  # slopcop: ignore[no-broad-except]
                logger.warning("Context event listener failed", exc_info=True)

        return event

    def get_for_execution(self, session: Session, execution_id: UUID) -> list[RunContextEvent]:
        stmt = (
            select(RunContextEvent)
            .where(RunContextEvent.task_execution_id == execution_id)
            .order_by(RunContextEvent.sequence)
        )
        return list(session.exec(stmt).all())

    def get_for_run(self, session: Session, run_id: UUID) -> list[RunContextEvent]:
        stmt = (
            select(RunContextEvent)
            .where(RunContextEvent.run_id == run_id)
            .order_by(RunContextEvent.task_execution_id, RunContextEvent.sequence)
        )
        return list(session.exec(stmt).all())
