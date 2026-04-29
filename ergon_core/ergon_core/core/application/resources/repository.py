"""Resource repository."""

from uuid import UUID

from ergon_core.core.persistence.telemetry.models import RunResource
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
