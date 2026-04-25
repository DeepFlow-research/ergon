"""add 'blocked' to taskexecutionstatus enum

Revision ID: 4a71a3dc2ef5
Revises: 84519b3f8431
Create Date: 2026-04-23 00:00:00.000000

Extends the Postgres ``taskexecutionstatus`` enum with the new ``blocked``
value required by the task-propagation feature.  When a predecessor task
fails its direct successors transition to ``blocked`` (non-terminal, operator
action required) rather than ``cancelled`` (terminal).

Postgres requires ``ALTER TYPE ... ADD VALUE`` to run OUTSIDE a transaction.
Alembic's ``env.py`` wraps each migration in ``context.begin_transaction()``,
so we flip the bound connection to AUTOCOMMIT for the DDL via
``autocommit_block()``.  SQLite (used by the unit-test suite) stores enums as
VARCHAR through ``sa.Enum``'s native fallback, so the migration is a no-op on
non-Postgres dialects.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4a71a3dc2ef5"
down_revision: Union[str, None] = "84519b3f8431"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_context().dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE taskexecutionstatus ADD VALUE IF NOT EXISTS 'blocked'"))


def downgrade() -> None:
    pass
