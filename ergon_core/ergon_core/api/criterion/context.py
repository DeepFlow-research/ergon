"""Public runtime-facing criterion context."""

from typing import Any
from uuid import UUID

from ergon_core.api.benchmark.task import Task
from ergon_core.api.worker.results import WorkerOutput
from pydantic import BaseModel, ConfigDict, Field


class CriterionContext(BaseModel):
    """Task, worker output, and run identity for a criterion evaluation."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    task: Task
    worker_result: WorkerOutput
    metadata: dict[str, Any] = Field(default_factory=dict)
