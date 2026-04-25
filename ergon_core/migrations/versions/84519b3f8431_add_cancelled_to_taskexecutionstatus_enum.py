"""add CANCELLED to taskexecutionstatus enum

Revision ID: 84519b3f8431
Revises: a66564b89aac
Create Date: 2026-04-23 00:00:00.000000

The Python ``TaskExecutionStatus`` enum in
``ergon_core/core/persistence/shared/enums.py`` grew a ``CANCELLED``
member (see migration ``b5b36e45e5e6_add_containment_and_cancelled``
for the graph-side cancellation vocabulary change), but the Postgres
``taskexecutionstatus`` enum — created in the initial schema
``5f01559f2bc3_initial_schema_v2`` with only PENDING/RUNNING/COMPLETED/
FAILED/SKIPPED — was never extended. ``ergon-core-cleanup-cancelled-task``
therefore fails with::

    (psycopg2.errors.InvalidTextRepresentation) invalid input value for
    enum taskexecutionstatus: "CANCELLED"

when it issues ``UPDATE run_task_executions SET status='CANCELLED' ...``.
See ``docs/bugs/open/2026-04-23-inngest-function-failures.md`` § B.

Postgres requires ``ALTER TYPE ... ADD VALUE`` to run OUTSIDE a
transaction. Alembic's ``env.py`` wraps each migration in
``context.begin_transaction()``, so we flip the bound connection to
AUTOCOMMIT for the DDL. SQLite (used by some tests) stores enums as
VARCHAR via ``sa.Enum``'s native fallback, so the migration is a no-op
on non-Postgres dialects.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "84519b3f8431"
down_revision: Union[str, None] = "a66564b89aac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction in Postgres.
    # ``context.autocommit_block()`` is the Alembic-native way to carve out
    # a DDL that must run outside the migration's envelope transaction —
    # the earlier ``bind.execution_options(isolation_level=...)`` pattern
    # returned a proxy that did not flush the DDL before the envelope
    # transaction closed, leaving alembic_version unchanged after the
    # migration logged ``Running upgrade`` at the start.  SQLite renders
    # sa.Enum as VARCHAR, so the migration is a no-op on non-Postgres.
    if op.get_context().dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE taskexecutionstatus ADD VALUE IF NOT EXISTS 'CANCELLED'"))


def downgrade() -> None:
    # Postgres does not support removing a value from an enum type without
    # recreating the type and rewriting every column that references it.
    # Leaving the value in place is harmless: rows will simply never carry
    # it after the dependent application code is rolled back.
    pass
