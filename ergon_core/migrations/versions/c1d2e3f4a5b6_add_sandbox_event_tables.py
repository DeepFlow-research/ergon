"""add_sandbox_event_tables

Revision ID: c1d2e3f4a5b6
Revises: a1b2c3d4e5f6
Create Date: 2026-04-23 00:00:00.000000

Adds ``sandbox_command_wal_entries`` and ``sandbox_events`` tables so that
``PostgresSandboxEventSink`` can persist sandbox lifecycle and WAL events.
``run_id`` carries no FK constraint — the sandbox.closed WAL entry arrives
with a task_id rather than run_id due to manager teardown ordering.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sandbox_command_wal_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("sandbox_id", sa.Text(), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("stdout", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sandbox_command_wal_entries_run_id"),
        "sandbox_command_wal_entries",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sandbox_command_wal_entries_task_id"),
        "sandbox_command_wal_entries",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sandbox_command_wal_entries_sandbox_id"),
        "sandbox_command_wal_entries",
        ["sandbox_id"],
        unique=False,
    )

    op.create_table(
        "sandbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("sandbox_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("timeout_minutes", sa.Integer(), nullable=True),
        sa.Column("template", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sandbox_events_run_id"),
        "sandbox_events",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sandbox_events_task_id"),
        "sandbox_events",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sandbox_events_sandbox_id"),
        "sandbox_events",
        ["sandbox_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sandbox_events_sandbox_id"), table_name="sandbox_events")
    op.drop_index(op.f("ix_sandbox_events_task_id"), table_name="sandbox_events")
    op.drop_index(op.f("ix_sandbox_events_run_id"), table_name="sandbox_events")
    op.drop_table("sandbox_events")

    op.drop_index(
        op.f("ix_sandbox_command_wal_entries_sandbox_id"),
        table_name="sandbox_command_wal_entries",
    )
    op.drop_index(
        op.f("ix_sandbox_command_wal_entries_task_id"),
        table_name="sandbox_command_wal_entries",
    )
    op.drop_index(
        op.f("ix_sandbox_command_wal_entries_run_id"),
        table_name="sandbox_command_wal_entries",
    )
    op.drop_table("sandbox_command_wal_entries")
