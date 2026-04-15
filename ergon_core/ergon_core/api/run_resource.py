"""Public read-only DTO for run_resources rows.

The ORM class is ``ergon_core.core.persistence.telemetry.models.RunResource``;
this module exposes ``RunResourceView`` for public API and toolkit consumers.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any  # slopcop: ignore[no-typing-any]
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Re-export so callers have one import site.
from ergon_core.core.persistence.telemetry.models import RunResourceKind

if TYPE_CHECKING:
    from ergon_core.core.persistence.telemetry.models import RunResource as _RunResourceRow

__all__ = ["RunResourceKind", "RunResourceView"]


class RunResourceView(BaseModel):
    """Read-only DTO for a run_resources row.

    Construct via ``RunResourceView.from_row(orm_row)``.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    run_id: UUID
    task_execution_id: UUID | None
    kind: RunResourceKind
    name: str
    mime_type: str
    file_path: str
    size_bytes: int
    content_hash: str | None
    error: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: "_RunResourceRow") -> "RunResourceView":
        """Map an ORM ``RunResource`` row to a frozen DTO."""
        return cls(
            id=row.id,
            run_id=row.run_id,
            task_execution_id=row.task_execution_id,
            kind=RunResourceKind(row.kind),
            name=row.name,
            mime_type=row.mime_type,
            file_path=row.file_path,
            size_bytes=row.size_bytes,
            content_hash=row.content_hash,
            error=row.error,
            metadata=row.metadata_json,
            created_at=row.created_at,
        )
