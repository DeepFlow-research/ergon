"""Add experiment provenance to materialized samples.

Revision ID: 00000002
Revises: 00000001
Create Date: 2026-05-26
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy import inspect


revision = "00000002"
down_revision = "00000001"
branch_labels = None
depends_on = None


_NEW_COLUMNS = (
    sa.Column("experiment_id", sa.Uuid(), nullable=True),
    sa.Column("environment_id", sa.Uuid(), nullable=True),
    sa.Column("sampler_invocation_id", sa.Uuid(), nullable=True),
    sa.Column("pool_entry_id", sa.Uuid(), nullable=True),
    sa.Column("sample_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column("sample_ref_json", sa.JSON(), nullable=True),
)

_NEW_INDEXES = (
    ("ix_samples_experiment_id", ["experiment_id"]),
    ("ix_samples_environment_id", ["environment_id"]),
    ("ix_samples_sampler_invocation_id", ["sampler_invocation_id"]),
    ("ix_samples_pool_entry_id", ["pool_entry_id"]),
    ("ix_samples_sample_key", ["sample_key"]),
)


def upgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        _upgrade_unconditional()
        return

    bind = op.get_bind()
    existing_columns = {column["name"] for column in inspect(bind).get_columns("samples")}
    for column in _NEW_COLUMNS:
        if column.name not in existing_columns:
            op.add_column("samples", column.copy())

    existing_indexes = {index["name"] for index in inspect(bind).get_indexes("samples")}
    for index_name, columns in _NEW_INDEXES:
        if index_name not in existing_indexes:
            op.create_index(index_name, "samples", columns)


def downgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        _downgrade_unconditional()
        return

    bind = op.get_bind()
    existing_columns = {column["name"] for column in inspect(bind).get_columns("samples")}
    existing_indexes = {index["name"] for index in inspect(bind).get_indexes("samples")}
    for index_name, _columns in reversed(_NEW_INDEXES):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="samples")
    for column in reversed(_NEW_COLUMNS):
        if column.name in existing_columns:
            op.drop_column("samples", column.name)


def _upgrade_unconditional() -> None:
    for column in _NEW_COLUMNS:
        op.add_column("samples", column.copy())
    for index_name, columns in _NEW_INDEXES:
        op.create_index(index_name, "samples", columns)


def _downgrade_unconditional() -> None:
    for index_name, _columns in reversed(_NEW_INDEXES):
        op.drop_index(index_name, table_name="samples")
    for column in reversed(_NEW_COLUMNS):
        op.drop_column("samples", column.name)
