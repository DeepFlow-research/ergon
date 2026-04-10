"""Communication service — manages inter-agent messaging threads."""

from uuid import UUID

from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.telemetry.models import Thread, ThreadMessage
from h_arcane.core.runtime.services.communication_schemas import (
    CreateMessageRequest,
    MessageResponse,
    ThreadSummary,
    ThreadWithMessages,
)
from h_arcane.core.utils import utcnow
from sqlmodel import func, select

class CommunicationService:
    """Service for managing agent-to-agent communication."""

    def save_message(self, request: CreateMessageRequest) -> MessageResponse:
        """Save a new message, creating the thread if it does not exist yet."""
        with get_session() as session:
            thread = self._get_or_create_thread(
                session,
                run_id=request.run_id,
                agent_a_id=request.from_agent_id,
                agent_b_id=request.to_agent_id,
                topic=request.thread_topic,
            )

            seq_num = (
                session.exec(
                    select(func.coalesce(func.max(ThreadMessage.sequence_num), 0)).where(
                        ThreadMessage.thread_id == thread.id
                    )
                ).one()
                + 1
            )

            message = ThreadMessage(
                thread_id=thread.id,
                run_id=request.run_id,
                from_agent_id=request.from_agent_id,
                to_agent_id=request.to_agent_id,
                content=request.content,
                sequence_num=seq_num,
            )
            session.add(message)

            thread.updated_at = utcnow()
            session.add(thread)
            session.commit()
            session.refresh(message)
            session.refresh(thread)

            return MessageResponse(
                message_id=message.id,
                thread_id=thread.id,
                run_id=message.run_id,
                thread_topic=thread.topic,
                from_agent_id=message.from_agent_id,
                to_agent_id=message.to_agent_id,
                content=message.content,
                sequence_num=message.sequence_num,
                created_at=message.created_at,
            )

    def get_thread_messages(self, thread_id: UUID) -> list[MessageResponse]:
        """Return all messages in a thread ordered by sequence number."""
        with get_session() as session:
            thread = session.get(Thread, thread_id)
            if thread is None:
                return []

            stmt = (
                select(ThreadMessage)
                .where(ThreadMessage.thread_id == thread_id)
                .order_by(ThreadMessage.sequence_num)
            )
            messages = list(session.exec(stmt).all())

            return [
                MessageResponse(
                    message_id=m.id,
                    thread_id=m.thread_id,
                    run_id=m.run_id,
                    thread_topic=thread.topic,
                    from_agent_id=m.from_agent_id,
                    to_agent_id=m.to_agent_id,
                    content=m.content,
                    sequence_num=m.sequence_num,
                    created_at=m.created_at,
                )
                for m in messages
            ]

    def get_all_threads_for_run(self, run_id: UUID) -> list[ThreadSummary]:
        """Return summaries for every thread belonging to a run."""
        with get_session() as session:
            threads = list(
                session.exec(
                    select(Thread).where(Thread.run_id == run_id)
                ).all()
            )

            summaries: list[ThreadSummary] = []
            for thread in threads:
                count = session.exec(
                    select(func.count(ThreadMessage.id)).where(
                        ThreadMessage.thread_id == thread.id
                    )
                ).one()
                summaries.append(
                    ThreadSummary(
                        thread_id=thread.id,
                        run_id=thread.run_id,
                        topic=thread.topic,
                        agent_a_id=thread.agent_a_id,
                        agent_b_id=thread.agent_b_id,
                        message_count=count,
                        created_at=thread.created_at,
                        updated_at=thread.updated_at,
                    )
                )
            return summaries

    def get_thread_with_messages(self, thread_id: UUID) -> ThreadWithMessages | None:
        """Full thread payload including all messages."""
        with get_session() as session:
            thread = session.get(Thread, thread_id)
            if thread is None:
                return None

            messages = self.get_thread_messages(thread_id)
            return ThreadWithMessages(
                thread_id=thread.id,
                run_id=thread.run_id,
                topic=thread.topic,
                agent_a_id=thread.agent_a_id,
                agent_b_id=thread.agent_b_id,
                messages=messages,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
            )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _get_or_create_thread(
        session,
        *,
        run_id: UUID,
        agent_a_id: str,
        agent_b_id: str,
        topic: str,
    ) -> Thread:
        a, b = sorted([agent_a_id, agent_b_id])
        stmt = (
            select(Thread)
            .where(Thread.run_id == run_id)
            .where(Thread.agent_a_id == a)
            .where(Thread.agent_b_id == b)
            .where(Thread.topic == topic)
        )
        existing = session.exec(stmt).first()
        if existing is not None:
            return existing

        thread = Thread(
            run_id=run_id,
            topic=topic,
            agent_a_id=a,
            agent_b_id=b,
        )
        session.add(thread)
        session.flush()
        return thread

communication_service = CommunicationService()
