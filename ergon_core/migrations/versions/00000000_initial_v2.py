"""Initial v2 schema.

Revision ID: 00000000
Revises:
Create Date: 2026-05-18
"""

from importlib import import_module

from alembic import op
from sqlmodel import SQLModel


for module_name in (
    "ergon_core.core.persistence.context.models",
    "ergon_core.core.persistence.definitions.models",
    "ergon_core.core.persistence.graph.models",
    "ergon_core.core.persistence.telemetry.models",
):
    import_module(module_name)


revision = "00000000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    SQLModel.metadata.create_all(op.get_bind())


def downgrade() -> None:
    SQLModel.metadata.drop_all(op.get_bind())
