"""add sandbox and dependency fields to experiments and runs

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-04-29 00:10:00.000000
"""

from typing import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "experiments",
        sa.Column("sandbox_slug", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        "experiments",
        sa.Column("dependency_extras_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index(
        op.f("ix_experiments_sandbox_slug"),
        "experiments",
        ["sandbox_slug"],
    )

    op.add_column(
        "runs",
        sa.Column("sandbox_slug", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column("dependency_extras_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index(op.f("ix_runs_sandbox_slug"), "runs", ["sandbox_slug"])


def downgrade() -> None:
    op.drop_index(op.f("ix_runs_sandbox_slug"), table_name="runs")
    op.drop_column("runs", "dependency_extras_json")
    op.drop_column("runs", "sandbox_slug")

    op.drop_index(op.f("ix_experiments_sandbox_slug"), table_name="experiments")
    op.drop_column("experiments", "dependency_extras_json")
    op.drop_column("experiments", "sandbox_slug")
