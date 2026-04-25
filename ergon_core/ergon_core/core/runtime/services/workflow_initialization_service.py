"""Workflow initialization: load definitions, seed graph state, find initial tasks."""

from ergon_builtins.registry import BENCHMARKS
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionTask,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.runtime.execution.propagation import get_initial_ready_tasks
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_lookup import GraphNodeLookup
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.orchestration_dto import (
    InitializedWorkflow,
    InitializeWorkflowCommand,
    TaskDescriptor,
)
from ergon_core.core.utils import require_not_none, utcnow
from sqlmodel import select


class WorkflowInitializationService:
    async def initialize(self, command: InitializeWorkflowCommand) -> InitializedWorkflow:
        with get_session() as session:
            definition = require_not_none(
                session.get(ExperimentDefinition, command.definition_id),
                f"Definition {command.definition_id} not found",
            )
            benchmark_cls = require_not_none(
                BENCHMARKS.get(definition.benchmark_type),
                f"Benchmark {definition.benchmark_type!r} not found",
            )

            tasks_stmt = select(ExperimentDefinitionTask).where(
                ExperimentDefinitionTask.experiment_definition_id == command.definition_id,
            )
            all_tasks = list(session.exec(tasks_stmt).all())

            task_descriptors = [
                TaskDescriptor(
                    task_id=t.id,
                    task_slug=t.task_slug,
                    parent_task_id=t.parent_task_id,
                )
                for t in all_tasks
            ]

            graph_repo = WorkflowGraphRepository()
            graph_repo.initialize_from_definition(
                session,
                command.run_id,
                command.definition_id,
                initial_node_status=TaskExecutionStatus.PENDING,
                initial_edge_status="pending",
                task_payload_model=benchmark_cls.task_payload_model,
                meta=MutationMeta(actor="system:workflow_init"),
            )
            session.commit()

            graph_lookup = GraphNodeLookup(session, command.run_id)

            run_record = require_not_none(
                session.get(RunRecord, command.run_id),
                f"RunRecord {command.run_id} not found",
            )
            run_record.status = RunStatus.EXECUTING
            run_record.started_at = utcnow()
            session.add(run_record)
            session.commit()

            ready_ids = await get_initial_ready_tasks(
                session,
                command.run_id,
                command.definition_id,
                graph_repo=graph_repo,
                graph_lookup=graph_lookup,
            )

            ready_descriptors = [td for td in task_descriptors if td.task_id in set(ready_ids)]

            root_count = sum(1 for t in all_tasks if t.parent_task_id is None)

            return InitializedWorkflow(
                run_id=command.run_id,
                definition_id=command.definition_id,
                benchmark_type=definition.benchmark_type,
                total_tasks=len(all_tasks),
                total_root_tasks=root_count,
                pending_tasks=task_descriptors,
                initial_ready_tasks=ready_descriptors,
            )
