"""Add task_json + is_dynamic to run_graph_nodes (PR 1).

Additive only: every existing row gets `task_json='{}'` and
`is_dynamic=false` via server defaults so the migration succeeds even
when the writers haven't been updated yet. PR 3's worker_execute
cutover and PR 11's schema reset will tighten the contract.

Revision ID: aabbccdd0001
Revises: e2f3a4b5c6d7
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "aabbccdd0001"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "run_graph_nodes",
        sa.Column(
            "task_json",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "run_graph_nodes",
        sa.Column(
            "is_dynamic",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_run_graph_nodes_run_dynamic",
        "run_graph_nodes",
        ["run_id", "is_dynamic"],
    )


def downgrade() -> None:
    op.drop_index("ix_run_graph_nodes_run_dynamic", table_name="run_graph_nodes")
    op.drop_column("run_graph_nodes", "is_dynamic")
    op.drop_column("run_graph_nodes", "task_json")
