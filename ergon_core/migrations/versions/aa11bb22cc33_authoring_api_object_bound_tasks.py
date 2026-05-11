"""authoring_api_object_bound_tasks

Revision ID: aa11bb22cc33
Revises: f9075c2ddbc9
Create Date: 2026-05-10 22:10:00.000000

Store object-bound task definitions on definition and run graph rows.
Local data is intentionally disposable for this migration; the redesign has
no backwards-compatibility requirement.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aa11bb22cc33"
down_revision: Union[str, None] = "f9075c2ddbc9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    # The authoring redesign changes the persisted contract rather than
    # migrating production data. Keep the schema transition deterministic by
    # clearing affected local rows before adding non-null task JSON columns.
    for table_name in (
        "run_task_evaluations",
        "run_task_executions",
        "run_graph_edges",
        "run_graph_nodes",
        "experiment_definition_task_evaluators",
        "experiment_definition_task_dependencies",
        "experiment_definition_tasks",
    ):
        connection.execute(sa.text(f"DELETE FROM {table_name}"))

    op.add_column(
        "experiment_definition_tasks",
        sa.Column("task_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.alter_column("experiment_definition_tasks", "task_json", server_default=None)

    op.add_column("run_graph_nodes", sa.Column("task_id", sa.Uuid(), nullable=False))
    op.add_column(
        "run_graph_nodes",
        sa.Column("task_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("run_graph_nodes", sa.Column("parent_task_id", sa.Uuid(), nullable=True))
    op.alter_column("run_graph_nodes", "task_json", server_default=None)
    op.create_index(op.f("ix_run_graph_nodes_task_id"), "run_graph_nodes", ["task_id"])
    op.create_index(
        op.f("ix_run_graph_nodes_parent_task_id"),
        "run_graph_nodes",
        ["parent_task_id"],
    )
    op.create_index(
        "uq_run_graph_nodes_run_task",
        "run_graph_nodes",
        ["run_id", "task_id"],
        unique=True,
    )
    with op.batch_alter_table("run_graph_nodes") as batch_op:
        batch_op.drop_column("assigned_worker_slug")
        batch_op.drop_column("description")
        batch_op.drop_column("task_slug")
        batch_op.drop_column("instance_key")

    op.add_column("run_graph_edges", sa.Column("source_task_id", sa.Uuid(), nullable=True))
    op.add_column("run_graph_edges", sa.Column("target_task_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_run_graph_edges_source_task_id"),
        "run_graph_edges",
        ["source_task_id"],
    )
    op.create_index(
        op.f("ix_run_graph_edges_target_task_id"),
        "run_graph_edges",
        ["target_task_id"],
    )

    op.add_column("run_task_evaluations", sa.Column("evaluator_index", sa.Integer(), nullable=True))
    op.add_column("run_task_evaluations", sa.Column("evaluator_name", sa.String(), nullable=True))
    op.create_index(
        op.f("ix_run_task_evaluations_evaluator_index"),
        "run_task_evaluations",
        ["evaluator_index"],
    )
    op.create_index(
        op.f("ix_run_task_evaluations_evaluator_name"),
        "run_task_evaluations",
        ["evaluator_name"],
    )
    with op.batch_alter_table("run_task_evaluations") as batch_op:
        batch_op.alter_column(
            "definition_evaluator_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("run_task_evaluations") as batch_op:
        batch_op.alter_column(
            "definition_evaluator_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
    op.drop_index(op.f("ix_run_task_evaluations_evaluator_name"), table_name="run_task_evaluations")
    op.drop_index(
        op.f("ix_run_task_evaluations_evaluator_index"), table_name="run_task_evaluations"
    )
    op.drop_column("run_task_evaluations", "evaluator_name")
    op.drop_column("run_task_evaluations", "evaluator_index")

    op.drop_index(op.f("ix_run_graph_edges_target_task_id"), table_name="run_graph_edges")
    op.drop_index(op.f("ix_run_graph_edges_source_task_id"), table_name="run_graph_edges")
    op.drop_column("run_graph_edges", "target_task_id")
    op.drop_column("run_graph_edges", "source_task_id")

    op.drop_index("uq_run_graph_nodes_run_task", table_name="run_graph_nodes")
    op.drop_index(op.f("ix_run_graph_nodes_parent_task_id"), table_name="run_graph_nodes")
    op.drop_index(op.f("ix_run_graph_nodes_task_id"), table_name="run_graph_nodes")
    op.drop_column("run_graph_nodes", "parent_task_id")
    op.drop_column("run_graph_nodes", "task_json")
    op.drop_column("run_graph_nodes", "task_id")
    op.add_column("run_graph_nodes", sa.Column("instance_key", sa.String(), nullable=False))
    op.add_column("run_graph_nodes", sa.Column("task_slug", sa.String(), nullable=False))
    op.add_column("run_graph_nodes", sa.Column("description", sa.String(), nullable=False))
    op.add_column("run_graph_nodes", sa.Column("assigned_worker_slug", sa.String(), nullable=True))

    op.drop_column("experiment_definition_tasks", "task_json")
