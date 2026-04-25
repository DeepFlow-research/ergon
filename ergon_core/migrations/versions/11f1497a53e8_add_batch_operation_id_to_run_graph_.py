"""add batch_operation_id to run_graph_mutations

Revision ID: 11f1497a53e8
Revises: 7c9661121a86
Create Date: 2026-04-23 00:00:00.000000

Adds ``batch_operation_id`` (UUID, nullable) to ``run_graph_mutations`` so that
mutations emitted as part of the same logical batch (e.g. blocking all direct
successors of a failed task in a single propagation sweep) can be correlated for
observability and replay.  A partial index on non-NULL values keeps lookups fast
without penalising the common case where the column is NULL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "11f1497a53e8"
down_revision: Union[str, None] = "7c9661121a86"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("run_graph_mutations", sa.Column("batch_operation_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_run_graph_mutations_batch_operation_id",
        "run_graph_mutations",
        ["batch_operation_id"],
        postgresql_where=sa.text("batch_operation_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_run_graph_mutations_batch_operation_id", table_name="run_graph_mutations")
    op.drop_column("run_graph_mutations", "batch_operation_id")
