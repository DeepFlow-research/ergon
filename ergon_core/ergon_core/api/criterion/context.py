"""Public runtime-facing criterion context."""

from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID

from ergon_core.core.application.evaluation.protocols import CriterionRuntime
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SkipValidation

if TYPE_CHECKING:
    from ergon_core.api.benchmark.task import Task
    from ergon_core.api.worker.results import WorkerOutput

    TaskField = Task
    WorkerOutputField = WorkerOutput
else:
    TaskField = Any
    WorkerOutputField = Any


class CriterionContext(BaseModel):
    """Task, worker output, and public criterion capabilities."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    task: TaskField
    worker_result: WorkerOutputField
    sandbox_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
    _runtime: Annotated[CriterionRuntime | None, SkipValidation] = PrivateAttr(default=None)

    def __init__(self, **data: Any) -> None:  # slopcop: ignore[no-typing-any]
        runtime = data.pop("runtime", None)
        super().__init__(**data)
        if runtime is not None:
            object.__setattr__(self, "_runtime", runtime)

    def model_post_init(self, context: Any, /) -> None:  # slopcop: ignore[no-typing-any]
        if isinstance(context, dict) and "runtime" in context:
            object.__setattr__(self, "_runtime", context["runtime"])

    @classmethod
    def with_runtime(
        cls,
        *,
        runtime: CriterionRuntime | None,
        **data: Any,  # slopcop: ignore[no-typing-any]
    ) -> "CriterionContext":
        """Construct a context with runtime capabilities hidden from public fields."""
        instance = cls(**data)
        object.__setattr__(instance, "_runtime", runtime)
        return instance

    @property
    def has_runtime(self) -> bool:
        return self._runtime is not None

    @property
    def runtime(self) -> CriterionRuntime | None:
        """Private runtime capabilities exposed as a property, not a model field."""
        return self._runtime

    def _require_runtime(self) -> CriterionRuntime:
        if self._runtime is None:
            raise RuntimeError("CriterionRuntime not injected")
        return self._runtime

    async def ensure_sandbox(self) -> None:
        await self._require_runtime().ensure_sandbox()

    async def upload_files(self, files: list[dict]) -> None:
        await self._require_runtime().upload_files(files)

    async def write_file(self, path: str, content: bytes) -> None:
        await self._require_runtime().write_file(path, content)

    async def run_command(self, command: str, timeout: int = 30):
        return await self._require_runtime().run_command(command, timeout)

    async def execute_code(self, code: str):
        """Execute code through the internal criterion runtime."""
        return await self._require_runtime().execute_code(code)

    async def cleanup(self) -> None:
        await self._require_runtime().cleanup()

    async def read_resource(self, name: str) -> bytes:
        return await self._require_runtime().read_resource(name)

    async def read_resource_by_id(self, resource_id: UUID) -> bytes:
        return await self._require_runtime().read_resource_by_id(resource_id)

    async def list_resources(self, task_execution_id: UUID | None = None):
        return await self._require_runtime().list_resources(task_execution_id)

    async def get_all_files_for_task(self) -> dict[str, bytes]:
        return await self._require_runtime().get_all_files_for_task()

    async def list_files(self, path: str = "."):
        """List files through the internal criterion runtime."""
        return await self.run_command(f"find {path} -maxdepth 1 -type f", timeout=30)

    async def read_file(self, path: str) -> str:
        """Read a file through the internal criterion runtime."""
        return (await self.read_resource(path)).decode("utf-8")
