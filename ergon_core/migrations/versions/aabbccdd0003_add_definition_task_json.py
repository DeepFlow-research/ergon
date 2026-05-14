"""Add task_json to experiment_definition_tasks (PR 5).

PR 5's object-bound Task carries inline ``worker``/``sandbox``/
``evaluators`` references. The full snapshot lands on the definition
row in a new ``task_json`` column so ``Task.from_definition`` can
reconstruct the authored shape end-to-end (the existing
``task_payload`` column only carries ``Task.task_payload``).

Additive: every existing row gets ``task_json='{}'`` via server
default so legacy benchmarks still work — the runtime keeps reading
``task_payload`` for those. PR 11 may collapse the two columns
together once nothing reads the legacy payload-only path.

Revision ID: aabbccdd0003
Revises: aabbccdd0002
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "aabbccdd0003"
down_revision = "aabbccdd0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "experiment_definition_tasks",
        sa.Column(
            "task_json",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("experiment_definition_tasks", "task_json")
