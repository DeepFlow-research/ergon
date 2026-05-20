from typing import ClassVar
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract
from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel


class WorkerExecuteRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/worker-execute"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str
    task_slug: str
    task_description: str
    assigned_worker_slug: str
    worker_type: str
    model_target: str | None = None
    benchmark_type: str


class WorkerExecuteResult(BaseModel):
    model_config = {"frozen": True}

    success: bool = False
    final_assistant_message: str | None = None
    error: str | None = None
    error_json: JsonObject | None = None


WorkerExecuteJobRequest = WorkerExecuteRequest
WorkerExecuteJobResult = WorkerExecuteResult
