from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WorkflowCommandContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_task_key: UUID
    benchmark_type: str


class WorkflowCommandOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    stdout: str
    stderr: str | None = None
    exit_code: int = 0
