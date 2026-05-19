from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID, uuid4

import inngest
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionTask,
)
from ergon_core.core.application.runtime import status as graph_status
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import RunResourceKind, RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
)
from ergon_core.core.application.evaluation.scoring import aggregate_evaluation_scores
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager, DefaultSandboxManager
from ergon_core.core.application.events.task_events import TaskReadyEvent
from ergon_core.core.application.graph.lookup import GraphNodeLookup
from ergon_core.core.application.graph.propagation import (
    get_initial_ready_tasks,
    is_workflow_complete_v2,
    is_workflow_failed_v2,
    on_task_completed_or_failed,
)
from ergon_core.core.application.graph.traversal import descendant_ids
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.application.graph.models import GraphEdgeDto, GraphNodeDto, MutationMeta
from ergon_core.core.application.graph.repository import WorkflowGraphRepository
from ergon_core.core.application.workflows.orchestration import (
    FinalizedWorkflowResult,
    FinalizeWorkflowCommand,
    InitializedWorkflow,
    InitializeWorkflowCommand,
    PropagateTaskCompletionCommand,
    PropagationResult,
    RunCompletionData,
    TaskDescriptor,
    WorkflowTerminalState,
)
from ergon_core.core.application.workflows.models import (
    WorkflowBlockerRef,
    WorkflowDependencyRef,
    WorkflowExecutionRef,
    WorkflowMaterializedResourceRef,
    WorkflowMutationRef,
    WorkflowNextActionRef,
    WorkflowResourceLocationRef,
    WorkflowResourceRef,
    WorkflowTaskRef,
    WorkflowTaskWorkspaceRef,
)
from ergon_core.core.application.tasks.repository import TaskExecutionRepository
from ergon_core.core.shared.utils import require_not_none, utcnow
from sqlmodel import Session, col, select

ResourceScope = Literal["input", "upstream", "own", "children", "descendants", "visible"]


