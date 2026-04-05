"""Typed result objects returned by Inngest functions.

Each Inngest function has an output_type for structured returns.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class WorkflowStartResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    initial_ready_tasks: int = 0
    total_tasks: int = 0


class TaskExecuteResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    task_id: UUID
    execution_id: UUID | None = None
    success: bool = False
    skipped: bool = False
    skip_reason: str | None = None
    outputs_count: int = 0
    error: str | None = None


class TaskPropagateResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    task_id: UUID
    newly_ready_tasks: int = 0
    workflow_complete: bool = False
    workflow_failed: bool = False


class WorkflowCompleteResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    status: str = "completed"
    final_score: float | None = None
    normalized_score: float | None = None
    evaluators_count: int = 0


class WorkflowFailedResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    status: str = "failed"
    error: str | None = None


class SandboxReadyResult(BaseModel):
    model_config = {"frozen": True}

    sandbox_id: str
    output_dir: str | None = None


class WorkerExecuteResult(BaseModel):
    model_config = {"frozen": True}

    success: bool = False
    output_text: str | None = None
    error: str | None = None


class PersistOutputsResult(BaseModel):
    model_config = {"frozen": True}

    output_resource_ids: list[UUID] = Field(default_factory=list)
    outputs_count: int = 0


class EvaluatorsResult(BaseModel):
    model_config = {"frozen": True}

    task_id: UUID
    evaluators_found: int = 0
    evaluators_run: int = 0
    scores: list[float | None] = Field(default_factory=list)


class EvaluateTaskRunResult(BaseModel):
    model_config = {"frozen": True}

    score: float | None = None
    passed: bool | None = None
    evaluator_name: str = ""
    error: str | None = None


class BenchmarkRunStartResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID
    benchmark: str = ""


class RunCleanupResult(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    status: str = ""
    sandbox_terminated: bool = False
    sandbox_id: str | None = None
    error: str | None = None
