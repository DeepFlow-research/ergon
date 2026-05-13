"""Add worker_output_json to run_task_executions (PR 4).

PR 4's synchronous-fanout reshape persists the terminal ``WorkerOutput``
through ``WorkerOutputRepository`` so that per-evaluator Inngest workers
can reload it from a thin id-only payload. The column is nullable to
keep this migration additive — existing rows simply carry NULL until
they are written by the new orchestrator path.

Revision ID: aabbccdd0002
Revises: aabbccdd0001
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "aabbccdd0002"
down_revision = "aabbccdd0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "run_task_executions",
        sa.Column("worker_output_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("run_task_executions", "worker_output_json")
