"""Initial v2 schema.

Revision ID: 00000000
Revises:
Create Date: 2026-05-18
"""

import ergon_core.core.persistence.components.models  # noqa: F401
import ergon_core.core.persistence.context.models  # noqa: F401
import ergon_core.core.persistence.definitions.models  # noqa: F401
import ergon_core.core.persistence.graph.models  # noqa: F401
import ergon_core.core.persistence.imports.models  # noqa: F401
import ergon_core.core.persistence.telemetry.models  # noqa: F401
from alembic import op
from sqlmodel import SQLModel


revision = "00000000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    SQLModel.metadata.create_all(op.get_bind())


def downgrade() -> None:
    SQLModel.metadata.drop_all(op.get_bind())
