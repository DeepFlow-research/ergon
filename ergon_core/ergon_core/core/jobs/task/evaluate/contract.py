from typing import ClassVar
from uuid import UUID

from ergon_core.core.application.events.base import InngestEventContract
from pydantic import BaseModel, Field


class TaskEvaluateRequest(InngestEventContract):
    model_config = {"frozen": True}
    name: ClassVar[str] = "task/evaluate"

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    evaluator_index: int


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
    evaluator_name: str = ""  # slopcop: ignore[no-str-empty-default]
    error: str | None = None
