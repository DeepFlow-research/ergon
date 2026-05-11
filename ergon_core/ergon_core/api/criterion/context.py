"""Public runtime-facing criterion context."""

from uuid import UUID

from ergon_core.api.benchmark.task import Task
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel, ConfigDict, Field


class CriterionContext(BaseModel):
    """Task, worker output, and public criterion capabilities."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    task: Task
    worker_result: WorkerOutput
    sandbox_id: str | None = None
    metadata: JsonObject = Field(default_factory=dict)
