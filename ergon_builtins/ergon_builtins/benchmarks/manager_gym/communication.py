"""Recipient-scoped MAG communication tools over Ergon's message service."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from ergon_core.api.worker import WorkerContext
from ergon_core.core.application.communication.models import CreateMessageRequest
from ergon_core.core.application.communication.service import CommunicationService
from ergon_core.core.persistence.telemetry.models import ThreadMessage
from sqlmodel import col, select


def preview(content: str, limit: int) -> str:
    return content if len(content) <= limit else content[: limit - 3] + "..."


@dataclass
class MAGCommunication:
    context: WorkerContext
    actor: str
    recipients: list[str]
    logical_task: str
    timestep: int
    call_index: int = 0

    def read_messages(self) -> list[ThreadMessage]:
        with self.context.session_factory() as session:
            return list(
                session.exec(
                    select(ThreadMessage)
                    .where(
                        ThreadMessage.sample_id == self.context.sample_id,
                        (ThreadMessage.from_agent_id == self.actor)
                        | (ThreadMessage.to_agent_id == self.actor),
                    )
                    .order_by(col(ThreadMessage.created_at), col(ThreadMessage.id))
                ).all()
            )

    async def deliver(self, to_agent: str, content: str, message_type: str) -> str:
        if to_agent not in self.recipients:
            return "Unknown or unavailable recipient. Available agent IDs: " + ", ".join(
                self.recipients
            )
        index = self.call_index
        self.call_index += 1
        response = await CommunicationService().save_message(
            CreateMessageRequest(
                sample_id=self.context.sample_id,
                from_agent_id=self.actor,
                to_agent_id=to_agent,
                thread_topic=f"mag:{':'.join(sorted([self.actor, to_agent]))}",
                content=content,
                task_attempt_id=self.context.execution_id,
                idempotency_key=f"{self.context.execution_id}:tool:{index}",
                metadata={
                    "logical_task_id": self.logical_task,
                    "assigned_at_timestep": self.timestep,
                    "message_type": message_type,
                },
            )
        )
        return f"Message sent: {response.message_id}"

    async def send_message(self, to_agent: str, content: str, message_type: str = "general") -> str:
        """Send a direct message to another agent by its exact id."""
        return await self.deliver(to_agent, content, message_type)

    async def broadcast_message(self, content: str, message_type: str = "general") -> str:
        """Send the same message to every other available actor."""
        results = []
        for recipient in self.recipients:
            if recipient != self.actor:
                results.append(await self.deliver(recipient, content, message_type))
        return "\n".join(results)

    async def get_recent_messages(self, hours: float = 1, limit: int = 10) -> str:
        """Read recent messages addressed to this actor."""
        if hours < 0 or not 1 <= limit <= 100:
            return "Require nonnegative hours and limit from 1 to 100"
        since = datetime.now(UTC) - timedelta(hours=hours)
        rows = [
            m for m in self.read_messages() if m.to_agent_id == self.actor and m.created_at >= since
        ]
        if not rows:
            return "📭 No recent messages"
        return "\n".join(
            f"[{m.created_at:%H:%M}] {m.from_agent_id}: {preview(m.content, 100)}"
            for m in reversed(rows[-limit:])
        )

    async def get_conversation_with(self, other_agent_id: str, limit: int = 20) -> str:
        """Read this actor's conversation with one other actor."""
        limit = max(1, min(50, limit))
        rows = [
            m for m in self.read_messages() if other_agent_id in (m.from_agent_id, m.to_agent_id)
        ]
        if not rows:
            return f"No conversation history found with {other_agent_id}"
        rows = rows[-limit:]
        return "\n".join(
            [
                f"Conversation with {other_agent_id} ({len(rows)} messages):",
                *(
                    f"[{m.created_at:%H:%M}] {'You' if m.from_agent_id == self.actor else other_agent_id}: {preview(m.content, 150)}"
                    for m in rows
                ),
            ]
        )

    async def get_task_messages(self, task_id: str | None = None) -> str:
        """Read this actor's visible messages related to an authored task."""
        try:
            target = str(UUID(task_id or self.logical_task))
        except ValueError:
            return f"Invalid task ID format for task messages: {task_id}"
        rows = [m for m in self.read_messages() if m.metadata_json.get("logical_task_id") == target]
        if not rows:
            return f"No messages found for task {target}"
        return "\n".join(
            [
                f"Messages for task {target} ({len(rows)} found):",
                *(
                    f"[{m.created_at:%H:%M}] {m.from_agent_id} → {m.to_agent_id}: {preview(m.content, 100)}"
                    for m in rows
                ),
            ]
        )

    async def end_workflow(self, reason: str = "ended by agent") -> str:
        """Request that the manager end the episode after the current decision."""
        # Source exposes this tool to work roles despite its manager-only prose.
        # Preserve the reachable request as a durable, actor-attributed message.
        return await self.deliver("manager_agent", reason, "request_end_workflow")

    def tools(self) -> list[Any]:
        return [
            self.send_message,
            self.broadcast_message,
            self.get_recent_messages,
            self.get_conversation_with,
            self.get_task_messages,
            self.end_workflow,
        ]
