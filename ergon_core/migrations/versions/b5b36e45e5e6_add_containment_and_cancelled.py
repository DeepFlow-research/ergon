"""add_containment_and_cancelled

Revision ID: b5b36e45e5e6
Revises: f9075c2ddbc9
Create Date: 2026-04-16 13:52:20.698414
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b5b36e45e5e6"
down_revision: Union[str, None] = "f9075c2ddbc9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add parent_node_id column + index.
    # FK constraint is declared on the SQLModel field; we skip
    # op.create_foreign_key here because SQLite does not support
    # ALTER TABLE ... ADD CONSTRAINT. The ORM handles referential
    # integrity at the application level.
    op.add_column(
        "run_graph_nodes",
        sa.Column("parent_node_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_run_graph_nodes_parent_node_id",
        "run_graph_nodes",
        ["parent_node_id"],
    )

    # 2. Add level column (default 0 = root).
    op.add_column(
        "run_graph_nodes",
        sa.Column("level", sa.Integer(), server_default="0", nullable=False),
    )

    # 3. Backfill: old delegation edges (status='active') become parent_node_id
    #    on their target node. Uses subquery syntax for SQLite compatibility
    #    (SQLite does not support UPDATE ... FROM).
    op.execute("""
        UPDATE run_graph_nodes
           SET parent_node_id = (
               SELECT e.source_node_id
                 FROM run_graph_edges e
                WHERE e.target_node_id = run_graph_nodes.id
                  AND e.status = 'active'
                LIMIT 1
           )
         WHERE id IN (
               SELECT e.target_node_id
                 FROM run_graph_edges e
                WHERE e.status = 'active'
           )
    """)

    # 4. Recursive level backfill. SQLite supports recursive CTEs but not
    #    UPDATE ... FROM, so we use a correlated subquery approach instead.
    #    For each node with a parent, set level = parent's level + 1.
    #    We iterate up to 10 levels deep (sufficient for practical subtask trees).
    for _depth in range(10):
        op.execute("""
            UPDATE run_graph_nodes
               SET level = (
                   SELECT p.level + 1
                     FROM run_graph_nodes p
                    WHERE p.id = run_graph_nodes.parent_node_id
               )
             WHERE parent_node_id IS NOT NULL
               AND level = 0
               AND parent_node_id IN (
                   SELECT id FROM run_graph_nodes WHERE level > 0 OR parent_node_id IS NULL
               )
        """)

    # 5. Delete delegation edges — containment now lives on the node.
    op.execute("DELETE FROM run_graph_edges WHERE status = 'active'")

    # 6. Status vocabulary: ABANDONED -> CANCELLED.
    op.execute("UPDATE run_graph_nodes SET status = 'cancelled' WHERE status = 'abandoned'")
    op.execute("UPDATE run_graph_edges SET status = 'invalidated' WHERE status = 'abandoned'")


def downgrade() -> None:
    # Downgrade is lossy: delegation edges cannot be reconstructed.
    op.execute("UPDATE run_graph_nodes SET status = 'abandoned' WHERE status = 'cancelled'")
    op.execute("UPDATE run_graph_edges SET status = 'abandoned' WHERE status = 'invalidated'")
    op.drop_index("ix_run_graph_nodes_parent_node_id")
    op.drop_column("run_graph_nodes", "level")
    op.drop_column("run_graph_nodes", "parent_node_id")
