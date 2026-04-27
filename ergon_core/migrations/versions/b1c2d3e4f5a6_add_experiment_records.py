"""add experiment records

Revision ID: b1c2d3e4f5a6
Revises: 0a1b2c3d4e5f
Create Date: 2026-04-27 11:35:00.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "0a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cohort_id", sa.Uuid(), nullable=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("benchmark_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("sample_selection_json", sa.JSON(), nullable=False),
        sa.Column("default_worker_team_json", sa.JSON(), nullable=False),
        sa.Column("default_evaluator_slug", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("default_model_target", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("design_json", sa.JSON(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["cohort_id"], ["experiment_cohorts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_experiments_benchmark_type"), "experiments", ["benchmark_type"])
    op.create_index(op.f("ix_experiments_cohort_id"), "experiments", ["cohort_id"])
    op.create_index(op.f("ix_experiments_name"), "experiments", ["name"])
    op.create_index(op.f("ix_experiments_status"), "experiments", ["status"])

    op.add_column("runs", sa.Column("experiment_id", sa.Uuid(), nullable=True))
    op.add_column("runs", sa.Column("workflow_definition_id", sa.Uuid(), nullable=True))
    op.add_column("runs", sa.Column("benchmark_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("runs", sa.Column("instance_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("runs", sa.Column("sample_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("runs", sa.Column("worker_team_json", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("runs", sa.Column("evaluator_slug", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("runs", sa.Column("model_target", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("runs", sa.Column("assignment_json", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("runs", sa.Column("seed", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_runs_experiment_id", "runs", "experiments", ["experiment_id"], ["id"])
    op.create_foreign_key(
        "fk_runs_workflow_definition_id",
        "runs",
        "experiment_definitions",
        ["workflow_definition_id"],
        ["id"],
    )

    _migrate_existing_runs()

    op.alter_column("runs", "experiment_id", nullable=False)
    op.alter_column("runs", "workflow_definition_id", nullable=False)
    op.alter_column("runs", "benchmark_type", nullable=False)
    op.alter_column("runs", "instance_key", nullable=False)
    op.create_index(op.f("ix_runs_experiment_id"), "runs", ["experiment_id"])
    op.create_index(op.f("ix_runs_workflow_definition_id"), "runs", ["workflow_definition_id"])
    op.create_index(op.f("ix_runs_benchmark_type"), "runs", ["benchmark_type"])
    op.create_index(op.f("ix_runs_instance_key"), "runs", ["instance_key"])
    op.create_index(op.f("ix_runs_sample_id"), "runs", ["sample_id"])
    op.create_index(op.f("ix_runs_evaluator_slug"), "runs", ["evaluator_slug"])

    op.drop_index(op.f("ix_runs_cohort_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_experiment_definition_id"), table_name="runs")
    op.drop_column("runs", "cohort_id")
    op.drop_column("runs", "experiment_definition_id")


def downgrade() -> None:
    op.add_column("runs", sa.Column("experiment_definition_id", sa.Uuid(), nullable=True))
    op.add_column("runs", sa.Column("cohort_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_runs_experiment_definition_id",
        "runs",
        "experiment_definitions",
        ["experiment_definition_id"],
        ["id"],
    )
    op.create_foreign_key("fk_runs_cohort_id", "runs", "experiment_cohorts", ["cohort_id"], ["id"])

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE runs
            SET
              experiment_definition_id = workflow_definition_id,
              cohort_id = experiments.cohort_id
            FROM experiments
            WHERE runs.experiment_id = experiments.id
            """
        )
    )

    op.alter_column("runs", "experiment_definition_id", nullable=False)
    op.create_index(op.f("ix_runs_experiment_definition_id"), "runs", ["experiment_definition_id"])
    op.create_index(op.f("ix_runs_cohort_id"), "runs", ["cohort_id"])

    op.drop_index(op.f("ix_runs_evaluator_slug"), table_name="runs")
    op.drop_index(op.f("ix_runs_sample_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_instance_key"), table_name="runs")
    op.drop_index(op.f("ix_runs_benchmark_type"), table_name="runs")
    op.drop_index(op.f("ix_runs_workflow_definition_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_experiment_id"), table_name="runs")
    op.drop_constraint("fk_runs_workflow_definition_id", "runs", type_="foreignkey")
    op.drop_constraint("fk_runs_experiment_id", "runs", type_="foreignkey")
    op.drop_column("runs", "seed")
    op.drop_column("runs", "assignment_json")
    op.drop_column("runs", "model_target")
    op.drop_column("runs", "evaluator_slug")
    op.drop_column("runs", "worker_team_json")
    op.drop_column("runs", "sample_id")
    op.drop_column("runs", "instance_key")
    op.drop_column("runs", "benchmark_type")
    op.drop_column("runs", "workflow_definition_id")
    op.drop_column("runs", "experiment_id")

    op.drop_index(op.f("ix_experiments_status"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_name"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_cohort_id"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_benchmark_type"), table_name="experiments")
    op.drop_table("experiments")


def _migrate_existing_runs() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT
              runs.id AS run_id,
              runs.experiment_definition_id AS definition_id,
              runs.cohort_id AS cohort_id,
              runs.status AS run_status,
              runs.created_at AS created_at,
              runs.started_at AS started_at,
              runs.completed_at AS completed_at,
              experiment_definitions.benchmark_type AS benchmark_type
            FROM runs
            JOIN experiment_definitions
              ON experiment_definitions.id = runs.experiment_definition_id
            """
        )
    ).mappings()

    for row in rows:
        experiment_id = uuid4()
        instance_key = _first_instance_key(connection, row["definition_id"]) or f"migrated-{row['run_id']}"
        metadata = {
            "migrated_from_legacy_run": True,
            "source_run_id": str(row["run_id"]),
            "source_experiment_definition_id": str(row["definition_id"]),
        }
        connection.execute(
            sa.text(
                """
                INSERT INTO experiments (
                  id, cohort_id, name, benchmark_type, sample_count,
                  sample_selection_json, default_worker_team_json,
                  design_json, metadata_json, status, created_at, started_at, completed_at
                )
                VALUES (
                  :id, :cohort_id, :name, :benchmark_type, :sample_count,
                  CAST(:sample_selection_json AS JSON), CAST(:default_worker_team_json AS JSON),
                  CAST(:design_json AS JSON), CAST(:metadata_json AS JSON),
                  :status, :created_at, :started_at, :completed_at
                )
                """
            ),
            {
                "id": experiment_id,
                "cohort_id": row["cohort_id"],
                "name": f"Migrated experiment for run {row['run_id']}",
                "benchmark_type": row["benchmark_type"],
                "sample_count": 1,
                "sample_selection_json": json.dumps({"instance_keys": [instance_key]}),
                "default_worker_team_json": json.dumps({}),
                "design_json": json.dumps({}),
                "metadata_json": json.dumps(metadata),
                "status": row["run_status"],
                "created_at": row["created_at"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
            },
        )
        connection.execute(
            sa.text(
                """
                UPDATE runs
                SET
                  experiment_id = :experiment_id,
                  workflow_definition_id = :workflow_definition_id,
                  benchmark_type = :benchmark_type,
                  instance_key = :instance_key
                WHERE id = :run_id
                """
            ),
            {
                "experiment_id": experiment_id,
                "workflow_definition_id": row["definition_id"],
                "benchmark_type": row["benchmark_type"],
                "instance_key": instance_key,
                "run_id": row["run_id"],
            },
        )


def _first_instance_key(connection, definition_id) -> str | None:
    row = connection.execute(
        sa.text(
            """
            SELECT instance_key
            FROM experiment_definition_instances
            WHERE experiment_definition_id = :definition_id
            ORDER BY created_at ASC
            LIMIT 1
            """
        ),
        {"definition_id": definition_id},
    ).first()
    if row is None:
        return None
    return row[0]
