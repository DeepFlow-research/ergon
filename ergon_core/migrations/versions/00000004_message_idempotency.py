"""Serialize native message order and optionally deduplicate committed actions."""

from alembic import op
import sqlalchemy as sa

revision = "00000004"
down_revision = "00000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The historical baseline creates some tables from current SQLModel metadata.
    # Fresh installations therefore already have these additions.
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("thread_messages")}
    constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints("thread_messages")
    }
    if "idempotency_key" not in columns:
        op.add_column("thread_messages", sa.Column("idempotency_key", sa.String(), nullable=True))
    if "uq_thread_message_sequence" in constraints and "uq_thread_message_action" in constraints:
        return
    # Preserve the existing sequence order, breaking historical duplicate ties
    # by timestamp/id before enforcing uniqueness. Deploy with writers stopped.
    op.execute("""
        WITH ordered AS (
            SELECT id, row_number() OVER (
                PARTITION BY thread_id ORDER BY sequence_num, created_at, id
            ) AS new_sequence FROM thread_messages
        )
        UPDATE thread_messages SET sequence_num = (
            SELECT new_sequence FROM ordered WHERE ordered.id = thread_messages.id
        )
    """)
    with op.batch_alter_table("thread_messages") as batch:
        if "uq_thread_message_sequence" not in constraints:
            batch.create_unique_constraint(
                "uq_thread_message_sequence", ["thread_id", "sequence_num"]
            )
        if "uq_thread_message_action" not in constraints:
            batch.create_unique_constraint(
                "uq_thread_message_action", ["thread_id", "idempotency_key"]
            )


def downgrade() -> None:
    with op.batch_alter_table("thread_messages") as batch:
        batch.drop_constraint("uq_thread_message_action", type_="unique")
        batch.drop_constraint("uq_thread_message_sequence", type_="unique")
        batch.drop_column("idempotency_key")
