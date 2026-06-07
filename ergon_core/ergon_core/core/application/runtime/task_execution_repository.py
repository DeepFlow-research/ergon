"""Task execution domain repository."""

from uuid import UUID

from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.telemetry.models import SampleTaskAttempt
from sqlalchemy import update
from sqlmodel import Session, col, select


class WorkerOutputNotFound(LookupError):
    """Raised when ``WorkerOutputRepository.load`` finds no persisted output."""

    def __init__(self, *, execution_id: UUID) -> None:
        super().__init__(f"No worker output persisted for execution {execution_id}")
        self.execution_id = execution_id


class TaskExecutionRepository:
    """Domain queries over task execution rows."""

    def latest_for_node(self, session: Session, task_id: UUID) -> SampleTaskAttempt | None:
        stmt = (
            select(SampleTaskAttempt)
            .where(SampleTaskAttempt.task_id == task_id)
            .order_by(
                col(SampleTaskAttempt.created_at).desc(),
                col(SampleTaskAttempt.id).desc(),
            )
            .limit(1)
        )
        return session.exec(stmt).first()

    def list_children_of_execution(
        self,
        session: Session,
        parent_execution_id: UUID,
    ) -> list[SampleTaskAttempt]:
        parent = session.get(SampleTaskAttempt, parent_execution_id)
        if parent is None:
            return []
        child_task_ids_stmt = select(SampleGraphNode.task_id).where(
            SampleGraphNode.parent_task_id == parent.task_id
        )
        stmt = select(SampleTaskAttempt).where(
            col(SampleTaskAttempt.task_id).in_(child_task_ids_stmt)
        )
        return list(session.exec(stmt).all())

    async def set_sandbox_id(
        self,
        session: Session,
        *,
        execution_id: UUID,
        sandbox_id: str,
    ) -> None:
        """Stamp the live sandbox id on a task execution row.

        Called by ``worker_execute`` immediately after acquiring a sandbox so
        that per-evaluator workers can re-attach to the same external sandbox
        through ``graph_repo.node(..., sandbox_id=...)``. The caller commits.
        """

        session.exec(
            update(SampleTaskAttempt)
            .where(SampleTaskAttempt.id == execution_id)
            .values(sandbox_id=sandbox_id)
        )


class WorkerOutputRepository:
    """Persisted ``WorkerOutput`` keyed by ``execution_id``.

    The orchestrator (``worker_execute``) persists the terminal worker output
    before fanning out per-evaluator invocations; each eval worker reloads it
    from a thin id-only payload. Storage lives on ``SampleTaskAttempt`` —
    keeping the execution row authoritative for everything the eval workers
    need keeps the run-tier read boundary one query wide.
    """

    async def persist(
        self,
        session: Session,
        *,
        execution_id: UUID,
        output: WorkerOutput,
    ) -> None:
        """Write ``output`` onto the execution row. Caller commits."""

        session.exec(
            update(SampleTaskAttempt)
            .where(SampleTaskAttempt.id == execution_id)
            .values(worker_output_json=output.model_dump(mode="json"))
        )

    async def load(
        self,
        session: Session,
        *,
        execution_id: UUID,
    ) -> WorkerOutput:
        """Return the persisted ``WorkerOutput`` for ``execution_id``.

        Raises ``WorkerOutputNotFound`` when the orchestrator never wrote one
        (e.g. retry replay before the persist step committed) — the eval
        worker fails loudly rather than silently evaluating a missing output.
        """

        row = session.get(SampleTaskAttempt, execution_id)
        if row is None or row.worker_output_json is None:
            raise WorkerOutputNotFound(execution_id=execution_id)
        return WorkerOutput.model_validate(row.worker_output_json)
