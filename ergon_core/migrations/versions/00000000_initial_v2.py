"""Initial v2 schema.

Revision ID: 00000000
Revises:
Create Date: 2026-05-18
"""

from importlib import import_module

from alembic import op
from sqlmodel import SQLModel


for module_name in (
    "ergon_core.core.persistence.context.models",
    "ergon_core.core.persistence.definitions.models",
    "ergon_core.core.persistence.graph.models",
    "ergon_core.core.persistence.samples.models",
    "ergon_core.core.persistence.telemetry.models",
):
    import_module(module_name)


revision = "00000000"
down_revision = None
branch_labels = None
depends_on = None

INITIAL_TABLES = (
    "experiment_definitions",
    "experiment_definition_workers",
    "experiment_definition_evaluators",
    "experiment_definition_instances",
    "experiment_definition_tasks",
    "experiment_definition_task_dependencies",
    "experiment_definition_task_assignments",
    "experiment_definition_task_evaluators",
    "samples",
    "sample_graph_nodes",
    "sample_graph_edges",
    "sample_status_events",
    "sample_task_events",
    "sample_edge_events",
    "sample_worker_events",
    "sample_evaluator_events",
    "sample_sandbox_events",
    "sample_annotation_events",
    "sample_context_events",
    "sample_task_attempts",
    "sample_resources",
    "sample_task_evaluations",
    "threads",
    "thread_messages",
    "rollout_batches",
    "rollout_batch_sample_memberships",
    "sandbox_command_wal_entries",
    "sandbox_events",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in INITIAL_TABLES:
        SQLModel.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(INITIAL_TABLES):
        SQLModel.metadata.tables[table_name].drop(bind, checkfirst=True)
