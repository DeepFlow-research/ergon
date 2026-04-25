"""Core schemas for the evaluation engine."""

from uuid import UUID

from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion_runtime import CommandResult, SandboxResult
from ergon_core.api.json_types import JsonObject
from pydantic import BaseModel, ConfigDict, Field

# Re-exported for callers that still import from here.
__all__ = [
    "CommandResult",
    "CriterionContext",
    "CriterionSpec",
    "LLMJudgeResponse",
    "SandboxResult",
    "TaskEvaluationContext",
]


class LLMJudgeResponse(BaseModel):
    """Structured response from LLM judge evaluation."""

    reasoning: str = Field(
        description="Detailed reasoning explaining why the criterion is met or not met."
    )
    final_verdict: bool = Field(
        description="Binary classification: True if the criterion is met, False otherwise."
    )


class CriterionContext(BaseModel):
    """Context for evaluating a single criterion within the engine."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID
    task_input: str = ""  # slopcop: ignore[no-str-empty-default]
    agent_reasoning: str = ""  # slopcop: ignore[no-str-empty-default]
    agent_outputs: list[JsonObject] = Field(default_factory=list)
    stage_idx: int = 0
    stage_name: str = "default"
    criterion_idx: int = 0
    max_score: float = 1.0


class TaskEvaluationContext(BaseModel):
    """Context for evaluating an entire task/rubric."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID
    task_input: str = ""  # slopcop: ignore[no-str-empty-default]
    agent_reasoning: str = ""  # slopcop: ignore[no-str-empty-default]
    agent_outputs: list[JsonObject] = Field(default_factory=list)
    sandbox_id: str = ""  # slopcop: ignore[no-str-empty-default]


class CriterionSpec(BaseModel):
    """Declarative description of one criterion to execute."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    criterion: Criterion
    criterion_idx: int = 0
    max_score: float = 1.0
    stage_idx: int = 0
    stage_name: str = "default"
    aggregation_weight: float = 1.0
