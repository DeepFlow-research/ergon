"""Public worker ABC."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar

from h_arcane.api.results import WorkerResult
from h_arcane.api.task_types import BenchmarkTask
from h_arcane.api.worker_context import WorkerContext


class Worker(ABC):
    """Base class for all workers.

    Subclasses must set ``type_slug`` and implement ``execute``.
    """

    type_slug: ClassVar[str]

    def __init__(
        self,
        *,
        name: str,
        model: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.metadata: dict[str, Any] = dict(metadata or {})

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
        """Cheap validation of worker constructor state."""
