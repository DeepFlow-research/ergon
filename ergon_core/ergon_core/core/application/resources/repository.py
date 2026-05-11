"""Resource repository."""

from uuid import UUID

from ergon_core.core.persistence.telemetry.models import RunResource
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.shared.json_types import JsonObject
from sqlmodel import Session, select


class RunResourceRepository:
    """Domain repository for append-only run resource rows."""

    def list_by_run(self, session: Session, run_id: UUID) -> list[RunResource]:
        stmt = select(RunResource).where(RunResource.run_id == run_id)
        return list(session.exec(stmt).all())

    def list_for_task_scope(
        self,
        session: Session,
        *,
        run_id: UUID,
        task_id: UUID,
        scope: str,
    ) -> list[RunResource]:
        """List resources for WorkerContext's curated scopes."""
        if scope == "run":
            return self.list_by_run(session, run_id)

        task_ids = [task_id]
        if scope in {"children", "descendants"}:
            task_ids = self._descendant_task_ids(
                session,
                run_id=run_id,
                root_task_id=task_id,
                direct_only=scope == "children",
            )
        elif scope != "own":
            raise ValueError(f"unknown resource scope: {scope}")

        execution_ids = session.exec(
            select(RunTaskExecution.id).where(
                RunTaskExecution.run_id == run_id,
                RunTaskExecution.task_id.in_(task_ids),
            )
        ).all()
        if not execution_ids:
            return []

        rows = session.exec(
            select(RunResource)
            .where(
                RunResource.run_id == run_id,
                RunResource.task_execution_id.in_(execution_ids),
            )
            .order_by(RunResource.created_at.desc(), RunResource.id.desc())
        ).all()
        return list(rows)

    def _descendant_task_ids(
        self,
        session: Session,
        *,
        run_id: UUID,
        root_task_id: UUID,
        direct_only: bool,
    ) -> list[UUID]:
        task_ids: list[UUID] = []
        frontier = [root_task_id]
        while frontier:
            current = frontier.pop(0)
            children = list(
                session.exec(
                    select(RunGraphNode.task_id).where(
                        RunGraphNode.run_id == run_id,
                        RunGraphNode.parent_task_id == current,
                    )
                ).all()
            )
            task_ids.extend(children)
            if not direct_only:
                frontier.extend(children)
        return task_ids

    def list_by_execution(self, session: Session, task_execution_id: UUID) -> list[RunResource]:
        stmt = select(RunResource).where(RunResource.task_execution_id == task_execution_id)
        return list(session.exec(stmt).all())

    def latest_by_path(
        self,
        session: Session,
        *,
        task_execution_id: UUID,
        file_path: str,
    ) -> RunResource | None:
        stmt = (
            select(RunResource)
            .where(
                RunResource.task_execution_id == task_execution_id,
                RunResource.file_path == file_path,
            )
            .order_by(RunResource.created_at.desc(), RunResource.id.desc())
            .limit(1)
        )
        return session.exec(stmt).first()

    def find_by_hash(
        self,
        session: Session,
        *,
        task_execution_id: UUID,
        content_hash: str,
    ) -> RunResource | None:
        stmt = (
            select(RunResource)
            .where(
                RunResource.task_execution_id == task_execution_id,
                RunResource.content_hash == content_hash,
            )
            .limit(1)
        )
        return session.exec(stmt).first()

    def append(  # slopcop: ignore[max-function-params]
        self,
        session: Session,
        *,
        run_id: UUID,
        task_execution_id: UUID,
        kind: str,
        name: str,
        mime_type: str,
        file_path: str,
        size_bytes: int,
        error: str | None,
        content_hash: str | None,
        metadata: JsonObject | None = None,
        copied_from_resource_id: UUID | None = None,
    ) -> RunResource:
        row = RunResource(
            run_id=run_id,
            task_execution_id=task_execution_id,
            kind=kind,
            name=name,
            mime_type=mime_type,
            file_path=file_path,
            size_bytes=size_bytes,
            error=error,
            content_hash=content_hash,
            metadata_json=metadata or {},
            copied_from_resource_id=copied_from_resource_id,
        )
        session.add(row)
        session.flush()
        return row
