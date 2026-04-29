"""Evaluation dispatch DTOs."""

from uuid import UUID

from ergon_core.api.criterion import Criterion
from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel, ConfigDict, Field


class PreparedSingleEvaluator(BaseModel):
    model_config = {"frozen": True}

    evaluator_id: UUID
    evaluator_binding_key: str
    evaluator_type: str
    task_input: str
    agent_reasoning: str | None = None
    agent_outputs: list[JsonObject] = Field(default_factory=list)


class PreparedEvaluatorDispatch(BaseModel):
    model_config = {"frozen": True}

    node_id: UUID
    task_id: UUID | None = None
    evaluators_found: int = 0
    invalid_evaluator_ids: list[UUID] = Field(default_factory=list)
    valid_evaluators: list[PreparedSingleEvaluator] = Field(default_factory=list)


class DispatchEvaluatorsCommand(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID
    node_id: UUID
    task_id: UUID | None = None
    execution_id: UUID

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
