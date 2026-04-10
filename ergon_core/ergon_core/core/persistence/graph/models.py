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
from uuid import UUID, uuid4

from ergon_core.core.utils import utcnow as _utcnow
from pydantic import model_validator
from sqlalchemy import JSON, Column, DateTime, Index
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)


# ---------------------------------------------------------------------------
# RunGraphNode
# ---------------------------------------------------------------------------


class RunGraphNode(SQLModel, table=True):
    __tablename__ = "run_graph_nodes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    definition_task_id: UUID | None = Field(
        default=None,
        foreign_key="experiment_definition_tasks.id",
    )
    instance_key: str
    task_key: str = Field(index=True)
    description: str

    # Free-form string, not an enum. The experiment layer owns domain-specific
    # status values (e.g. "proposed", "negotiating", "completed") so different
    # experiments can define different lifecycles without core schema changes.
    status: str = Field(index=True)

    # Kept on the core row (not in annotations) because the execution runtime
    # needs it for task dispatch routing. Everything else experiment-specific
    # (payload, contracts, criteria) goes in annotations.
    assigned_worker_key: str | None = None

    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)


# ---------------------------------------------------------------------------
# RunGraphEdge
# ---------------------------------------------------------------------------


class RunGraphEdge(SQLModel, table=True):
    __tablename__ = "run_graph_edges"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    definition_dependency_id: UUID | None = Field(
        default=None,
        foreign_key="experiment_definition_task_dependencies.id",
    )
    source_node_id: UUID = Field(
        foreign_key="run_graph_nodes.id",
        index=True,
    )
    target_node_id: UUID = Field(
        foreign_key="run_graph_nodes.id",
        index=True,
    )
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
    target_type: str
    target_id: UUID
    namespace: str
    sequence: int = Field(index=True)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    def parsed_payload(self) -> dict[str, object]:
        return self.__class__._parse_payload(self.payload)

    @classmethod
    def _parse_payload(cls, data: dict) -> dict[str, object]:
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
    mutation_type: str = Field(index=True)
    target_type: str
    target_id: UUID = Field(index=True)
    actor: str
    old_value: dict | None = Field(default=None, sa_column=Column(JSON))
    new_value: dict = Field(default_factory=dict, sa_column=Column(JSON))
    reason: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
