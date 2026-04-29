"""Public worker ABC."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from typing import Any, ClassVar, Self, cast
from uuid import UUID

from ergon_core.api.benchmark.task import Task
from ergon_core.api.errors import DependencyError
from ergon_core.api.worker.context import WorkerContext
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.domain.generation.context_parts import ContextPartChunk
from ergon_core.core.infrastructure.dependencies import check_packages

WorkerStreamItem = ContextPartChunk | WorkerOutput


class Worker(ABC):
    """Base class for all workers."""

    type_slug: ClassVar[str]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""

    def __init__(
        self,
        *,
        name: str,
        model: str | None,
        task_id: UUID,
        sandbox_id: str,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        self.name = name
        self.model = model
        self.task_id = task_id
        self.sandbox_id = sandbox_id
        self.metadata: dict[str, Any] = dict(metadata or {})  # slopcop: ignore[no-typing-any]

    @abstractmethod
    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        """Run the worker, yielding context chunks and a terminal WorkerOutput."""
        raise NotImplementedError
        yield cast(WorkerStreamItem, None)

    @classmethod
    def from_buffer(
        cls,
        execution_id: UUID,
        session: Any,  # slopcop: ignore[no-typing-any] -- runtime owns concrete session type
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Self | None:
        """Construct a worker pre-seeded with context event history."""
        return None

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
