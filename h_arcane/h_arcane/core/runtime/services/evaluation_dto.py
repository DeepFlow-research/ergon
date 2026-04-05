"""Evaluation dispatch DTOs."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PreparedSingleEvaluator(BaseModel):
    model_config = {"frozen": True}

    evaluator_id: UUID
    evaluator_binding_key: str
    evaluator_type: str
    task_input: str = ""
    agent_reasoning: str = ""
    agent_outputs: list[dict[str, Any]] = Field(default_factory=list)


class PreparedEvaluatorDispatch(BaseModel):
    model_config = {"frozen": True}

    task_id: UUID
    evaluators_found: int = 0
    invalid_evaluator_ids: list[UUID] = Field(default_factory=list)
    valid_evaluators: list[PreparedSingleEvaluator] = Field(default_factory=list)


class DispatchEvaluatorsCommand(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    definition_id: UUID
    task_id: UUID
    execution_id: UUID
