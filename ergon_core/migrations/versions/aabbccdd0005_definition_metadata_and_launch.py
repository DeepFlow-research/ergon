"""Add definition metadata columns to experiment_definitions (PR 7).

PR 7 collapses identity/metadata onto the immutable
``ExperimentDefinition`` row so launches can address a definition by id
without going through ``BenchmarkDefinitionRecord``. Three new identity
columns join ``benchmark_type``: ``name`` (indexed, NOT NULL),
``description`` (nullable), and ``created_by`` (nullable). The free-form
``metadata_json`` JSON column is unchanged.

Additive with a backfill: existing rows get ``name = benchmark_type``
before the column flips to NOT NULL, which is consistent with the
SQLModel field declaration ``name: str = Field(index=True)``. PR 11
collapses the remaining dual-write paths once every reader migrates.

Revision ID: aabbccdd0005
Revises: aabbccdd0004
Create Date: 2026-05-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "aabbccdd0005"
down_revision = "aabbccdd0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("experiment_definitions", sa.Column("name", sa.Text(), nullable=True))
    op.add_column("experiment_definitions", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("experiment_definitions", sa.Column("created_by", sa.Text(), nullable=True))
    op.create_index("ix_experiment_definitions_name", "experiment_definitions", ["name"])
    op.execute("UPDATE experiment_definitions SET name = benchmark_type WHERE name IS NULL")
    op.alter_column("experiment_definitions", "name", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_experiment_definitions_name", table_name="experiment_definitions")
    op.drop_column("experiment_definitions", "created_by")
    op.drop_column("experiment_definitions", "description")
    op.drop_column("experiment_definitions", "name")
