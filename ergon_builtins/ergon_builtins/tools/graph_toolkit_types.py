"""Response DTOs for the ResearchGraphToolkit.

Lightweight Pydantic models that the LLM sees as tool return types.
Construct via ``from_view`` / ``from_row`` classmethods.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ergon_core.api.run_resource import RunResourceKind
from ergon_core.api.run_resource import RunResourceView
from ergon_core.core.persistence.telemetry.models import RunResource, RunTaskExecution


class ResourceRef(BaseModel):
    """Subset of RunResourceView surfaced to the LLM."""

    model_config = ConfigDict(frozen=True)

    logical_path: str
    kind: RunResourceKind
    mime_type: str
    file_path: str
    content_hash: str | None
    created_at: datetime
    producing_task_execution_id: UUID | None

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
    """Subset of RunTaskExecution surfaced to the LLM."""

    model_config = ConfigDict(frozen=True)

    task_execution_id: UUID
    task_key: str | None
    status: str
    started_at: datetime | None
    ended_at: datetime | None

    @classmethod
    def from_row(cls, row: RunTaskExecution) -> "TaskExecutionRef":
        """Lift an ORM ``RunTaskExecution`` row to a ``TaskExecutionRef``."""
        return cls(
            task_execution_id=row.id,
            task_key=None,
            status=str(row.status),
            started_at=row.started_at,
            ended_at=row.completed_at,
        )
