"""add execution_outcome to run_generation_turns

Revision ID: a1b2c3d4e5f6
Revises: 0299739fd54e
Create Date: 2026-04-13 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "0299739fd54e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "run_generation_turns",
        sa.Column("execution_outcome", sa.String(), nullable=True, index=True),
    )
    op.create_index(
        "ix_run_generation_turns_execution_outcome",
        "run_generation_turns",
        ["execution_outcome"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_run_generation_turns_execution_outcome",
        table_name="run_generation_turns",
    )
    op.drop_column("run_generation_turns", "execution_outcome")
