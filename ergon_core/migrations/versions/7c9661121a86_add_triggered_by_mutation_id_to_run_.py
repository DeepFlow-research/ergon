"""add triggered_by_mutation_id to run_graph_mutations

Revision ID: 7c9661121a86
Revises: 4a71a3dc2ef5
Create Date: 2026-04-23 00:00:00.000000

Adds a self-referential foreign key ``triggered_by_mutation_id`` to
``run_graph_mutations`` so that downstream mutations (e.g. blocking successor
tasks) can be traced back to the upstream mutation (e.g. a predecessor task
failing) that caused them.  The column is nullable — root-cause mutations have
no triggering parent.  ON DELETE SET NULL ensures referential integrity is
preserved if a mutation row is ever cleaned up.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c9661121a86"
down_revision: Union[str, None] = "4a71a3dc2ef5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "run_graph_mutations", sa.Column("triggered_by_mutation_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_run_graph_mutations_triggered_by",
        "run_graph_mutations",
        "run_graph_mutations",
        ["triggered_by_mutation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_run_graph_mutations_triggered_by", "run_graph_mutations", type_="foreignkey"
    )
    op.drop_column("run_graph_mutations", "triggered_by_mutation_id")
