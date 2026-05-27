"""Delete definition-backed runtime columns from existing databases.

Revision ID: 00000003
Revises: 00000002
Create Date: 2026-05-27
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy import inspect


revision = "00000003"
down_revision = "00000002"
branch_labels = None
depends_on = None


_DEFINITION_TABLES = (
    "experiment_definition_dependencies",
    "experiment_definition_task_evaluators",
    "experiment_definition_task_assignments",
    "experiment_definition_task_dependencies",
    "experiment_definition_evaluators",
    "experiment_definition_workers",
    "experiment_definition_tasks",
    "experiment_definition_instances",
    "experiment_definitions",
)

_LEGACY_RUN_TABLES = (
    "run_context_events",
    "run_graph_annotations",
    "run_graph_mutations",
    "run_graph_edges",
    "run_graph_nodes",
    "run_resources",
    "run_task_evaluations",
    "run_task_executions",
)


def upgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        _upgrade_offline()
        return

    bind = op.get_bind()
    inspector = inspect(bind)

    _ensure_evaluator_slug(inspector)
    _rename_run_id_to_sample_id_if_needed(inspector, "threads")
    _rename_run_id_to_sample_id_if_needed(inspector, "thread_messages")
    _rename_run_id_to_sample_id_if_needed(inspector, "sandbox_command_wal_entries")
    _rename_run_id_to_sample_id_if_needed(inspector, "sandbox_events")
    _replace_sample_fk(inspector, "threads", "sample_id", "samples")
    _replace_sample_fk(inspector, "thread_messages", "sample_id", "samples")
    _drop_sample_fk(inspector, "sandbox_command_wal_entries", "sample_id")
    _drop_sample_fk(inspector, "sandbox_events", "sample_id")
    _add_column_if_missing(
        inspector,
        "experiment_sampler_invocations",
        sa.Column("policy_version", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        inspector,
        "experiment_sample_pool_entries",
        sa.Column("sample_ref_json", sa.JSON(), nullable=True),
    )
    _drop_column_if_exists(inspector, "samples", "definition_id")
    _drop_column_if_exists(inspector, "sample_task_attempts", "definition_worker_id")
    _drop_column_if_exists(inspector, "sample_task_evaluations", "definition_evaluator_id")
    _drop_column_if_exists(inspector, "sample_graph_edges", "definition_dependency_id")

    existing_tables = set(inspector.get_table_names())
    for table_name in (*_LEGACY_RUN_TABLES, *_DEFINITION_TABLES):
        if table_name in existing_tables:
            _drop_table_cascade(table_name)


def downgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        _downgrade_offline()
        return

    bind = op.get_bind()
    inspector = inspect(bind)
    _add_column_if_missing(
        inspector, "samples", sa.Column("definition_id", sa.Uuid(), nullable=True)
    )
    _add_column_if_missing(
        inspector,
        "sample_task_attempts",
        sa.Column("definition_worker_id", sa.Uuid(), nullable=True),
    )
    _add_column_if_missing(
        inspector,
        "sample_task_evaluations",
        sa.Column("definition_evaluator_id", sa.Uuid(), nullable=True),
    )
    _add_column_if_missing(
        inspector,
        "sample_graph_edges",
        sa.Column("definition_dependency_id", sa.Uuid(), nullable=True),
    )


def _ensure_evaluator_slug(inspector: sa.Inspector) -> None:
    columns = {column["name"] for column in inspector.get_columns("sample_task_evaluations")}
    if "evaluator_slug" not in columns:
        op.add_column(
            "sample_task_evaluations",
            sa.Column(
                "evaluator_slug",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            ),
        )
        op.execute(
            "UPDATE sample_task_evaluations "
            "SET evaluator_slug = 'unknown-evaluator' "
            "WHERE evaluator_slug IS NULL"
        )
        op.alter_column("sample_task_evaluations", "evaluator_slug", nullable=False)

    indexes = {index["name"] for index in inspector.get_indexes("sample_task_evaluations")}
    if "ix_sample_task_evaluations_evaluator_slug" not in indexes:
        op.create_index(
            "ix_sample_task_evaluations_evaluator_slug",
            "sample_task_evaluations",
            ["evaluator_slug"],
        )


def _drop_column_if_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> None:
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in columns:
        op.drop_column(table_name, column_name)


def _rename_run_id_to_sample_id_if_needed(inspector: sa.Inspector, table_name: str) -> None:
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "sample_id" not in columns and "run_id" in columns:
        op.alter_column(table_name, "run_id", new_column_name="sample_id")


def _add_column_if_missing(
    inspector: sa.Inspector,
    table_name: str,
    column: sa.Column,
) -> None:
    columns = {existing["name"] for existing in inspector.get_columns(table_name)}
    if column.name not in columns:
        op.add_column(table_name, column)


def _replace_sample_fk(
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
    referred_table: str,
) -> None:
    foreign_keys = inspector.get_foreign_keys(table_name)
    has_target_fk = False
    for foreign_key in foreign_keys:
        constrained_columns = foreign_key.get("constrained_columns") or []
        if constrained_columns != [column_name]:
            continue
        if foreign_key.get("referred_table") == referred_table:
            has_target_fk = True
            continue
        name = foreign_key.get("name")
        if name:
            op.drop_constraint(name, table_name, type_="foreignkey")

    if not has_target_fk:
        op.create_foreign_key(
            f"fk_{table_name}_{column_name}_{referred_table}",
            table_name,
            referred_table,
            [column_name],
            ["id"],
        )


def _drop_sample_fk(
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
) -> None:
    if table_name not in inspector.get_table_names():
        return
    for foreign_key in inspector.get_foreign_keys(table_name):
        constrained_columns = foreign_key.get("constrained_columns") or []
        if constrained_columns != [column_name]:
            continue
        name = foreign_key.get("name")
        if name:
            op.drop_constraint(name, table_name, type_="foreignkey")


def _drop_table_cascade(table_name: str) -> None:
    op.execute(sa.text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))


def _upgrade_offline() -> None:
    op.add_column(
        "sample_task_evaluations",
        sa.Column("evaluator_slug", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.execute(
        "UPDATE sample_task_evaluations "
        "SET evaluator_slug = 'unknown-evaluator' "
        "WHERE evaluator_slug IS NULL"
    )
    op.alter_column("sample_task_evaluations", "evaluator_slug", nullable=False)
    op.create_index(
        "ix_sample_task_evaluations_evaluator_slug",
        "sample_task_evaluations",
        ["evaluator_slug"],
    )
    for table_name in ("threads", "thread_messages"):
        op.alter_column(table_name, "run_id", new_column_name="sample_id")
        op.execute(
            f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{table_name}_run_id_fkey"'
        )
        op.create_foreign_key(
            f"fk_{table_name}_sample_id_samples",
            table_name,
            "samples",
            ["sample_id"],
            ["id"],
        )
    for table_name in ("sandbox_command_wal_entries", "sandbox_events"):
        op.alter_column(table_name, "run_id", new_column_name="sample_id")
        op.execute(
            f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{table_name}_run_id_fkey"'
        )
    op.add_column(
        "experiment_sampler_invocations",
        sa.Column("policy_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "experiment_sample_pool_entries",
        sa.Column("sample_ref_json", sa.JSON(), nullable=True),
    )
    op.drop_column("samples", "definition_id")
    op.drop_column("sample_task_attempts", "definition_worker_id")
    op.drop_column("sample_task_evaluations", "definition_evaluator_id")
    op.drop_column("sample_graph_edges", "definition_dependency_id")
    for table_name in (*_LEGACY_RUN_TABLES, *_DEFINITION_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")


def _downgrade_offline() -> None:
    op.add_column("samples", sa.Column("definition_id", sa.Uuid(), nullable=True))
    op.add_column(
        "sample_task_attempts",
        sa.Column("definition_worker_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "sample_task_evaluations",
        sa.Column("definition_evaluator_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "sample_graph_edges",
        sa.Column("definition_dependency_id", sa.Uuid(), nullable=True),
    )
    op.drop_index(
        "ix_sample_task_evaluations_evaluator_slug",
        table_name="sample_task_evaluations",
    )
    op.drop_column("sample_task_evaluations", "evaluator_slug")
