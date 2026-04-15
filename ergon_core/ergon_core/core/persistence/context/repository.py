# ergon_core/ergon_core/core/persistence/context/repository.py
"""Append-only write path for run_context_events.

Repository maintains per-execution sequence counters in memory (not DB).
This is safe because each execution runs in a single Inngest invocation.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Session, select

from ergon_core.api.generation import (
    GenerationTurn,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from ergon_core.core.persistence.context.event_payloads import (
    AssistantTextPayload,
    ContextEventPayload,
    SystemPromptPayload,
    ThinkingPayload,
    ToolCallPayload,
    ToolResultPayload,
    UserMessagePayload,
)
from ergon_core.core.persistence.context.models import RunContextEvent

logger = logging.getLogger(__name__)


class ContextEventRepository:
    """Append-only write path for run_context_events."""

    def __init__(self) -> None:
        self._listeners: list[Callable[[RunContextEvent], Awaitable[None]]] = []
        self._sequence_counters: dict[UUID, int] = {}

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
        payload: ContextEventPayload,
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
            event_type=payload.event_type,
            payload=payload.model_dump(mode="json"),
            started_at=started_at,
            completed_at=completed_at,
            policy_version=policy_version,
        )

    def _events_from_request_parts(
        self,
        run_id: UUID,
        execution_id: UUID,
        worker_binding_key: str,
        turn: GenerationTurn,
        seq: int,
    ) -> tuple[list[RunContextEvent], int]:
        """Produce context events from messages_in (excluding ToolReturnParts)."""
        events: list[RunContextEvent] = []
        for part in turn.messages_in:
            if isinstance(part, SystemPromptPart):
                events.append(
                    self._make_event(
                        run_id,
                        execution_id,
                        worker_binding_key,
                        seq,
                        SystemPromptPayload(text=part.content),
                    )
                )
                seq += 1
            elif isinstance(part, UserPromptPart):
                events.append(
                    self._make_event(
                        run_id,
                        execution_id,
                        worker_binding_key,
                        seq,
                        UserMessagePayload(text=part.content),
                    )
                )
                seq += 1
        return events, seq

    def _events_from_response_parts(
        self,
        run_id: UUID,
        execution_id: UUID,
        worker_binding_key: str,
        turn: GenerationTurn,
        seq: int,
        turn_id: str,
    ) -> tuple[list[RunContextEvent], int]:
        """Produce context events from response_parts (model-generated output)."""
        events: list[RunContextEvent] = []
        token_ids = turn.turn_token_ids
        logprobs = turn.turn_logprobs
        for part in turn.response_parts:
            payload: ContextEventPayload
            if isinstance(part, ThinkingPart):
                payload = ThinkingPayload(
                    text=part.content,
                    turn_id=turn_id,
                    turn_token_ids=token_ids,
                    turn_logprobs=logprobs,
                )
            elif isinstance(part, TextPart):
                payload = AssistantTextPayload(
                    text=part.content,
                    turn_id=turn_id,
                    turn_token_ids=token_ids,
                    turn_logprobs=logprobs,
                )
            elif isinstance(part, ToolCallPart):
                payload = ToolCallPayload(
                    tool_call_id=part.tool_call_id,
                    tool_name=part.tool_name,
                    args=part.args,
                    turn_id=turn_id,
                    turn_token_ids=token_ids,
                    turn_logprobs=logprobs,
                )
            else:
                continue
            events.append(
                self._make_event(
                    run_id,
                    execution_id,
                    worker_binding_key,
                    seq,
                    payload,
                    started_at=turn.started_at,
                    completed_at=turn.completed_at,
                    policy_version=turn.policy_version,
                )
            )
            token_ids = None
            logprobs = None
            seq += 1
        return events, seq

    def _events_from_tool_results(
        self,
        run_id: UUID,
        execution_id: UUID,
        worker_binding_key: str,
        turn: GenerationTurn,
        seq: int,
    ) -> tuple[list[RunContextEvent], int]:
        """Produce tool_result events from ToolReturnParts in messages_in."""
        events: list[RunContextEvent] = []
        for part in turn.messages_in:
            if isinstance(part, ToolReturnPart):
                events.append(
                    self._make_event(
                        run_id,
                        execution_id,
                        worker_binding_key,
                        seq,
                        ToolResultPayload(
                            tool_call_id=part.tool_call_id,
                            tool_name=part.tool_name,
                            result=part.content,
                            # Set is_error=True when ToolReturnPart gains an is_error field (currently always False)
                        ),
                    )
                )
                seq += 1
        return events, seq

    async def persist_turn(
        self,
        session: Session,
        *,
        run_id: UUID,
        execution_id: UUID,
        worker_binding_key: str,
        turn: GenerationTurn,
    ) -> list[RunContextEvent]:
        """Decompose one GenerationTurn into ordered context events and persist them."""
        seq = self._next_sequence(execution_id)
        turn_id = str(uuid4())

        req_events, seq = self._events_from_request_parts(
            run_id, execution_id, worker_binding_key, turn, seq
        )
        resp_events, seq = self._events_from_response_parts(
            run_id, execution_id, worker_binding_key, turn, seq, turn_id
        )
        tool_events, seq = self._events_from_tool_results(
            run_id, execution_id, worker_binding_key, turn, seq
        )

        events = req_events + resp_events + tool_events
        self._sequence_counters[execution_id] = seq

        for event in events:
            session.add(event)
        session.commit()

        for event in events:
            for listener in self._listeners:
                try:
                    await listener(event)
                except Exception:  # slopcop: ignore[no-broad-except]
                    logger.warning("Context event listener failed", exc_info=True)

        return events

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
