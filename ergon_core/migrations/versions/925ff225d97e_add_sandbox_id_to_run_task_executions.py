"""add sandbox_id to run_task_executions

Revision ID: 925ff225d97e
Revises: 11f1497a53e8
Create Date: 2026-04-23 00:00:00.000000

Adds ``sandbox_id`` (VARCHAR, nullable) to ``run_task_executions`` so that the
E2B sandbox instance associated with a task execution can be recorded and later
used to restart or clean up a blocked task without re-allocating a sandbox.
The column is nullable because legacy executions and test fixtures do not carry
a sandbox reference.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "925ff225d97e"
down_revision: Union[str, None] = "11f1497a53e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("run_task_executions", sa.Column("sandbox_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("run_task_executions", "sandbox_id")
