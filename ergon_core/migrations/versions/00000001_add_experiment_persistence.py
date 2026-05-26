"""Add experiment persistence and candidate pool tables.

Revision ID: 00000001
Revises: 00000000
Create Date: 2026-05-26
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision = "00000001"
down_revision = "00000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_by", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_experiments_created_by"), "experiments", ["created_by"])
    op.create_index(op.f("ix_experiments_name"), "experiments", ["name"])

    op.create_table(
        "experiment_environments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_mode", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_metadata_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "name"),
    )
    op.create_index(
        op.f("ix_experiment_environments_experiment_id"),
        "experiment_environments",
        ["experiment_id"],
    )
    op.create_index(
        op.f("ix_experiment_environments_name"),
        "experiment_environments",
        ["name"],
    )
    op.create_index(
        op.f("ix_experiment_environments_source_mode"),
        "experiment_environments",
        ["source_mode"],
    )

    op.create_table(
        "experiment_sampler_invocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("sampler_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("requested_k", sa.Integer(), nullable=False),
        sa.Column("candidate_pool_size", sa.Integer(), nullable=False),
        sa.Column("selected_count", sa.Integer(), nullable=False),
        sa.Column("sampler_config_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_experiment_sampler_invocations_experiment_id"),
        "experiment_sampler_invocations",
        ["experiment_id"],
    )
    op.create_index(
        op.f("ix_experiment_sampler_invocations_sampler_name"),
        "experiment_sampler_invocations",
        ["sampler_name"],
    )

    op.create_table(
        "experiment_sample_pool_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("sampler_invocation_id", sa.Uuid(), nullable=True),
        sa.Column("sample_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("sample_json", sa.JSON(), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("discarded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["environment_id"], ["experiment_environments.id"]),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"]),
        sa.ForeignKeyConstraint(
            ["sampler_invocation_id"],
            ["experiment_sampler_invocations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "environment_id", "sample_key"),
    )
    op.create_index(
        op.f("ix_experiment_sample_pool_entries_discarded"),
        "experiment_sample_pool_entries",
        ["discarded"],
    )
    op.create_index(
        op.f("ix_experiment_sample_pool_entries_environment_id"),
        "experiment_sample_pool_entries",
        ["environment_id"],
    )
    op.create_index(
        op.f("ix_experiment_sample_pool_entries_experiment_id"),
        "experiment_sample_pool_entries",
        ["experiment_id"],
    )
    op.create_index(
        op.f("ix_experiment_sample_pool_entries_sample_key"),
        "experiment_sample_pool_entries",
        ["sample_key"],
    )
    op.create_index(
        op.f("ix_experiment_sample_pool_entries_sampler_invocation_id"),
        "experiment_sample_pool_entries",
        ["sampler_invocation_id"],
    )
    op.create_index(
        op.f("ix_experiment_sample_pool_entries_selected"),
        "experiment_sample_pool_entries",
        ["selected"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_experiment_sample_pool_entries_selected"),
        table_name="experiment_sample_pool_entries",
    )
    op.drop_index(
        op.f("ix_experiment_sample_pool_entries_sampler_invocation_id"),
        table_name="experiment_sample_pool_entries",
    )
    op.drop_index(
        op.f("ix_experiment_sample_pool_entries_sample_key"),
        table_name="experiment_sample_pool_entries",
    )
    op.drop_index(
        op.f("ix_experiment_sample_pool_entries_experiment_id"),
        table_name="experiment_sample_pool_entries",
    )
    op.drop_index(
        op.f("ix_experiment_sample_pool_entries_environment_id"),
        table_name="experiment_sample_pool_entries",
    )
    op.drop_index(
        op.f("ix_experiment_sample_pool_entries_discarded"),
        table_name="experiment_sample_pool_entries",
    )
    op.drop_table("experiment_sample_pool_entries")
    op.drop_index(
        op.f("ix_experiment_sampler_invocations_sampler_name"),
        table_name="experiment_sampler_invocations",
    )
    op.drop_index(
        op.f("ix_experiment_sampler_invocations_experiment_id"),
        table_name="experiment_sampler_invocations",
    )
    op.drop_table("experiment_sampler_invocations")
    op.drop_index(
        op.f("ix_experiment_environments_source_mode"),
        table_name="experiment_environments",
    )
    op.drop_index(op.f("ix_experiment_environments_name"), table_name="experiment_environments")
    op.drop_index(
        op.f("ix_experiment_environments_experiment_id"),
        table_name="experiment_environments",
    )
    op.drop_table("experiment_environments")
    op.drop_index(op.f("ix_experiments_name"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_created_by"), table_name="experiments")
    op.drop_table("experiments")
