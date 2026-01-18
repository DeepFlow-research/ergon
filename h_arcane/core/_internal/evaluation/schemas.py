"""Core schemas for evaluation - data containers and response types."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from h_arcane.core._internal.db.models import ResourceRecord


class SandboxResult(BaseModel):
    """Result from sandbox code execution."""

    stdout: list[str]
    stderr: list[str]


class LLMJudgeResponse(BaseModel):
    """Structured response from LLM judge evaluation.

    Uses binary classification: criterion is either met (True) or not met (False).
    """

    reasoning: str = Field(
        description="Detailed reasoning explaining why the criterion is met or not met. "
        "Should cite specific evidence from the task input, agent reasoning, and outputs."
    )
    final_verdict: bool = Field(
        description="Binary classification: True if the criterion is met, False otherwise. "
        "This is a pass/fail decision based on whether the output satisfies the criterion."
    )


class EvaluationData(BaseModel):
    """Pure data for evaluation - no infrastructure methods."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[ResourceRecord]
    stage_idx: int
    stage_name: str
    rule_idx: int
    max_score: float


class TaskEvaluationContext(BaseModel):
    """Context for evaluating an entire task (all criteria).

    Bundles all data needed to evaluate task outputs against a rubric.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[ResourceRecord]
    rubric: Any  # AnyRubric at runtime - discriminated union of rubric types
