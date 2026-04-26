from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID, uuid4

from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.shared.enums import TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import (
    RunResource,
    RunResourceKind,
    RunTaskExecution,
)
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager, DefaultSandboxManager
from ergon_core.core.runtime.services.graph_dto import GraphEdgeDto, GraphNodeDto, MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.workflow_dto import (
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
    ) -> None:
        self._sandbox_manager_factory = sandbox_manager_factory or self._sandbox_manager_for
        self._graph_repo = graph_repository or WorkflowGraphRepository()

    def list_tasks(
        self,
        session: Session,
        *,
        run_id: UUID,
        parent_node_id: UUID | None = None,
    ) -> list[WorkflowTaskRef]:
        stmt = select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        if parent_node_id is not None:
            stmt = stmt.where(RunGraphNode.parent_node_id == parent_node_id)
        nodes = list(session.exec(stmt).all())
        nodes.sort(key=lambda node: (node.level, node.task_slug, str(node.id)))
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
        stmt = (
            select(RunTaskExecution)
            .where(RunTaskExecution.node_id == node_id)
            .order_by(
                col(RunTaskExecution.attempt_number).desc(),
                col(RunTaskExecution.started_at).desc(),
            )
            .limit(1)
        )
        return session.exec(stmt).first()

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
            clauses.append(RunGraphEdge.target_node_id == node_id)
        if direction in {"downstream", "both"}:
            clauses.append(RunGraphEdge.source_node_id == node_id)
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
                source=self._task_ref(nodes[edge.source_node_id]),
                target=self._task_ref(nodes[edge.target_node_id]),
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
        parent_node_id: UUID,
        task_slug: str,
        description: str,
        assigned_worker_slug: str,
        dry_run: bool,
    ) -> WorkflowMutationRef:
        parent = self._resolve_node(
            session,
            run_id=run_id,
            node_id=parent_node_id,
            task_slug=None,
        )
        node_ref = WorkflowTaskRef(
            node_id=uuid4(),
            task_slug=task_slug,
            status=TaskExecutionStatus.PENDING.value,
            level=parent.level + 1,
            parent_node_id=parent.id,
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

        created = await self._graph_repo.add_node(
            session,
            run_id,
            task_slug=task_slug,
            instance_key=parent.instance_key,
            description=description,
            status=TaskExecutionStatus.PENDING.value,
            assigned_worker_slug=assigned_worker_slug,
            parent_node_id=parent.id,
            level=parent.level + 1,
            meta=self._meta("add-task"),
        )
        session.commit()
        return WorkflowMutationRef(
            action="add-task",
            dry_run=False,
            node=self._task_ref_from_graph(created),
            message=f"Added task {task_slug}",
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
            source_node_id=source.id,
            target_node_id=target.id,
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
            node_id=node.id,
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

    async def restart_task(
        self,
        session: Session,
        *,
        run_id: UUID,
        task_slug: str,
        dry_run: bool,
    ) -> WorkflowMutationRef:
        return await self._set_task_status(
            session,
            run_id=run_id,
            task_slug=task_slug,
            action="restart-task",
            status=TaskExecutionStatus.PENDING.value,
            dry_run=dry_run,
        )

    async def abandon_task(
        self,
        session: Session,
        *,
        run_id: UUID,
        task_slug: str,
        dry_run: bool,
    ) -> WorkflowMutationRef:
        return await self._set_task_status(
            session,
            run_id=run_id,
            task_slug=task_slug,
            action="abandon-task",
            status=TaskExecutionStatus.CANCELLED.value,
            dry_run=dry_run,
        )

    async def _set_task_status(
        self,
        session: Session,
        *,
        run_id: UUID,
        task_slug: str,
        action: str,
        status: str,
        dry_run: bool,
    ) -> WorkflowMutationRef:
        node = self._resolve_node(session, run_id=run_id, node_id=None, task_slug=task_slug)
        if dry_run:
            return WorkflowMutationRef(
                action=action,
                dry_run=True,
                node=self._task_ref(node).model_copy(update={"status": status}),
                message=f"Would set {task_slug} to {status}",
            )
        await self._graph_repo.update_node_status(
            session,
            run_id=run_id,
            node_id=node.id,
            new_status=status,
            meta=self._meta(action),
        )
        session.commit()
        refreshed = self._resolve_node(session, run_id=run_id, node_id=None, task_slug=task_slug)
        return WorkflowMutationRef(
            action=action,
            dry_run=False,
            node=self._task_ref(refreshed),
            message=f"Set {task_slug} to {status}",
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
            node_id=node.id,
            task_slug=node.task_slug,
            status=node.status,
            level=node.level,
            parent_node_id=node.parent_node_id,
            assigned_worker_slug=node.assigned_worker_slug,
            description=node.description,
        )

    @staticmethod
    def _task_ref_from_graph(node: GraphNodeDto) -> WorkflowTaskRef:
        return WorkflowTaskRef(
            node_id=node.id,
            task_slug=node.task_slug,
            status=node.status,
            level=node.level,
            parent_node_id=node.parent_node_id,
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
            source=self._task_ref(nodes[edge.source_node_id]),
            target=self._task_ref(nodes[edge.target_node_id]),
        )

    @staticmethod
    def _meta(action: str) -> MutationMeta:
        return MutationMeta(actor="workflow-cli", reason=action)

    def _resource_ref(self, session: Session, resource: RunResource) -> WorkflowResourceRef:
        producer = self._producer_node_for_resource(session, resource)
        return WorkflowResourceRef(
            resource_id=resource.id,
            run_id=resource.run_id,
            task_execution_id=resource.task_execution_id,
            node_id=producer.id if producer is not None else None,
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
            stmt = stmt.where(RunGraphNode.id == node_id)
        if task_slug is not None:
            stmt = stmt.where(RunGraphNode.task_slug == task_slug)
        rows = list(session.exec(stmt).all())
        if len(rows) != 1:
            raise ValueError(f"expected exactly one task, got {len(rows)}")
        return rows[0]

    @staticmethod
    def _nodes_by_id(session: Session, run_id: UUID) -> dict[UUID, RunGraphNode]:
        nodes = list(session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all())
        return {node.id: node for node in nodes}

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
                    RunGraphEdge.target_node_id == node_id,
                )
            ).all()
            return {edge.source_node_id for edge in edges}
        if scope == "children":
            children = session.exec(
                select(RunGraphNode).where(
                    RunGraphNode.run_id == run_id,
                    RunGraphNode.parent_node_id == node_id,
                )
            ).all()
            return {child.id for child in children}
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
        result: set[UUID] = set()
        frontier = {node_id}
        for _ in range(max_depth):
            children = session.exec(
                select(RunGraphNode).where(
                    RunGraphNode.run_id == run_id,
                    col(RunGraphNode.parent_node_id).in_(frontier),
                )
            ).all()
            frontier = {child.id for child in children}
            result.update(frontier)
            if not frontier:
                break
        return result

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
        return session.get(RunGraphNode, execution.node_id)

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
