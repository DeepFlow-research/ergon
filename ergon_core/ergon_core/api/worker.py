"""Public worker ABC."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from typing import Any, ClassVar, Self
from uuid import UUID

from ergon_core.api.dependencies import check_packages
from ergon_core.api.errors import DependencyError
from ergon_core.api.generation import GenerationTurn
from ergon_core.api.results import WorkerOutput
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.repositories import GenerationTurnRepository
from sqlmodel import Session


class Worker(ABC):
    """Base class for all workers.

    Subclasses must set ``type_slug`` and implement ``execute`` as an
    async generator that yields ``GenerationTurn`` objects.
    """

    type_slug: ClassVar[str]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""

    def __init__(
        self,
        *,
        name: str,
        model: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        self.name = name
        self.model = model
        self.metadata: dict[str, Any] = dict(metadata or {})  # slopcop: ignore[no-typing-any]
        self._turn_repo = GenerationTurnRepository()

    @abstractmethod
    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        """Run the worker's task behavior, yielding turns as they complete.

        Each yielded GenerationTurn is persisted to PG immediately by the
        runtime. Workers that can detect turn boundaries mid-execution
        yield incrementally. Workers that can't yield all turns at the end.
        """
        ...
        yield  # type: ignore[misc]

    @classmethod
    def from_buffer(
        cls,
        execution_id: UUID,
        session: Session,
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Self | None:
        """Construct a worker pre-seeded with context event history.

        Returns a new worker instance whose ``execute()`` will continue
        from where the previous execution left off, or ``None`` if this
        worker type doesn't support resumption.
        """
        return None

    def get_output(self, context: WorkerContext) -> WorkerOutput:
        """Build output from persisted turns. Override for custom output.

        Called by the runtime after the async generator is fully consumed.
        Default reads turns from PG via ``self._turn_repo`` and returns the
        last turn's response text. Workers that need structured output,
        summaries, or custom logic override this.
        """
        with get_session() as session:
            turns = self._turn_repo.get_for_execution(session, context.execution_id)
        last_turn = turns[-1] if turns else None
        return WorkerOutput(
            output=last_turn.response_text if last_turn else "",
            success=True,
        )

    def validate(self) -> None:
        """Check that runtime dependencies are available."""
        errors = check_packages(
            self.required_packages,
            f"Worker '{self.type_slug}'",
        )
        if errors:
            parts = [*errors]
            if self.install_hint:
                parts.append(f"Install with: {self.install_hint}")
            raise DependencyError("\n".join(parts))
