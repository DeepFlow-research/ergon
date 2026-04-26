"""add_copied_from_resource_id

Revision ID: a2b3c4d5e6f7
Revises: f6a7b8c9d0e1
Create Date: 2026-04-26 12:50:00.000000

Record resource copy lineage for workflow materialization.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "run_resources",
        sa.Column("copied_from_resource_id", sa.Uuid(), nullable=True),
    )
    with op.batch_alter_table("run_resources") as batch_op:
        batch_op.create_foreign_key(
            "fk_run_resources_copied_from_resource_id_run_resources",
            "run_resources",
            ["copied_from_resource_id"],
            ["id"],
        )
    op.create_index(
        op.f("ix_run_resources_copied_from_resource_id"),
        "run_resources",
        ["copied_from_resource_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_run_resources_copied_from_resource_id"), table_name="run_resources")
    with op.batch_alter_table("run_resources") as batch_op:
        batch_op.drop_constraint(
            "fk_run_resources_copied_from_resource_id_run_resources",
            type_="foreignkey",
        )
    op.drop_column("run_resources", "copied_from_resource_id")
