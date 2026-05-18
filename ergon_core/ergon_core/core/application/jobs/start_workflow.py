"""Inngest function: workflow initialization and first-task dispatch."""

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from ergon_core.core.infrastructure.dashboard.event_contracts import TaskTreeNode, WorkerRef
from ergon_core.core.infrastructure.dashboard.provider import get_dashboard_emitter
from ergon_core.core.persistence.definitions.models import ExperimentDefinitionWorker
from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.application.events.task_events import (
    TaskReadyEvent,
    WorkflowStartedEvent,
)
from ergon_core.core.infrastructure.inngest.client import InngestEvent, inngest_client
from ergon_core.core.application.jobs.models import WorkflowStartResult
from ergon_core.core.application.workflows.orchestration import InitializeWorkflowCommand
from ergon_core.core.application.workflows.service import WorkflowService
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    workflow_start_context,
)
from sqlmodel import select

logger = logging.getLogger(__name__)

# Stable namespace used to derive deterministic UUIDs for worker binding keys
# that have no ExperimentDefinitionWorker row (or for synthetic placeholders).
# reason: the dashboard Zod contract (WorkerRefSchema) requires a UUID for
# `assigned_to.id`, but graph nodes only carry the binding_key string.
_WORKER_SLUG_NS = UUID("8e4d1a0e-2f21-4d6f-8f7d-9f0c2e5a1b77")


def _worker_ref_for_slug(
    slug: str | None,
    worker_rows_by_key: dict[str, ExperimentDefinitionWorker],
) -> WorkerRef:
    """Return a ``WorkerRef`` matching the dashboard's WorkerRefSchema.

    Falls back to a deterministic synthetic ref if the slug is unknown so the
    emitted event still validates.
    """
    if slug is not None and slug in worker_rows_by_key:
        row = worker_rows_by_key[slug]
        return WorkerRef(id=str(row.id), name=row.binding_key, type=row.worker_type)
    # Synthetic ref: deterministic id derived from the slug so consumers can
    # dedupe across events, but the row itself is absent from the DB.
    synthetic_slug = slug or "unassigned"
    return WorkerRef(
        id=str(uuid5(_WORKER_SLUG_NS, synthetic_slug)),
        name=synthetic_slug,
        type="unknown",
    )


def _build_task_tree_for_run(
    run_id: UUID,
    definition_id: UUID,
) -> TaskTreeNode:
    """Build the nested task tree expected by the dashboard Zod schema.

    Reads RunGraphNode/RunGraphEdge rows for the run and ExperimentDefinitionWorker
    rows for the definition. Returns a single-rooted ``TaskTreeNode``; if the
    run has multiple roots (typical for multi-instance cohorts), a synthetic
    wrapper root is produced so the tree is always single-rooted.
    """
    with get_session() as session:
        node_rows = list(
            session.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()
        )
        edge_rows = list(
            session.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all()
        )
        worker_rows = list(
            session.exec(
                select(ExperimentDefinitionWorker).where(
                    ExperimentDefinitionWorker.experiment_definition_id == definition_id,
                )
            ).all()
        )

    worker_rows_by_key: dict[str, ExperimentDefinitionWorker] = {
        w.binding_key: w for w in worker_rows
    }

    # children_by_parent: parent_task_id -> [child_task_id]
    children_by_parent: dict[UUID | None, list[UUID]] = {}
    node_by_id: dict[UUID, RunGraphNode] = {n.task_id: n for n in node_rows}
    for n in node_rows:
        children_by_parent.setdefault(n.parent_task_id, []).append(n.task_id)

    # depends_on_by_target: target_task_id -> [source_task_id]
    # Edges are stored as source=dependency, target=dependent task.
    depends_on_by_target: dict[UUID, list[UUID]] = {}
    for e in edge_rows:
        depends_on_by_target.setdefault(e.target_task_id, []).append(e.source_task_id)

    def build(node_id: UUID) -> TaskTreeNode:
        node = node_by_id[node_id]
        child_ids = children_by_parent.get(node_id, [])
        return TaskTreeNode(
            id=str(node.task_id),
            name=node.task_slug,
            description=node.description,
            status=node.status,
            level=node.level,
            assigned_worker_slug=node.assigned_worker_slug,
            assigned_to=_worker_ref_for_slug(node.assigned_worker_slug, worker_rows_by_key),
            children=[build(c) for c in child_ids],
            depends_on=[str(s) for s in depends_on_by_target.get(node_id, [])],
            is_leaf=not child_ids,
            resources=[],
            parent_id=str(node.parent_task_id) if node.parent_task_id else None,
        )

    root_ids = children_by_parent.get(None, [])
    if len(root_ids) == 1:
        return build(root_ids[0])

    # Multiple (or zero) roots: wrap in a synthetic root so the dashboard's
    # single-rooted Zod contract is satisfied.
    synthetic_id = uuid4()
    children = [build(r) for r in root_ids]
    return TaskTreeNode(
        id=str(synthetic_id),
        name="workflow",
        description="Synthetic root node wrapping all definition roots.",
        status="pending",
        level=-1,
        assigned_worker_slug=None,
        assigned_to=_worker_ref_for_slug(None, worker_rows_by_key),
        children=children,
        depends_on=[],
        is_leaf=not children,
        resources=[],
        parent_id=None,
    )


async def run_start_workflow_job(payload: WorkflowStartedEvent) -> WorkflowStartResult:
    logger.info("workflow-start run_id=%s definition_id=%s", payload.run_id, payload.definition_id)
    span_start = datetime.now(UTC)

    svc = WorkflowService()
    initialized = await svc.initialize(
        InitializeWorkflowCommand(
            run_id=payload.run_id,
            definition_id=payload.definition_id,
        )
    )

    events = [
        InngestEvent(
            name=TaskReadyEvent.name,
            data=TaskReadyEvent(
                run_id=payload.run_id,
                definition_id=payload.definition_id,
                task_id=td.task_id,
            ).model_dump(mode="json"),
        )
        for td in initialized.initial_ready_tasks
    ]

    if events:
        await inngest_client.send(events)

    task_tree = _build_task_tree_for_run(payload.run_id, payload.definition_id)

    await get_dashboard_emitter().workflow_started(
        run_id=payload.run_id,
        definition_id=payload.definition_id,
        workflow_name=initialized.benchmark_type,
        task_tree=task_tree,
        total_tasks=initialized.total_tasks,
        total_leaf_tasks=initialized.total_tasks - initialized.total_root_tasks,
    )

    result = WorkflowStartResult(
        run_id=payload.run_id,
        initial_ready_tasks=len(initialized.initial_ready_tasks),
        total_tasks=initialized.total_tasks,
    )

    get_trace_sink().emit_span(
        CompletedSpan(
            name="workflow.start",
            context=workflow_start_context(payload.run_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(payload.run_id),
                "definition_id": str(payload.definition_id),
                "total_tasks": initialized.total_tasks,
                "initial_ready_tasks": len(initialized.initial_ready_tasks),
            },
        )
    )

    logger.info(
        "workflow-start completed: %d initial tasks of %d total",
        result.initial_ready_tasks,
        result.total_tasks,
    )
    return result
