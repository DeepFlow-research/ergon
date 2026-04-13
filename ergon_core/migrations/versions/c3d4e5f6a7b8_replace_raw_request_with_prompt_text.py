"""replace raw_request with prompt_text on run_generation_turns

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-13 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "run_generation_turns",
        sa.Column("prompt_text", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.drop_column("run_generation_turns", "raw_request")


def downgrade() -> None:
    op.add_column(
        "run_generation_turns",
        sa.Column("raw_request", sa.JSON(), nullable=True),
    )
    op.drop_column("run_generation_turns", "prompt_text")
