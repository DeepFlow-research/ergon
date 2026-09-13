"""Keep author-supplied message metadata in the native message record."""

from alembic import op
import sqlalchemy as sa

revision = "00000005"
down_revision = "00000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("thread_messages")}
    if "metadata_json" not in columns:
        op.add_column(
            "thread_messages",
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        )


def downgrade() -> None:
    op.drop_column("thread_messages", "metadata_json")
