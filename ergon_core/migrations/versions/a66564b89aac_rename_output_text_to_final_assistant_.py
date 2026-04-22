"""rename output_text to final_assistant_message

Revision ID: a66564b89aac
Revises: e96c85469899
Create Date: 2026-04-22 16:10:33.765768

Column rename on run_task_executions. No data transform. The ORM
attribute was renamed in the preceding commit; this migration brings
the DB schema into sync. RFC: 2026-04-22-worker-interface-and-artifact-routing.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a66564b89aac"
down_revision: Union[str, None] = "e96c85469899"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "run_task_executions",
        "output_text",
        new_column_name="final_assistant_message",
    )


def downgrade() -> None:
    op.alter_column(
        "run_task_executions",
        "final_assistant_message",
        new_column_name="output_text",
    )
