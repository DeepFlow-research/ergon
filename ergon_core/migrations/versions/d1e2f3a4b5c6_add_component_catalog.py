"""add component catalog

Revision ID: d1e2f3a4b5c6
Revises: c2d3e4f5a6b7
Create Date: 2026-04-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "component_catalog",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("module", sa.String(), nullable=False),
        sa.Column("qualname", sa.String(), nullable=False),
        sa.Column("package", sa.String(), nullable=True),
        sa.Column("version", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "slug", name="uq_component_catalog_kind_slug"),
    )
    op.create_index("ix_component_catalog_kind", "component_catalog", ["kind"], unique=False)
    op.create_index("ix_component_catalog_slug", "component_catalog", ["slug"], unique=False)
    op.create_index("ix_component_catalog_package", "component_catalog", ["package"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_component_catalog_package", table_name="component_catalog")
    op.drop_index("ix_component_catalog_slug", table_name="component_catalog")
    op.drop_index("ix_component_catalog_kind", table_name="component_catalog")
    op.drop_table("component_catalog")
