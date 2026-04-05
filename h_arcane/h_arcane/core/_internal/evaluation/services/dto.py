"""Service DTOs for evaluation orchestration."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from h_arcane.core._internal.db.models import ResourceRecord


class DispatchEvaluatorsCommand(BaseModel):
    """Inputs required to prepare evaluator dispatch for a completed task."""

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    experiment_id: UUID


class PreparedSingleEvaluator(BaseModel):
    """Prepared inputs for invoking a single rubric evaluation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    evaluator_id: UUID
    rubric: Any
    task_input: str
    agent_reasoning: str
    agent_outputs: list[ResourceRecord]


class PreparedEvaluatorDispatch(BaseModel):
    """Prepared evaluator dispatch payloads for the runner."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: UUID
    evaluators_found: int
    invalid_evaluator_ids: list[UUID]
    valid_evaluators: list[PreparedSingleEvaluator]
