"""add import reducer tables

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-04-30
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "run_reducers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=True),
        sa.Column("task_execution_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("implementation_ref", sa.String(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("input_scope_json", sa.JSON(), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["run_graph_nodes.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["task_execution_id"], ["run_task_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_run_reducers_run_id"), "run_reducers", ["run_id"])
    op.create_index(op.f("ix_run_reducers_node_id"), "run_reducers", ["node_id"])
    op.create_index(
        op.f("ix_run_reducers_task_execution_id"),
        "run_reducers",
        ["task_execution_id"],
    )
    op.create_index(op.f("ix_run_reducers_name"), "run_reducers", ["name"])
    op.create_index(op.f("ix_run_reducers_kind"), "run_reducers", ["kind"])
    op.create_index(op.f("ix_run_reducers_status"), "run_reducers", ["status"])

    op.create_table(
        "run_reducer_footprints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reducer_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("namespace", sa.String(), nullable=True),
        sa.Column("fields_read_json", sa.JSON(), nullable=True),
        sa.Column("filters_json", sa.JSON(), nullable=True),
        sa.Column("aggregation_json", sa.JSON(), nullable=True),
        sa.Column("access_kind", sa.String(), nullable=False),
        sa.Column("sequence_min", sa.Integer(), nullable=True),
        sa.Column("sequence_max", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reducer_id"], ["run_reducers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_run_reducer_footprints_reducer_id"),
        "run_reducer_footprints",
        ["reducer_id"],
    )
    op.create_index(
        op.f("ix_run_reducer_footprints_source_kind"),
        "run_reducer_footprints",
        ["source_kind"],
    )
    op.create_index(
        op.f("ix_run_reducer_footprints_namespace"),
        "run_reducer_footprints",
        ["namespace"],
    )
    op.create_index(
        op.f("ix_run_reducer_footprints_access_kind"),
        "run_reducer_footprints",
        ["access_kind"],
    )

    op.create_table(
        "run_drops_manifests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reducer_id", sa.Uuid(), nullable=False),
        sa.Column("loss_class", sa.String(), nullable=False),
        sa.Column("dropped_source_kind", sa.String(), nullable=True),
        sa.Column("dropped_field_path", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("affected_analysis", sa.String(), nullable=True),
        sa.Column("declaration_kind", sa.String(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reducer_id"], ["run_reducers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_run_drops_manifests_reducer_id"),
        "run_drops_manifests",
        ["reducer_id"],
    )
    op.create_index(
        op.f("ix_run_drops_manifests_loss_class"),
        "run_drops_manifests",
        ["loss_class"],
    )
    op.create_index(
        op.f("ix_run_drops_manifests_dropped_field_path"),
        "run_drops_manifests",
        ["dropped_field_path"],
    )
    op.create_index(
        op.f("ix_run_drops_manifests_reason"),
        "run_drops_manifests",
        ["reason"],
    )
    op.create_index(
        op.f("ix_run_drops_manifests_declaration_kind"),
        "run_drops_manifests",
        ["declaration_kind"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_run_drops_manifests_declaration_kind"), "run_drops_manifests")
    op.drop_index(op.f("ix_run_drops_manifests_reason"), "run_drops_manifests")
    op.drop_index(op.f("ix_run_drops_manifests_dropped_field_path"), "run_drops_manifests")
    op.drop_index(op.f("ix_run_drops_manifests_loss_class"), "run_drops_manifests")
    op.drop_index(op.f("ix_run_drops_manifests_reducer_id"), "run_drops_manifests")
    op.drop_table("run_drops_manifests")

    op.drop_index(op.f("ix_run_reducer_footprints_access_kind"), "run_reducer_footprints")
    op.drop_index(op.f("ix_run_reducer_footprints_namespace"), "run_reducer_footprints")
    op.drop_index(op.f("ix_run_reducer_footprints_source_kind"), "run_reducer_footprints")
    op.drop_index(op.f("ix_run_reducer_footprints_reducer_id"), "run_reducer_footprints")
    op.drop_table("run_reducer_footprints")

    op.drop_index(op.f("ix_run_reducers_status"), "run_reducers")
    op.drop_index(op.f("ix_run_reducers_kind"), "run_reducers")
    op.drop_index(op.f("ix_run_reducers_name"), "run_reducers")
    op.drop_index(op.f("ix_run_reducers_task_execution_id"), "run_reducers")
    op.drop_index(op.f("ix_run_reducers_node_id"), "run_reducers")
    op.drop_index(op.f("ix_run_reducers_run_id"), "run_reducers")
    op.drop_table("run_reducers")
