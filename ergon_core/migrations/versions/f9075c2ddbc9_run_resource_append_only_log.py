"""run_resource_append_only_log

Revision ID: f9075c2ddbc9
Revises: f1a2b3c4d5e6
Create Date: 2026-04-15 20:22:04.375113
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9075c2ddbc9"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "run_resources",
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.add_column(
        "run_resources",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "idx_run_resources_task_path_created",
        "run_resources",
        [
            "task_execution_id",
            "file_path",
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ],
    )
    op.create_index(
        "idx_run_resources_task_hash",
        "run_resources",
        ["task_execution_id", "content_hash"],
    )


def downgrade() -> None:
    op.drop_index("idx_run_resources_task_hash", table_name="run_resources")
    op.drop_index("idx_run_resources_task_path_created", table_name="run_resources")
    op.drop_column("run_resources", "content_hash")
    op.drop_column("run_resources", "error")
