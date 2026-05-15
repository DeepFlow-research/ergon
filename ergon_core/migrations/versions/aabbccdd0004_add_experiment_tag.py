"""Add ``experiment`` string tag to experiments table (PR 6.5).

PR 6.5 (Phase 2) killed the public ``Experiment`` Pydantic class.  The
word "experiment" survives only as a `str | None` grouping column on
``BenchmarkDefinitionRecord`` (the SQLModel class — table stays
``experiments`` for backward-compat with the existing Alembic chain;
PR 11 collapses the whole history into a v2 initial schema).

Two persisted definitions that share the same ``experiment`` string
belong to the same logical experiment (e.g. an ablation study).
``NULL`` means the record is not grouped into any named experiment.

Additive: every existing row gets ``experiment=NULL`` by default.

Revision ID: aabbccdd0004
Revises: aabbccdd0003
Create Date: 2026-05-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "aabbccdd0004"
down_revision = "aabbccdd0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "experiments",
        sa.Column("experiment", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_experiments_experiment",
        "experiments",
        ["experiment"],
    )


def downgrade() -> None:
    op.drop_index("ix_experiments_experiment", table_name="experiments")
    op.drop_column("experiments", "experiment")
