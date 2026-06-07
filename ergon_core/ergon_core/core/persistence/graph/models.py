"""Per-sample mutable workflow graph projection tables.

The core graph layer. Status is a free-form string — the core does not
constrain values. Domain semantics live in the experiment layer.

Tables:
    sample_graph_nodes        — mutable task node read model
    sample_graph_edges        — mutable dependency edge read model
"""

from datetime import datetime
from uuid import UUID, uuid4

from ergon_core.core.shared.utils import utcnow as _utcnow
from sqlalchemy import JSON, Boolean, Column, DateTime
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)


# ---------------------------------------------------------------------------
# SampleGraphNode
# ---------------------------------------------------------------------------


class SampleGraphNode(SQLModel, table=True):
    __tablename__ = "sample_graph_nodes"

    sample_id: UUID = Field(foreign_key="samples.id", primary_key=True, index=True)
    task_id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Canonical runtime identity for this task within a run.",
    )
    instance_key: str = Field(
        description="Dataset row, environment variant, or caller-provided sample grouping key."
    )
    task_slug: str = Field(
        index=True,
        description=(
            "Task slot in the experiment template, or the caller-chosen slug for a "
            "dynamically spawned subtask. Required at creation and persisted verbatim."
        ),
    )
    description: str

    task_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default="{}"),
        description=(
            "Run-tier snapshot of the authored Task. Static nodes copy "
            "this from the authored sample at materialization time; "
            "dynamic nodes write it directly at spawn time."
        ),
    )

    is_dynamic: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
        description=(
            "True when this node was spawned during execution. Denormalized "
            "at insert time so the static-vs-dynamic discriminator avoids a join."
        ),
    )

    status: str = Field(
        index=True,
        description=(
            "Free-form node status owned by the experiment layer so different "
            "experiments can define lifecycles without core schema changes."
        ),
    )

    assigned_worker_slug: str | None = Field(
        default=None,
        description=(
            "Worker registry slug assigned to execute this node, for example "
            "'researchrubrics-researcher' or 'canonical-smoke'."
        ),
    )

    parent_task_id: UUID | None = Field(
        default=None,
        index=True,
        description=(
            "Self-referential containment parent. Null for definition-seeded roots and set "
            "for dynamic subtasks so hierarchy can be read without joins or edge traversal."
        ),
    )

    level: int = Field(
        default=0,
        description=(
            "Depth in the containment tree: 0 for roots and parent.level + 1 for dynamic "
            "subtasks. Stored for debugging and to avoid N+1 level computation."
        ),
    )

    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# SampleGraphEdge
# ---------------------------------------------------------------------------


class SampleGraphEdge(SQLModel, table=True):
    __tablename__ = "sample_graph_edges"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sample_id: UUID = Field(foreign_key="samples.id", index=True)
    source_task_id: UUID = Field(
        index=True,
    )
    target_task_id: UUID = Field(
        index=True,
    )
    status: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
