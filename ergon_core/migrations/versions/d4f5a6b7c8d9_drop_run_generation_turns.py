"""drop_run_generation_turns

Revision ID: d4f5a6b7c8d9
Revises: c1d2e3f4a5b6
Create Date: 2026-04-25 20:30:00.000000

The canonical replay/action log is ``run_context_events``. The older
``run_generation_turns`` summary table is no longer read or written.
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "d4f5a6b7c8d9"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f("ix_run_generation_turns_worker_binding_key"), table_name="run_generation_turns")
    op.drop_index(op.f("ix_run_generation_turns_task_execution_id"), table_name="run_generation_turns")
    op.drop_index(op.f("ix_run_generation_turns_run_id"), table_name="run_generation_turns")
    op.drop_index(op.f("ix_run_generation_turns_execution_outcome"), table_name="run_generation_turns")
    op.drop_table("run_generation_turns")


def downgrade() -> None:
    op.create_table(
        "run_generation_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_execution_id", sa.Uuid(), nullable=False),
        sa.Column("worker_binding_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("prompt_text", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("raw_response", sa.JSON(), nullable=True),
        sa.Column("response_text", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("tool_calls_json", sa.JSON(), nullable=True),
        sa.Column("tool_results_json", sa.JSON(), nullable=True),
        sa.Column("token_ids_json", sa.JSON(), nullable=True),
        sa.Column("logprobs_json", sa.JSON(), nullable=True),
        sa.Column("policy_version", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("execution_outcome", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["task_execution_id"], ["run_task_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_run_generation_turns_execution_outcome"),
        "run_generation_turns",
        ["execution_outcome"],
        unique=False,
    )
    op.create_index(
        op.f("ix_run_generation_turns_run_id"),
        "run_generation_turns",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_run_generation_turns_task_execution_id"),
        "run_generation_turns",
        ["task_execution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_run_generation_turns_worker_binding_key"),
        "run_generation_turns",
        ["worker_binding_key"],
        unique=False,
    )
