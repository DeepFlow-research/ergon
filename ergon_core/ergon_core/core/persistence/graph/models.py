"""Per-run mutable workflow graph tables.

The core graph layer. Status is a free-form string — the core does not
constrain values. Domain semantics live in the experiment layer.

Tables:
    run_graph_nodes        — mutable task nodes, one per run
    run_graph_edges        — mutable dependency edges, one per run
    run_graph_annotations  — append-only namespaced metadata (WAL)
    run_graph_mutations    — append-only audit log of every change
"""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.shared.utils import utcnow as _utcnow
from pydantic import model_validator
import sqlalchemy as sa
from sqlalchemy import JSON, Column, DateTime, Index
from sqlmodel import Field, SQLModel

GraphTargetType = Literal["node", "edge"]

MutationType = Literal[
    "node.added",
    "node.removed",
    "node.status_changed",
    "node.field_changed",
    "edge.added",
    "edge.removed",
    "edge.status_changed",
    "annotation.set",
    "annotation.deleted",
]

TZDateTime = DateTime(timezone=True)


# ---------------------------------------------------------------------------
# RunGraphNode
# ---------------------------------------------------------------------------


class RunGraphNode(SQLModel, table=True):
    __tablename__ = "run_graph_nodes"
    __table_args__ = (
        sa.PrimaryKeyConstraint("run_id", "task_id"),
        sa.Index("ix_run_graph_nodes_parent", "run_id", "parent_task_id"),
        sa.Index("ix_run_graph_nodes_status", "run_id", "status"),
    )

    run_id: UUID = Field(foreign_key="runs.id")
    task_id: UUID = Field(default_factory=uuid4)
    instance_key: str = Field(
        description=(
            "Benchmark instance identifier for this task, such as a dataset row or "
            "environment variant; maps to ExperimentDefinitionInstance.instance_key."
        )
    )
    task_slug: str = Field(
        index=True,
        description=(
            "Task slot in the experiment template, or the caller-chosen slug for a "
            "dynamically spawned subtask. Required at creation and persisted verbatim."
        ),
    )
    description: str
    task_json: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))

    status: str = Field(
        description=(
            "Free-form task status owned by the experiment layer so different "
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
        description="Task id of the parent node for dynamically spawned child tasks.",
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

    @model_validator(mode="after")
    def _validate_task_json(self) -> "RunGraphNode":
        if not isinstance(self.task_json, dict):
            raise ValueError(f"task_json must be a dict, got {type(self.task_json).__name__}")
        return self

    @property
    def id(self) -> UUID:
        """Compatibility accessor while application DTOs finish moving to task_id."""
        return self.task_id


# ---------------------------------------------------------------------------
# RunGraphEdge
# ---------------------------------------------------------------------------


class RunGraphEdge(SQLModel, table=True):
    __tablename__ = "run_graph_edges"
    __table_args__ = (
        sa.UniqueConstraint(
            "run_id",
            "source_task_id",
            "target_task_id",
            name="uq_run_graph_edges_natural",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "source_task_id"],
            ["run_graph_nodes.run_id", "run_graph_nodes.task_id"],
            name="fk_run_graph_edges_source",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "target_task_id"],
            ["run_graph_nodes.run_id", "run_graph_nodes.task_id"],
            name="fk_run_graph_edges_target",
        ),
        sa.Index("ix_run_graph_edges_target", "run_id", "target_task_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    source_task_id: UUID = Field(index=True)
    target_task_id: UUID = Field(index=True)
    status: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# RunGraphAnnotation
# ---------------------------------------------------------------------------


class RunGraphAnnotation(SQLModel, table=True):
    """Append-only annotation WAL. Each set_annotation() inserts a new row.
    Current value = latest sequence. Point-in-time = sequence <= N.

    Append-only (rather than upsert) so the full DAG state can be
    reconstructed at any mutation sequence — needed for counterfactual
    replay and credit assignment in the training pipeline."""

    __tablename__ = "run_graph_annotations"
    __table_args__ = (
        Index(
            "ix_annotation_lookup",
            "run_id",
            "target_type",
            "target_id",
            "namespace",
            "sequence",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    target_type: str = Field(
        description=(
            "GraphTargetType literal ('node' or 'edge') stored as a string for SQLModel "
            "compatibility."
        )
    )
    target_id: UUID
    namespace: str
    sequence: int = Field(index=True)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    def parsed_payload(self) -> JsonObject:
        return self.__class__._parse_payload(self.payload)

    @classmethod
    def _parse_payload(cls, data: dict) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"payload must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_payload(self) -> "RunGraphAnnotation":
        self.__class__._parse_payload(self.payload)
        return self


# ---------------------------------------------------------------------------
# RunGraphMutation
# ---------------------------------------------------------------------------


class RunGraphMutation(SQLModel, table=True):
    __tablename__ = "run_graph_mutations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    sequence: int = Field(index=True)
    mutation_type: str = Field(
        index=True,
        description="MutationType literal stored as a string for SQLModel compatibility.",
    )
    target_type: str = Field(
        description=(
            "GraphTargetType literal ('node' or 'edge') stored as a string for SQLModel "
            "compatibility."
        )
    )
    target_id: UUID = Field(index=True)
    actor: str
    old_value: dict | None = Field(default=None, sa_column=Column(JSON))
    new_value: dict = Field(default_factory=dict, sa_column=Column(JSON))
    reason: str | None = None
    triggered_by_mutation_id: UUID | None = Field(
        default=None,
        foreign_key="run_graph_mutations.id",
        ondelete="SET NULL",
    )
    batch_operation_id: UUID | None = Field(default=None, index=False)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
