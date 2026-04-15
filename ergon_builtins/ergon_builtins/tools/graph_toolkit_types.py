"""Response DTOs for the ResearchGraphToolkit.

Lightweight Pydantic models that the LLM sees as tool return types.
Construct via ``from_view`` / ``from_row`` classmethods.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ergon_core.api.run_resource import RunResourceKind, RunResourceView
from ergon_core.core.persistence.telemetry.models import RunResource, RunTaskExecution


class ResourceRef(BaseModel):
    """Subset of ``RunResourceView`` surfaced to the LLM."""

    model_config = ConfigDict(frozen=True)

    logical_path: str = Field(
        description=(
            "Stable key the worker should use to refer to this resource. "
            "Currently equal to ``file_path``; kept as a distinct field so "
            "we can introduce a logical-name layer without changing the "
            "tool surface."
        ),
    )
    kind: RunResourceKind = Field(
        description="Canonical kind (report, output, note, ...).",
    )
    mime_type: str = Field(
        description="Best-effort MIME type of the underlying blob.",
    )
    file_path: str = Field(
        description="Content-addressed blob path on disk.",
    )
    content_hash: str | None = Field(
        description="SHA-256 hex digest of the blob; ``None`` only for error rows.",
    )
    created_at: datetime = Field(
        description="Row insertion time -- used to disambiguate latest-wins reads.",
    )
    producing_task_execution_id: UUID | None = Field(
        description=(
            "Task execution that produced the resource; ``None`` for "
            "run-scoped (non-task) resources."
        ),
    )

    @classmethod
    def from_view(cls, view: RunResourceView) -> "ResourceRef":
        """Lift a ``RunResourceView`` to a ``ResourceRef``."""
        return cls(
            logical_path=view.file_path,
            kind=RunResourceKind(view.kind),
            mime_type=view.mime_type,
            file_path=view.file_path,
            content_hash=view.content_hash,
            created_at=view.created_at,
            producing_task_execution_id=view.task_execution_id,
        )

    @classmethod
    def from_row(cls, row: RunResource) -> "ResourceRef":
        """Lift an ORM ``RunResource`` row to a ``ResourceRef``."""
        return cls(
            logical_path=row.file_path,
            kind=RunResourceKind(row.kind),
            mime_type=row.mime_type,
            file_path=row.file_path,
            content_hash=row.content_hash,
            created_at=row.created_at,
            producing_task_execution_id=row.task_execution_id,
        )


class TaskExecutionRef(BaseModel):
    """Subset of ``RunTaskExecution`` surfaced to the LLM."""

    model_config = ConfigDict(frozen=True)

    task_execution_id: UUID = Field(
        description="Primary key of the ``run_task_executions`` row.",
    )
    status: str = Field(
        description=(
            "Task execution status (e.g. ``pending``, ``running``, ``completed``, ``failed``)."
        ),
    )
    started_at: datetime | None = Field(
        description="Time the task started; ``None`` if it hasn't started yet.",
    )
    ended_at: datetime | None = Field(
        description=(
            "Time the task reached a terminal status; ``None`` while still running or pending."
        ),
    )

    @classmethod
    def from_row(cls, row: RunTaskExecution) -> "TaskExecutionRef":
        """Lift an ORM ``RunTaskExecution`` row to a ``TaskExecutionRef``."""
        return cls(
            task_execution_id=row.id,
            status=str(row.status),
            started_at=row.started_at,
            ended_at=row.completed_at,
        )
