"""drop_run_actions_add_turn_timing

Revision ID: e89c6c427de4
Revises: 5f01559f2bc3
Create Date: 2026-04-14 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "e89c6c427de4"
down_revision: Union[str, None] = "5f01559f2bc3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f("ix_run_actions_task_execution_id"), table_name="run_actions")
    op.drop_index(op.f("ix_run_actions_run_id"), table_name="run_actions")
    op.drop_table("run_actions")

    op.add_column(
        "run_generation_turns",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "run_generation_turns",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("run_generation_turns", "completed_at")
    op.drop_column("run_generation_turns", "started_at")

    op.create_table(
        "run_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_execution_id", sa.Uuid(), nullable=False),
        sa.Column("action_num", sa.Integer(), nullable=False),
        sa.Column("action_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("input_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("output_text", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["task_execution_id"], ["run_task_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_run_actions_run_id"), "run_actions", ["run_id"], unique=False
    )
    op.create_index(
        op.f("ix_run_actions_task_execution_id"),
        "run_actions",
        ["task_execution_id"],
        unique=False,
    )
