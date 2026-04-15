"""add_run_context_events

Revision ID: f1a2b3c4d5e6
Revises: e89c6c427de4
Create Date: 2026-04-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e89c6c427de4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_context_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_execution_id", sa.Uuid(), nullable=False),
        sa.Column("worker_binding_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["task_execution_id"], ["run_task_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_run_context_events_event_type"),
        "run_context_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_run_context_events_run_id"),
        "run_context_events",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_run_context_events_task_execution_id"),
        "run_context_events",
        ["task_execution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_run_context_events_worker_binding_key"),
        "run_context_events",
        ["worker_binding_key"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_run_context_events_execution_sequence",
        "run_context_events",
        ["task_execution_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_run_context_events_worker_binding_key"), table_name="run_context_events"
    )
    op.drop_index(
        op.f("ix_run_context_events_task_execution_id"), table_name="run_context_events"
    )
    op.drop_index(op.f("ix_run_context_events_run_id"), table_name="run_context_events")
    op.drop_index(op.f("ix_run_context_events_event_type"), table_name="run_context_events")
    op.drop_constraint(
        "uq_run_context_events_execution_sequence",
        "run_context_events",
        type_="unique",
    )
    op.drop_table("run_context_events")
