"""add sandbox_id to run_task_executions

Revision ID: c7c0e0404480
Revises: 307fcca3a621
Create Date: 2026-04-21

Additive migration: nullable sandbox_id column on run_task_executions.
No backfill required — historical rows are NULL, which the cleanup step
treats as 'no sandbox to release'.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c7c0e0404480"
down_revision: Union[str, None] = "307fcca3a621"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "run_task_executions",
        sa.Column("sandbox_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("run_task_executions", "sandbox_id")
