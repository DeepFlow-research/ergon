"""Public read-only DTO for a ``run_resources`` row.

The ORM row lives at ``ergon_core.core.persistence.telemetry.models.RunResource``;
this module is the API-layer shape callers should depend on.  ``RunResourceKind``
is imported at the package level (``ergon_core.api``), so prefer that import
site over reaching into the ORM module.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from ergon_core.api.json_types import JsonObject
from ergon_core.core.persistence.telemetry.models import RunResourceKind
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from ergon_core.core.persistence.telemetry.models import RunResource as _RunResourceRow

__all__ = ["RunResourceKind", "RunResourceView"]


class RunResourceView(BaseModel):
    """Read-only DTO for a ``run_resources`` row.

    Construct via ``RunResourceView.from_row(orm_row)``.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(description="Primary key of the run_resources row.")
    run_id: UUID = Field(description="The run this resource was produced in.")
    task_execution_id: UUID | None = Field(
        description=(
            "The task execution that produced the resource, or ``None`` for "
            "run-scoped resources (e.g. aggregate reports)."
        ),
    )
    kind: RunResourceKind = Field(
        description="Canonical category (report, worker_output, trace, etc.).",
    )
    name: str = Field(
        description="Human-readable name -- usually the sandbox file name or the output slot.",
    )
    mime_type: str = Field(
        description="Best-effort MIME type, guessed from ``name`` if not provided.",
    )
    file_path: str = Field(
        description=(
            "Absolute path to the content-addressed blob on disk "
            "(``${ERGON_BLOB_ROOT}/<hash[:2]>/<hash>``)."
        ),
    )
    size_bytes: int = Field(description="Size of the blob in bytes.")
    content_hash: str | None = Field(
        description="SHA-256 hex digest of the blob; used for dedup and verification.",
    )
    error: str | None = Field(
        description="Populated only when writing the resource failed; ``None`` on success.",
    )
    metadata: JsonObject = Field(
        default_factory=dict,
        description='Free-form publisher metadata (e.g. ``{"sandbox_origin": "..."}``).',
    )
    created_at: datetime = Field(
        description=(
            "Row insertion time; the log is append-only, so ``(created_at, id)`` "
            "DESC defines 'latest' for a given file_path."
        ),
    )

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
