"""Public worker ABC."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar

from ergon_core.api.dependencies import check_packages
from ergon_core.api.errors import DependencyError
from ergon_core.api.results import WorkerResult
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker_context import WorkerContext


class Worker(ABC):
    """Base class for all workers.

    Subclasses must set ``type_slug`` and implement ``execute``.
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

    @abstractmethod
    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> WorkerResult:
        """Perform the worker's task behavior for one task invocation."""
        ...

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