class WorkflowService:
    """Run-scoped workflow navigation and resource-copy policy.

    ``sandbox_manager_factory`` is intentionally injectable so unit tests can
    verify materialization without opening a real E2B sandbox. Production code
    uses ``DefaultSandboxManager`` today; benchmark-specific manager routing can
    be added here once the CLI has callers outside the ResearchRubrics POC.
    """

    def __init__(
        self,
        *,
        sandbox_manager_factory: Callable[[str], BaseSandboxManager] | None = None,
        graph_repository: WorkflowGraphRepository | None = None,
        task_ready_dispatcher: Callable[[UUID, UUID, UUID], Awaitable[None]] | None = None,
    ) -> None:
        self._sandbox_manager_factory = sandbox_manager_factory or self._sandbox_manager_for
        self._graph_repo = graph_repository or WorkflowGraphRepository()
        self._task_execution_repo = TaskExecutionRepository()
        self._task_ready_dispatcher = task_ready_dispatcher or self._dispatch_task_ready

    async def initialize(self, command: InitializeWorkflowCommand) -> InitializedWorkflow:
        """Load a definition, seed graph state, and return initially ready tasks."""
        with get_session() as session:
            definition = require_not_none(
                session.get(ExperimentDefinition, command.definition_id),
                f"Definition {command.definition_id} not found",
            )
            all_tasks = list(
                session.exec(
                    select(ExperimentDefinitionTask).where(
                        ExperimentDefinitionTask.experiment_definition_id == command.definition_id,
                    )
                ).all()
            )

            self._graph_repo.initialize_from_definition(
                session,
                command.run_id,
                command.definition_id,
                initial_node_status=graph_status.PENDING,
                initial_edge_status=graph_status.EDGE_PENDING,
                meta=MutationMeta(actor="system:workflow_init"),
            )
            session.commit()

            task_descriptors = [
                TaskDescriptor(
                    task_id=t.id,
                    task_slug=t.task_slug,
                    parent_task_id=t.parent_task_id,
                )
                for t in all_tasks
            ]
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
                graph_repo=self._graph_repo,
                graph_lookup=graph_lookup,
            )
            ready_id_set = set(ready_ids)
            root_count = sum(1 for t in all_tasks if t.parent_task_id is None)

            return InitializedWorkflow(
                run_id=command.run_id,
                definition_id=command.definition_id,
                benchmark_type=definition.benchmark_type,
                total_tasks=len(all_tasks),
                total_root_tasks=root_count,
                pending_tasks=task_descriptors,
                initial_ready_tasks=[td for td in task_descriptors if td.task_id in ready_id_set],
            )

    def finalize(self, command: FinalizeWorkflowCommand) -> FinalizedWorkflowResult:
        """Aggregate evaluations and close the run."""
        with get_session() as session:
            evaluations = list(
                session.exec(
                    select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == command.run_id)
                ).all()
            )
            score_summary = aggregate_evaluation_scores(evaluations)
            completion = RunCompletionData(
                completed_at=utcnow(),
                final_score=score_summary.final_score,
                normalized_score=score_summary.normalized_score,
            )
            run_record = require_not_none(
                session.get(RunRecord, command.run_id),
                f"RunRecord {command.run_id} not found",
            )
            run_record.status = RunStatus.COMPLETED
            run_record.completed_at = completion.completed_at
            run_record.summary_json = {
                "final_score": completion.final_score,
                "normalized_score": completion.normalized_score,
                "evaluators_count": score_summary.evaluators_count,
                "total_cost_usd": completion.total_cost_usd,
            }
            session.add(run_record)
            session.commit()

            return FinalizedWorkflowResult(
                run_id=command.run_id,
                final_score=score_summary.final_score,
                normalized_score=score_summary.normalized_score,
                evaluators_count=score_summary.evaluators_count,
            )

    async def propagate(self, command: PropagateTaskCompletionCommand) -> PropagationResult:
        """Handle successful task completion and schedule newly ready tasks."""
        with get_session() as session:
            node_id = command.task_id

            await self._graph_repo.update_node_status(
                session,
                run_id=command.run_id,
                node_id=node_id,
                new_status=graph_status.COMPLETED,
                meta=MutationMeta(
                    actor="system:propagation",
                    reason=f"task {command.task_id} completed",
                ),
                only_if_not_terminal=True,
            )
            newly_ready_node_ids = await on_task_completed_or_failed(
                session,
                command.run_id,
                node_id,
                graph_status.COMPLETED,
                graph_repo=self._graph_repo,
            )
            ready_descriptors = self._task_descriptors_for_nodes(session, newly_ready_node_ids)
            terminal = WorkflowTerminalState.NONE
            if is_workflow_complete_v2(session, command.run_id):
                terminal = WorkflowTerminalState.COMPLETED
            elif is_workflow_failed_v2(session, command.run_id):
                terminal = WorkflowTerminalState.FAILED

            return PropagationResult(
                run_id=command.run_id,
                definition_id=command.definition_id,
                completed_task_id=command.task_id,
                ready_tasks=ready_descriptors,
                workflow_terminal_state=terminal,
            )

    async def propagate_failure(self, command: PropagateTaskCompletionCommand) -> PropagationResult:
        """Handle task failure, block successors, and detect workflow terminal state."""
        with get_session() as session:
            node_id = command.task_id
            await self._graph_repo.update_node_status(
                session,
                run_id=command.run_id,
                node_id=node_id,
                new_status=graph_status.FAILED,
                meta=MutationMeta(
                    actor="system:propagation",
                    reason=f"task {command.task_id} failed",
                ),
                only_if_not_terminal=True,
            )
            await on_task_completed_or_failed(
                session,
                command.run_id,
                node_id,
                graph_status.FAILED,
                graph_repo=self._graph_repo,
            )

            terminal = WorkflowTerminalState.NONE
            if is_workflow_failed_v2(session, command.run_id):
                terminal = WorkflowTerminalState.FAILED

            return PropagationResult(
                run_id=command.run_id,
                definition_id=command.definition_id,
                completed_task_id=command.task_id,
                workflow_terminal_state=terminal,
            )

    async def operator_unblock(self, *, run_id: UUID, node_id: UUID, reason: str) -> None:
        with get_session() as session:
            await self._graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=node_id,
                new_status=graph_status.PENDING,
                meta=MutationMeta(actor="operator:unblock", reason=reason),
            )
            session.commit()

    async def restart_node(self, *, run_id: UUID, node_id: UUID, reason: str) -> None:
        with get_session() as session:
            await self._graph_repo.update_node_status(
                session,
                run_id=run_id,
                node_id=node_id,
                new_status=graph_status.PENDING,
                meta=MutationMeta(actor="operator:restart", reason=reason),
            )
            session.commit()

    @staticmethod
    def _task_descriptors_for_nodes(
        session: Session,
        node_ids: list[UUID],
    ) -> list[TaskDescriptor]:
        descriptors: list[TaskDescriptor] = []
        for node_id in node_ids:
            node = session.exec(select(RunGraphNode).where(RunGraphNode.task_id == node_id)).first()
            if node is not None:
                descriptors.append(
                    TaskDescriptor(
                        task_id=node.task_id,
                        task_slug=node.task_slug,
                    )
                )
        return descriptors

    def list_tasks(
        self,
        session: Session,
        *,
        run_id: UUID,
        parent_task_id: UUID | None = None,
    ) -> list[WorkflowTaskRef]:
        stmt = select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        if parent_task_id is not None:
            stmt = stmt.where(RunGraphNode.parent_task_id == parent_task_id)
        nodes = list(session.exec(stmt).all())
        nodes.sort(key=lambda node: (node.level, node.task_slug, str(node.task_id)))
        return [self._task_ref(node) for node in nodes]

    def get_task(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID | None = None,
        task_slug: str | None = None,
    ) -> WorkflowTaskRef:
        node = self._resolve_node(session, run_id=run_id, node_id=node_id, task_slug=task_slug)
        return self._task_ref(node)

    def get_latest_execution(
        self,
        session: Session,
        *,
        node_id: UUID,
    ) -> RunTaskExecution | None:
        return self._task_execution_repo.latest_for_node(session, node_id)

    def list_dependencies(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
        direction: Literal["upstream", "downstream", "both"],
    ) -> list[WorkflowDependencyRef]:
        clauses = []
        if direction in {"upstream", "both"}:
            clauses.append(RunGraphEdge.target_task_id == node_id)
        if direction in {"downstream", "both"}:
            clauses.append(RunGraphEdge.source_task_id == node_id)
        if not clauses:
            raise ValueError(f"unsupported dependency direction: {direction}")

        stmt = select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)
        if len(clauses) == 1:
            stmt = stmt.where(clauses[0])
        else:
            stmt = stmt.where(clauses[0] | clauses[1])
        edges = list(session.exec(stmt).all())
        nodes = self._nodes_by_id(session, run_id)
        return [
            WorkflowDependencyRef(
                edge_id=edge.id,
                edge_status=edge.status,
                source=self._task_ref(nodes[edge.source_task_id]),
                target=self._task_ref(nodes[edge.target_task_id]),
            )
            for edge in edges
        ]

    def list_resources(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
        scope: ResourceScope,
        kind: str | None = None,
        max_depth: int = 3,
        limit: int = 50,
    ) -> list[WorkflowResourceRef]:
        execution_ids = self._execution_ids_for_scope(
            session,
            run_id=run_id,
            node_id=node_id,
            scope=scope,
            max_depth=max_depth,
        )
        stmt = select(RunResource).where(RunResource.run_id == run_id)
        if execution_ids is not None:
            stmt = stmt.where(col(RunResource.task_execution_id).in_(execution_ids))
        if kind is not None:
            stmt = stmt.where(RunResource.kind == kind)
        resources = list(session.exec(stmt).all())
        resources.sort(key=lambda resource: (resource.created_at, resource.id), reverse=True)
        if limit >= 0:
            resources = resources[:limit]
        return [self._resource_ref(session, resource) for resource in resources]

    def read_resource_bytes(
        self,
        session: Session,
        *,
        run_id: UUID,
        resource_id: UUID,
        max_bytes: int,
    ) -> bytes:
        resource = self._resource_in_run(session, run_id=run_id, resource_id=resource_id)
        with open(resource.file_path, "rb") as handle:
            return handle.read(max_bytes)

    def get_resource_location(
        self,
        session: Session,
        *,
        run_id: UUID,
        resource_id: UUID,
    ) -> WorkflowResourceLocationRef:
        resource = self._resource_in_run(session, run_id=run_id, resource_id=resource_id)
        producer = self._producer_node_for_resource(session, resource)
        copied_name = self._copy_name(resource.name)
        default_path = self._sandbox_destination(
            destination=None,
            producer_slug=producer.task_slug if producer is not None else "unknown",
            copied_name=copied_name,
        )
        return WorkflowResourceLocationRef(
            resource=self._resource_ref(session, resource),
            producer_task_slug=producer.task_slug if producer is not None else None,
            local_file_path=resource.file_path,
            default_sandbox_path=default_path,
        )

    def get_task_workspace(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
    ) -> WorkflowTaskWorkspaceRef:
        node = self._resolve_node(session, run_id=run_id, node_id=node_id, task_slug=None)
        latest = self.get_latest_execution(session, node_id=node_id)
        own_resources: list[WorkflowResourceRef] = []
        if latest is not None:
            own_rows = list(
                session.exec(
                    select(RunResource)
                    .where(RunResource.run_id == run_id)
                    .where(RunResource.task_execution_id == latest.id),
                ).all(),
            )
            own_rows.sort(key=lambda resource: (resource.created_at, resource.id), reverse=True)
            own_resources = [self._resource_ref(session, resource) for resource in own_rows]
        return WorkflowTaskWorkspaceRef(
            task=self._task_ref(node),
            latest_execution=self._execution_ref(latest) if latest is not None else None,
            own_resources=own_resources,
            input_resources=self.list_resources(
                session,
                run_id=run_id,
                node_id=node_id,
                scope="input",
            ),
        )

    def get_task_blockers(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
    ) -> list[WorkflowBlockerRef]:
        task = self.get_task(session, run_id=run_id, node_id=node_id)
        deps = self.list_dependencies(session, run_id=run_id, node_id=node_id, direction="upstream")
        blockers: list[WorkflowBlockerRef] = []
        pending = [dep.source.task_slug for dep in deps if dep.edge_status != "satisfied"]
        if pending:
            blockers.append(
                WorkflowBlockerRef(
                    task=task,
                    reason="waiting_for_upstream",
                    details=pending,
                    suggested_commands=["inspect task-dependencies --direction upstream"],
                )
            )
        return blockers

    def get_next_actions(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
        manager_capable: bool,
    ) -> list[WorkflowNextActionRef]:
        task = self.get_task(session, run_id=run_id, node_id=node_id)
        commands = [
            "inspect task-workspace",
            "inspect resource-list --scope input",
            "inspect resource-list --scope visible --limit 20",
        ]
        if manager_capable:
            commands.append(f"manage restart-task --task-slug {task.task_slug} --dry-run")
        return [
            WorkflowNextActionRef(
                priority="normal",
                task=task,
                summary="Inspect current task state and available resources.",
                suggested_commands=commands,
            )
        ]

    async def add_task(
        self,
        session: Session,
        *,
        run_id: UUID,
        parent_task_id: UUID,
        task_slug: str,
        description: str,
        assigned_worker_slug: str,
        dry_run: bool,
    ) -> WorkflowMutationRef:
        parent = self._resolve_node(
            session,
            run_id=run_id,
            node_id=parent_task_id,
            task_slug=None,
        )
        node_ref = WorkflowTaskRef(
            task_id=uuid4(),
            task_slug=task_slug,
            status=TaskExecutionStatus.PENDING.value,
            level=parent.level + 1,
            parent_task_id=parent.task_id,
            assigned_worker_slug=assigned_worker_slug,
            description=description,
        )
        if dry_run:
            return WorkflowMutationRef(
                action="add-task",
                dry_run=True,
                node=node_ref,
                message=f"Would add task {task_slug}",
            )

        raise ValueError(
            "add-task requires an object-bound Task in the final v2 schema; "
            "use WorkerContext.spawn_task(Task(...)) for dynamic tasks."
        )

    async def add_edge(
        self,
        session: Session,
        *,
        run_id: UUID,
        source_task_slug: str,
        target_task_slug: str,
        dry_run: bool,
    ) -> WorkflowMutationRef:
        source = self._resolve_node(
            session,
            run_id=run_id,
            node_id=None,
            task_slug=source_task_slug,
        )
        target = self._resolve_node(
            session,
            run_id=run_id,
            node_id=None,
            task_slug=target_task_slug,
        )
        edge_ref = WorkflowDependencyRef(
            edge_id=uuid4(),
            edge_status="pending",
            source=self._task_ref(source),
            target=self._task_ref(target),
        )
        if dry_run:
            return WorkflowMutationRef(
                action="add-edge",
                dry_run=True,
                edge=edge_ref,
                message=f"Would add dependency {source_task_slug} -> {target_task_slug}",
            )

        created = await self._graph_repo.add_edge(
            session,
            run_id,
            source_task_id=source.task_id,
            target_task_id=target.task_id,
            status="pending",
            meta=self._meta("add-edge"),
        )
        session.commit()
        return WorkflowMutationRef(
            action="add-edge",
            dry_run=False,
            edge=self._dependency_ref_from_graph(session, run_id, created),
            message=f"Added dependency {source_task_slug} -> {target_task_slug}",
        )

    async def update_task_description(
        self,
        session: Session,
        *,
        run_id: UUID,
        task_slug: str,
        description: str,
        dry_run: bool,
    ) -> WorkflowMutationRef:
        node = self._resolve_node(session, run_id=run_id, node_id=None, task_slug=task_slug)
        if dry_run:
            return WorkflowMutationRef(
                action="update-task-description",
                dry_run=True,
                node=self._task_ref(node).model_copy(update={"description": description}),
                message=f"Would update description for {task_slug}",
            )

        updated = await self._graph_repo.update_node_field(
            session,
            run_id=run_id,
            node_id=node.task_id,
            field="description",
            value=description,
            meta=self._meta("update-task-description"),
        )
        session.commit()
        return WorkflowMutationRef(
            action="update-task-description",
            dry_run=False,
            node=self._task_ref_from_graph(updated),
            message=f"Updated description for {task_slug}",
        )

    async def materialize_resource(  # slopcop: ignore[max-function-params] -- mirrors CLI scope fields
        self,
        session: Session,
        *,
        run_id: UUID,
        current_node_id: UUID,
        current_execution_id: UUID,
        sandbox_task_key: UUID,
        benchmark_type: str,
        resource_id: UUID,
        destination: str | None,
        dry_run: bool,
    ) -> WorkflowMaterializedResourceRef:
        source = self._resource_in_run(session, run_id=run_id, resource_id=resource_id)
        producer = self._producer_node_for_resource(session, source)
        copied_name = self._copy_name(source.name)
        sandbox_path = self._sandbox_destination(
            destination=destination,
            producer_slug=producer.task_slug if producer is not None else "unknown",
            copied_name=copied_name,
        )
        result = WorkflowMaterializedResourceRef(
            source_resource_id=source.id,
            copied_resource_id=None,
            copied_from_resource_id=source.id,
            source_name=source.name,
            copied_name=PurePosixPath(sandbox_path).name,
            source_content_hash=source.content_hash,
            copied_content_hash=source.content_hash,
            sandbox_path=sandbox_path,
            dry_run=dry_run,
            source_mutated=False,
        )
        if dry_run:
            return result

        manager = self._sandbox_manager_factory(benchmark_type)
        await manager.upload_file(sandbox_task_key, source.file_path, sandbox_path)

        copy = RunResource(
            run_id=run_id,
            task_execution_id=current_execution_id,
            kind=RunResourceKind.IMPORT.value,
            name=result.copied_name,
            mime_type=source.mime_type,
            file_path=source.file_path,
            size_bytes=source.size_bytes,
            metadata_json={
                "source_resource_id": str(source.id),
                "source_task_slug": producer.task_slug if producer is not None else None,
                "sandbox_destination": sandbox_path,
            },
            error=None,
            content_hash=source.content_hash,
            copied_from_resource_id=source.id,
        )
        session.add(copy)
        session.commit()
        session.refresh(copy)
        return result.model_copy(update={"copied_resource_id": copy.id})

    @staticmethod
    def _sandbox_manager_for(benchmark_type: str) -> BaseSandboxManager:
        _ = benchmark_type
        return DefaultSandboxManager()

    @staticmethod
    def _task_ref(node: RunGraphNode) -> WorkflowTaskRef:
        return WorkflowTaskRef(
            task_id=node.task_id,
            task_slug=node.task_slug,
            status=node.status,
            level=node.level,
            parent_task_id=node.parent_task_id,
            assigned_worker_slug=node.assigned_worker_slug,
            description=node.description,
        )

    @staticmethod
    def _task_ref_from_graph(node: GraphNodeDto) -> WorkflowTaskRef:
        return WorkflowTaskRef(
            task_id=node.task_id,
            task_slug=node.task_slug,
            status=node.status,
            level=node.level,
            parent_task_id=node.parent_task_id,
            assigned_worker_slug=node.assigned_worker_slug,
            description=node.description,
        )

    def _dependency_ref_from_graph(
        self,
        session: Session,
        run_id: UUID,
        edge: GraphEdgeDto,
    ) -> WorkflowDependencyRef:
        nodes = self._nodes_by_id(session, run_id)
        return WorkflowDependencyRef(
            edge_id=edge.id,
            edge_status=edge.status,
            source=self._task_ref(nodes[edge.source_task_id]),
            target=self._task_ref(nodes[edge.target_task_id]),
        )

    @staticmethod
    def _meta(action: str) -> MutationMeta:
        return MutationMeta(actor="workflow-cli", reason=action)

    def _resolve_definition_id(self, session: Session, run_id: UUID) -> UUID:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise ValueError(f"run {run_id} not found")
        return run.definition_id

    async def _dispatch_task_ready(self, run_id: UUID, definition_id: UUID, node_id: UUID) -> None:
        event = TaskReadyEvent(
            run_id=run_id,
            definition_id=definition_id,
            task_id=node_id,
        )
        await inngest_client.send(
            inngest.Event(
                name=TaskReadyEvent.name,
                data=event.model_dump(mode="json"),
            )
        )

    def _resource_ref(self, session: Session, resource: RunResource) -> WorkflowResourceRef:
        producer = self._producer_node_for_resource(session, resource)
        return WorkflowResourceRef(
            resource_id=resource.id,
            run_id=resource.run_id,
            task_execution_id=resource.task_execution_id,
            node_id=producer.task_id if producer is not None else None,
            task_slug=producer.task_slug if producer is not None else None,
            kind=resource.kind,
            name=resource.name,
            mime_type=resource.mime_type,
            size_bytes=resource.size_bytes,
            file_path=resource.file_path,
            content_hash=resource.content_hash,
            copied_from_resource_id=resource.copied_from_resource_id,
            created_at=resource.created_at,
        )

    @staticmethod
    def _execution_ref(execution: RunTaskExecution) -> WorkflowExecutionRef:
        return WorkflowExecutionRef(
            execution_id=execution.id,
            status=execution.status,
            attempt_number=execution.attempt_number,
            final_assistant_message=execution.final_assistant_message,
        )

    @staticmethod
    def _resource_in_run(session: Session, *, run_id: UUID, resource_id: UUID) -> RunResource:
        resource = session.get(RunResource, resource_id)
        if resource is None or resource.run_id != run_id:
            raise ValueError(f"resource {resource_id} is not visible in current run")
        return resource

    @staticmethod
    def _resolve_node(
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID | None,
        task_slug: str | None,
    ) -> RunGraphNode:
        if node_id is None and task_slug is None:
            raise ValueError("node_id or task_slug is required")
        stmt = select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        if node_id is not None:
            stmt = stmt.where(RunGraphNode.task_id == node_id)
        if task_slug is not None:
            stmt = stmt.where(RunGraphNode.task_slug == task_slug)
        rows = list(session.exec(stmt).all())
        if len(rows) != 1:
            raise ValueError(f"expected exactly one task, got {len(rows)}")
        return rows[0]

    @staticmethod
    def _nodes_by_id(session: Session, run_id: UUID) -> dict[UUID, RunGraphNode]:
        nodes = list(session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all())
        return {node.task_id: node for node in nodes}

    def _execution_ids_for_scope(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
        scope: ResourceScope,
        max_depth: int,
    ) -> set[UUID] | None:
        if scope == "visible":
            return None
        node_ids = self._node_ids_for_scope(
            session,
            run_id=run_id,
            node_id=node_id,
            scope=scope,
            max_depth=max_depth,
        )
        executions = []
        for current_node_id in node_ids:
            execution = self.get_latest_execution(session, node_id=current_node_id)
            if execution is not None and execution.status == TaskExecutionStatus.COMPLETED:
                executions.append(execution.id)
        return set(executions)

    def _node_ids_for_scope(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
        scope: ResourceScope,
        max_depth: int,
    ) -> set[UUID]:
        if scope == "own":
            return {node_id}
        if scope in {"input", "upstream"}:
            edges = session.exec(
                select(RunGraphEdge).where(
                    RunGraphEdge.run_id == run_id,
                    RunGraphEdge.target_task_id == node_id,
                )
            ).all()
            return {edge.source_task_id for edge in edges}
        if scope == "children":
            children = session.exec(
                select(RunGraphNode).where(
                    RunGraphNode.run_id == run_id,
                    RunGraphNode.parent_task_id == node_id,
                )
            ).all()
            return {child.task_id for child in children}
        if scope == "descendants":
            return self._descendant_ids(
                session, run_id=run_id, node_id=node_id, max_depth=max_depth
            )
        raise ValueError(f"unsupported resource scope: {scope}")

    def _descendant_ids(
        self,
        session: Session,
        *,
        run_id: UUID,
        node_id: UUID,
        max_depth: int,
    ) -> set[UUID]:
        return descendant_ids(session, run_id=run_id, root_node_id=node_id, max_depth=max_depth)

    @staticmethod
    def _producer_node_for_resource(
        session: Session,
        resource: RunResource,
    ) -> RunGraphNode | None:
        if resource.task_execution_id is None:
            return None
        execution = session.get(RunTaskExecution, resource.task_execution_id)
        if execution is None:
            return None
        return session.get(RunGraphNode, (execution.run_id, execution.task_id))

    @staticmethod
    def _copy_name(name: str) -> str:
        path = PurePosixPath(name)
        suffix = "".join(path.suffixes)
        if suffix:
            stem = name[: -len(suffix)]
            return f"{stem} (copy){suffix}"
        return f"{name} (copy)"

    @staticmethod
    def _sandbox_destination(
        *,
        destination: str | None,
        producer_slug: str,
        copied_name: str,
    ) -> str:
        if destination is None:
            relative = PurePosixPath("imported") / producer_slug / copied_name
        else:
            requested = PurePosixPath(destination)
            relative = requested.parent / copied_name
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("destination must stay inside /workspace")
        return str(PurePosixPath("/workspace") / relative)
