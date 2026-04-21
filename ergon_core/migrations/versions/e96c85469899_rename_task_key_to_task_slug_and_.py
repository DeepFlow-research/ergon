"""rename task_key to task_slug and assigned_worker_key to assigned_worker_slug

Revision ID: e96c85469899
Revises: 307fcca3a621
Create Date: 2026-04-21 17:51:58.759451
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e96c85469899"
down_revision: Union[str, None] = "307fcca3a621"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("run_graph_nodes", "task_key", new_column_name="task_slug")
    op.alter_column(
        "run_graph_nodes",
        "assigned_worker_key",
        new_column_name="assigned_worker_slug",
    )
    op.alter_column(
        "experiment_definition_tasks",
        "task_key",
        new_column_name="task_slug",
    )


def downgrade() -> None:
    op.alter_column(
        "experiment_definition_tasks",
        "task_slug",
        new_column_name="task_key",
    )
    op.alter_column(
        "run_graph_nodes",
        "assigned_worker_slug",
        new_column_name="assigned_worker_key",
    )
    op.alter_column("run_graph_nodes", "task_slug", new_column_name="task_key")
