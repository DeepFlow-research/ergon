# ergon_core/ergon_core/core/persistence/context/models.py
"""ORM model for run_context_events."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from ergon_core.core.persistence.context.event_payloads import ContextEventPayload
from ergon_core.core.persistence.shared.ids import new_id
from pydantic import TypeAdapter
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)


def _utcnow() -> datetime:
    return datetime.now(UTC)


_PAYLOAD_ADAPTER: TypeAdapter[ContextEventPayload] = TypeAdapter(ContextEventPayload)


class RunContextEvent(SQLModel, table=True):
    __tablename__ = "run_context_events"
    __table_args__ = (
        sa.UniqueConstraint(
            "task_execution_id", "sequence", name="uq_run_context_events_execution_sequence"
        ),
    )

    id: UUID = Field(default_factory=new_id, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    task_execution_id: UUID = Field(foreign_key="run_task_executions.id", index=True)
    worker_binding_key: str = Field(index=True)
    sequence: int
    event_type: str = Field(index=True)  # ContextEventType Literal — str for SQLModel compat
    payload: dict[str, Any] = Field(sa_column=Column(JSON))  # slopcop: ignore[no-typing-any]
    # Note: Uses JSON (not JSONB) for SQLite test compatibility.
    # The migration uses JSONB for PostgreSQL production.
    started_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    completed_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    policy_version: str | None = None

    def parsed_payload(self) -> ContextEventPayload:
        return _PAYLOAD_ADAPTER.validate_python(self.payload)
