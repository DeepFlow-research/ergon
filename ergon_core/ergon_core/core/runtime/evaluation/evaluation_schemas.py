"""Core schemas for the evaluation engine."""

from uuid import UUID

from ergon_core.api.criterion import Criterion
from ergon_core.api.json_types import JsonObject
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CriterionContext",
    "CriterionSpec",
    "TaskEvaluationContext",
]


class CriterionContext(BaseModel):
    """Context for evaluating a single criterion within the engine."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID
    task_input: str
    agent_reasoning: str | None
    agent_outputs: list[JsonObject] = Field(default_factory=list)
    stage_idx: int = 0
    stage_name: str = "default"
    criterion_idx: int = 0
    max_score: float = 1.0


class TaskEvaluationContext(BaseModel):
    """Context for evaluating an entire task/rubric."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID
    task_input: str
    agent_reasoning: str | None
    agent_outputs: list[JsonObject] = Field(default_factory=list)
    sandbox_id: str | None = None


class CriterionSpec(BaseModel):
    """Declarative description of one criterion to execute."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    criterion: Criterion
    criterion_idx: int = 0
    max_score: float = 1.0
    stage_idx: int = 0
    stage_name: str = "default"
    aggregation_weight: float = 1.0
