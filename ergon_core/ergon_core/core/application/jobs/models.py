"""Pure application job request and result models."""

from typing import ClassVar, Literal
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract
from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel, Field, model_validator


class SandboxSetupRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/sandbox-setup"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    benchmark_type: str
    sandbox_slug: str | None = None
    input_resource_ids: list[UUID] = Field(default_factory=list)
    envs: dict[str, str] = Field(default_factory=dict)


class WorkerExecuteRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/worker-execute"

    run_id: UUID
    definition_id: UUID
    task_id: UUID | None
    execution_id: UUID
    sandbox_id: str
    task_slug: str
    task_description: str
    assigned_worker_slug: str
    worker_type: str
    model_target: str
    benchmark_type: str
    node_id: UUID | None = None

    @model_validator(mode="after")
    def _has_static_or_dynamic_identity(self) -> "WorkerExecuteRequest":
        if self.task_id is None and self.node_id is None:
            raise ValueError("WorkerExecuteRequest requires task_id or node_id")
        return self


class PersistOutputsRequest(InngestEventContract):
    model_config = {"extra": "allow"}
    name: ClassVar[str] = "task/persist-outputs"

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_id: str | None = None
    output_dir: str | None = None
    benchmark_type: str
    sandbox_slug: str | None = None


class TaskEvaluateRequest(InngestEventContract):
    """v2 wire shape for `task/evaluate`. The id-only payload — every
    other piece of state is reloaded from persistence by the receiver.

    Carried fields:
        run_id          identifies the run (for `RunRecord` lookups)
        task_id         identifies the task within the run
        execution_id    identifies the specific worker execution being
                        evaluated; also the join key to the persisted
                        WorkerOutput and stamped sandbox_id
        evaluator_index 0-based index into `task.evaluators`; legacy
                        binding-key fallback remains only until PR 11

    Sent by `execute_task._fan_out_evaluators` (one event per
    evaluator, via `asyncio.gather` over `ctx.step.invoke`). Received
    by `run_evaluate_task_run_job`, which reloads everything else
    through the run-tier read boundary.
    """

    model_config = {"frozen": True}
    name: ClassVar[str] = "task/evaluate"

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    evaluator_index: int


class WorkflowStartResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    initial_ready_tasks: int = 0
    total_tasks: int = 0


class TaskExecuteResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    task_id: UUID | None
    execution_id: UUID
    success: bool = False
    skipped: bool = False
    skip_reason: str | None = None
    outputs_count: int = 0
    error: str | None = None


class TaskPropagateResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    task_id: UUID | None
    newly_ready_tasks: int = 0
    workflow_complete: bool = False
    workflow_failed: bool = False


class WorkflowCompleteResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    status: Literal["completed"] = "completed"
    final_score: float | None = None
    normalized_score: float | None = None
    evaluators_count: int = 0


class WorkflowFailedResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    status: Literal["failed"] = "failed"
    error: str | None = None


class SandboxReadyResult(BaseModel):
    model_config = {"frozen": True}

    sandbox_id: str
    output_dir: str | None = None


class WorkerExecuteResult(BaseModel):
    model_config = {"frozen": True}

    success: bool = False
    final_assistant_message: str | None = None
    error: str | None = None
    error_json: JsonObject | None = None


class PersistOutputsResult(BaseModel):
    model_config = {"frozen": True}

    output_resource_ids: list[UUID] = Field(default_factory=list)
    outputs_count: int = 0


class EvaluatorsResult(BaseModel):
    model_config = {"frozen": True}

    task_id: UUID | None
    evaluators_found: int = 0
    evaluators_run: int = 0
    scores: list[float | None] = Field(default_factory=list)


class EvaluateTaskRunResult(BaseModel):
    model_config = {"frozen": True}

    score: float | None = None
    passed: bool | None = None
    evaluator_name: str = ""  # slopcop: ignore[no-str-empty-default]
    error: str | None = None


class RunCleanupResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    status: str | None = None
    sandbox_terminated: bool = False
    sandbox_id: str | None = None
    error: str | None = None


WorkerExecuteJobRequest = WorkerExecuteRequest
WorkerExecuteJobResult = WorkerExecuteResult

__all__ = [
    "EvaluateTaskRunResult",
    "TaskEvaluateRequest",
    "EvaluatorsResult",
    "PersistOutputsRequest",
    "PersistOutputsResult",
    "RunCleanupResult",
    "SandboxReadyResult",
    "SandboxSetupRequest",
    "TaskExecuteResult",
    "TaskPropagateResult",
    "WorkerExecuteRequest",
    "WorkerExecuteResult",
    "WorkerExecuteJobRequest",
    "WorkerExecuteJobResult",
    "WorkflowCompleteResult",
    "WorkflowFailedResult",
    "WorkflowStartResult",
]
