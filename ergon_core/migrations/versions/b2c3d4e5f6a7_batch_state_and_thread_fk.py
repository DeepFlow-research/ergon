"""add rollout batch tables and thread execution FK

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-13 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rollout_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("definition_id", sa.Uuid(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["definition_id"], ["experiment_definitions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rollout_batches_definition_id", "rollout_batches", ["definition_id"])
    op.create_index("ix_rollout_batches_status", "rollout_batches", ["status"])

    op.create_table(
        "rollout_batch_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["rollout_batches.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rollout_batch_runs_batch_id", "rollout_batch_runs", ["batch_id"])
    op.create_index("ix_rollout_batch_runs_run_id", "rollout_batch_runs", ["run_id"])

    op.add_column(
        "thread_messages",
        sa.Column("task_execution_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_thread_messages_task_execution_id",
        "thread_messages",
        "run_task_executions",
        ["task_execution_id"],
        ["id"],
    )
    op.create_index(
        "ix_thread_messages_task_execution_id",
        "thread_messages",
        ["task_execution_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_thread_messages_task_execution_id", table_name="thread_messages")
    op.drop_constraint("fk_thread_messages_task_execution_id", "thread_messages", type_="foreignkey")
    op.drop_column("thread_messages", "task_execution_id")

    op.drop_index("ix_rollout_batch_runs_run_id", table_name="rollout_batch_runs")
    op.drop_index("ix_rollout_batch_runs_batch_id", table_name="rollout_batch_runs")
    op.drop_table("rollout_batch_runs")

    op.drop_index("ix_rollout_batches_status", table_name="rollout_batches")
    op.drop_index("ix_rollout_batches_definition_id", table_name="rollout_batches")
    op.drop_table("rollout_batches")
