"""Resource repository."""

from uuid import UUID

from ergon_core.api.errors import ContainmentViolation
from ergon_core.core.application.resources.errors import RunResourceNotFoundError
from ergon_core.core.application.resources.models import RunResourceView
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.telemetry.models import RunResource
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.shared.json_types import JsonObject
from sqlmodel import Session, select


class RunResourceRepository:
    """Domain repository for append-only run resource rows."""

    def list_by_run(self, session: Session, run_id: UUID) -> list[RunResource]:
        stmt = select(RunResource).where(RunResource.run_id == run_id)
        return list(session.exec(stmt).all())

    def list_by_execution(self, session: Session, task_execution_id: UUID) -> list[RunResource]:
        stmt = select(RunResource).where(RunResource.task_execution_id == task_execution_id)
        return list(session.exec(stmt).all())

    def list_for_run(
        self,
        session: Session,
        *,
        run_id: UUID,
        task_id: UUID | None = None,
        task_execution_id: UUID | None = None,
        kind: str | None = None,
        name: str | None = None,
    ) -> list[RunResourceView]:
        stmt = select(RunResource).where(RunResource.run_id == run_id)
        if task_execution_id is not None:
            execution = session.get(RunTaskExecution, task_execution_id)
            if execution is None or execution.run_id != run_id:
                raise ContainmentViolation(
                    parent_task_id=task_id,
                    target_task_id=task_execution_id,
                )
            stmt = stmt.where(RunResource.task_execution_id == task_execution_id)
        if task_id is not None:
            node = session.get(RunGraphNode, (run_id, task_id))
            if node is None or node.run_id != run_id:
                return []
            execution_ids = session.exec(
                select(RunTaskExecution.id).where(
                    RunTaskExecution.run_id == run_id,
                    RunTaskExecution.task_id == task_id,
                )
            ).all()
            stmt = stmt.where(RunResource.task_execution_id.in_(execution_ids))
        if kind is not None:
            stmt = stmt.where(RunResource.kind == kind)
        if name is not None:
            stmt = stmt.where(RunResource.name == name)
        rows = session.exec(
            stmt.order_by(RunResource.created_at.desc(), RunResource.id.desc())
        ).all()
        return [RunResourceView.from_row(row) for row in rows]

    def get(self, session: Session, resource_id: UUID) -> RunResource:
        resource = session.get(RunResource, resource_id)
        if resource is None:
            raise RunResourceNotFoundError(resource_id)
        return resource

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
