"""drop run_task_state_events table

Revision ID: 307fcca3a621
Revises: b5b36e45e5e6
Create Date: 2026-04-21 00:00:00.000000

Drops the legacy RunTaskStateEvent table and its three indexes.
Data was exported to exports/run_task_state_events_<timestamp>.jsonl.gz
before this migration ran.
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "307fcca3a621"
down_revision: Union[str, None] = "b5b36e45e5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        op.f("ix_run_task_state_events_definition_task_id"),
        table_name="run_task_state_events",
    )
    op.drop_index(
        op.f("ix_run_task_state_events_event_type"),
        table_name="run_task_state_events",
    )
    op.drop_index(
        op.f("ix_run_task_state_events_run_id"),
        table_name="run_task_state_events",
    )
    op.drop_table("run_task_state_events")


def downgrade() -> None:
    op.create_table(
        "run_task_state_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("definition_task_id", sa.Uuid(), nullable=False),
        sa.Column("task_execution_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("old_status", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("new_status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["definition_task_id"], ["experiment_definition_tasks.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["task_execution_id"], ["run_task_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_run_task_state_events_run_id"),
        "run_task_state_events",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_run_task_state_events_event_type"),
        "run_task_state_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_run_task_state_events_definition_task_id"),
        "run_task_state_events",
        ["definition_task_id"],
        unique=False,
    )
