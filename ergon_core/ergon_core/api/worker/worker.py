"""Public worker ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from typing import TYPE_CHECKING, Any, ClassVar, Self
from uuid import UUID

from pydantic import BaseModel, Field

from ergon_core.api.errors import DependencyError
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.domain.definitions import inflate_definition, serialize_definition
from ergon_core.core.domain.generation.context_parts import ContextPartChunk
from ergon_core.core.infrastructure.dependencies import check_packages

if TYPE_CHECKING:
    from ergon_core.api.benchmark.task import Task
    from ergon_core.api.sandbox import Sandbox
    from ergon_core.api.worker.context import WorkerContext

WorkerStreamItem = ContextPartChunk | WorkerOutput


class Worker(BaseModel, ABC):
    """Base class for all workers."""

    model_config = {"arbitrary_types_allowed": True, "extra": "allow", "frozen": False}

    type_slug: ClassVar[str]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""
    requires_sandbox: ClassVar[type[Sandbox] | None] = None

    name: str
    model: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]

    def __init__(
        self,
        *,
        name: str,
        model: str | None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
        **data: Any,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(name=name, model=model, metadata=dict(metadata or {}), **data)

    @classmethod
    def from_definition(
        cls, worker_json: dict[str, Any]
    ) -> "Worker":  # slopcop: ignore[no-typing-any]
        """Reconstruct a concrete worker from persisted definition JSON."""
        return inflate_definition(worker_json)

    def to_definition(self) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        """Serialize this worker for persisted experiment definitions."""
        return serialize_definition(self)

    @abstractmethod
    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
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
