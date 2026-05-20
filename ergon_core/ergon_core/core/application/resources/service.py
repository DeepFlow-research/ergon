"""Application service for reading run resources."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TypeAlias
from uuid import UUID

from sqlmodel import Session

from ergon_core.api.errors import ContainmentViolation
from ergon_core.core.application.resources.models import RunResourceView
from ergon_core.core.application.resources.repository import RunResourceRepository
from ergon_core.core.persistence.shared.db import get_session

SessionFactory: TypeAlias = Callable[[], AbstractContextManager[Session]]


class RunResourceReadService:
    """Owns worker-facing read policy for run resources."""

    def __init__(
        self,
        *,
        repository: RunResourceRepository | None = None,
        session_factory: SessionFactory = get_session,
    ) -> None:
        self._resource_repo = repository or RunResourceRepository()
        self._session_factory = session_factory

    def list_for_run(
        self,
        *,
        run_id: UUID,
        task_id: UUID | None = None,
        task_execution_id: UUID | None = None,
        kind: str | None = None,
        name: str | None = None,
    ) -> tuple[RunResourceView, ...]:
        """List resources visible inside a run."""

        with self._session_factory() as session:
            rows = self._resource_repo.list_for_run(
                session,
                run_id=run_id,
                task_id=task_id,
                task_execution_id=task_execution_id,
                kind=kind,
                name=name,
            )
        return tuple(rows)

    def read_bytes(
        self,
        *,
        run_id: UUID,
        current_task_id: UUID,
        resource_id: UUID,
    ) -> bytes:
        """Read a resource blob after enforcing run containment."""

        with self._session_factory() as session:
            resource = self._resource_repo.get(session, resource_id)
            if resource.run_id != run_id:
                raise ContainmentViolation(
                    parent_task_id=current_task_id,
                    target_task_id=resource_id,
                )
            return Path(resource.file_path).read_bytes()
