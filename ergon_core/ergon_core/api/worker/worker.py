"""Public worker ABC."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from typing import Any, ClassVar, Self, cast
from uuid import UUID

from ergon_core.api._serialization import (
    TaskDefinitionJson as ComponentDefinitionJson,
    import_component,
)
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
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        self.name = name
        self.model = model
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

    @classmethod
    def from_buffer(
        cls,
        execution_id: UUID,
        session: Any,  # slopcop: ignore[no-typing-any] -- runtime owns concrete session type
        **kwargs: Any,  # slopcop: ignore[no-typing-any]
    ) -> Self | None:
        """Construct a worker pre-seeded with context event history."""
        return None

    @classmethod
    def from_definition(cls, worker_json: ComponentDefinitionJson) -> "Worker":
        """Reconstruct a Worker subclass from `_type`-discriminated JSON.

        Becomes fully functional in PR 5, which converts ``Worker`` from
        a plain ABC into a Pydantic ``BaseModel``. Until then the
        signature is locked here so callers can be wired ahead of time,
        but invocation requires ``model_validate`` on the resolved
        subclass.
        """

        worker_type = worker_json.get("_type")
        if not isinstance(worker_type, str):
            raise ValueError(
                f"Worker snapshot is missing the required `_type` "
                f"discriminator (got {type(worker_type).__name__}). Every "
                f"persisted worker must carry `_type`."
            )
        WorkerCls = import_component(worker_type)
        # TODO(PR 5): once Worker is a Pydantic BaseModel, every
        # subclass has `model_validate` and the AttributeError branch
        # is unreachable — remove the try/except and the
        # NotImplementedError.
        try:
            return cast("Worker", WorkerCls.model_validate(worker_json))
        except AttributeError as exc:
            raise NotImplementedError(
                f"Worker.from_definition requires PR 5's Pydantic Worker "
                f"conversion; {WorkerCls.__name__} is still a plain ABC."
            ) from exc

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
