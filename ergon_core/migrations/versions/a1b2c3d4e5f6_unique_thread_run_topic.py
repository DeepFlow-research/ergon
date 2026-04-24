"""unique_thread_run_topic

Revision ID: a1b2c3d4e5f6
Revises: 925ff225d97e
Create Date: 2026-04-23 12:00:00.000000

Adds a UNIQUE constraint on (run_id, topic) for the ``threads`` table so that
concurrent leaf workers all land in the same broadcast thread rather than each
creating their own.  Before adding the constraint, removes any duplicate rows
keeping the earliest-created thread per (run_id, topic) pair.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "925ff225d97e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Remove messages belonging to duplicate threads (FK requires messages go first).
    conn.execute(
        sa.text("""
            DELETE FROM thread_messages
            WHERE thread_id IN (
                SELECT id FROM threads
                WHERE id NOT IN (
                    SELECT DISTINCT ON (run_id, topic) id
                    FROM threads
                    ORDER BY run_id, topic, created_at
                )
            )
        """)
    )

    # Now remove the duplicate thread rows, keeping the earliest per (run_id, topic).
    conn.execute(
        sa.text("""
            DELETE FROM threads
            WHERE id NOT IN (
                SELECT DISTINCT ON (run_id, topic) id
                FROM threads
                ORDER BY run_id, topic, created_at
            )
        """)
    )

    op.create_unique_constraint("uq_threads_run_topic", "threads", ["run_id", "topic"])


def downgrade() -> None:
    op.drop_constraint("uq_threads_run_topic", "threads", type_="unique")
