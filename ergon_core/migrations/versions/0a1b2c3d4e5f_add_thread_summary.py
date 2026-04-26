"""add_thread_summary

Revision ID: 0a1b2c3d4e5f
Revises: f6a7b8c9d0e1
Create Date: 2026-04-26 19:45:00.000000

Add an optional human-readable summary for communication threads.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0a1b2c3d4e5f"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("threads", sa.Column("summary", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("threads", "summary")
