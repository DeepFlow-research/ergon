"""key_task_evaluations_by_node

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-25 21:10:00.000000

Store task evaluation identity by runtime graph node instead of static
definition task id so dynamic nodes can be rendered truthfully.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("run_task_evaluations", sa.Column("node_id", sa.Uuid(), nullable=True))
    op.add_column(
        "run_task_evaluations",
        sa.Column("task_execution_id", sa.Uuid(), nullable=True),
    )

    evaluations = sa.table(
        "run_task_evaluations",
        sa.column("id"),
        sa.column("run_id"),
        sa.column("definition_task_id"),
        sa.column("node_id"),
        sa.column("task_execution_id"),
    )
    executions = sa.table(
        "run_task_executions",
        sa.column("id"),
        sa.column("run_id"),
        sa.column("definition_task_id"),
        sa.column("node_id"),
        sa.column("started_at"),
    )
    connection = op.get_bind()

    for evaluation in connection.execute(
        sa.select(
            evaluations.c.id,
            evaluations.c.run_id,
            evaluations.c.definition_task_id,
        )
    ):
        execution = connection.execute(
            sa.select(executions.c.id, executions.c.node_id)
            .where(executions.c.run_id == evaluation.run_id)
            .where(executions.c.definition_task_id == evaluation.definition_task_id)
            .order_by(executions.c.started_at.desc())
            .limit(1)
        ).first()
        if execution is None or execution.node_id is None:
            connection.execute(evaluations.delete().where(evaluations.c.id == evaluation.id))
            continue

        connection.execute(
            evaluations.update()
            .where(evaluations.c.id == evaluation.id)
            .values(
                node_id=execution.node_id,
                task_execution_id=execution.id,
            )
        )

    with op.batch_alter_table("run_task_evaluations") as batch_op:
        batch_op.alter_column("node_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.alter_column("task_execution_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.alter_column("definition_task_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.create_foreign_key(
            "fk_run_task_evaluations_node_id_run_graph_nodes",
            "run_graph_nodes",
            ["node_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_run_task_evaluations_task_execution_id_run_task_executions",
            "run_task_executions",
            ["task_execution_id"],
            ["id"],
        )

    op.create_index(
        op.f("ix_run_task_evaluations_node_id"),
        "run_task_evaluations",
        ["node_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_run_task_evaluations_task_execution_id"),
        "run_task_evaluations",
        ["task_execution_id"],
        unique=False,
    )


def downgrade() -> None:
    evaluations = sa.table(
        "run_task_evaluations",
        sa.column("definition_task_id"),
    )
    connection = op.get_bind()
    connection.execute(evaluations.delete().where(evaluations.c.definition_task_id.is_(None)))

    with op.batch_alter_table("run_task_evaluations") as batch_op:
        batch_op.drop_constraint(
            "fk_run_task_evaluations_task_execution_id_run_task_executions",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_run_task_evaluations_node_id_run_graph_nodes",
            type_="foreignkey",
        )
        batch_op.alter_column("definition_task_id", existing_type=sa.Uuid(), nullable=False)

    op.drop_index(
        op.f("ix_run_task_evaluations_task_execution_id"), table_name="run_task_evaluations"
    )
    op.drop_index(op.f("ix_run_task_evaluations_node_id"), table_name="run_task_evaluations")
    op.drop_column("run_task_evaluations", "task_execution_id")
    op.drop_column("run_task_evaluations", "node_id")
