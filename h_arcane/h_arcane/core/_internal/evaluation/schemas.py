"""Core schemas for evaluation - data containers and response types."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from h_arcane.core._internal.db.models import ResourceRecord


class SandboxResult(BaseModel):
    """Result from sandbox code execution."""

    stdout: list[str]
    stderr: list[str]


class CommandResult(BaseModel):
    """Result from command execution in a sandbox."""

    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None


class LLMJudgeResponse(BaseModel):
    """Structured response from LLM judge evaluation."""

    reasoning: str = Field(
        description="Detailed reasoning explaining why the criterion is met or not met. "
        "Should cite specific evidence from the task input, agent reasoning, and outputs."
    )
    final_verdict: bool = Field(
        description="Binary classification: True if the criterion is met, False otherwise. "
        "This is a pass/fail decision based on whether the output satisfies the criterion."
    )


class CriterionContext(BaseModel):
    """Context for evaluating a single criterion."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[ResourceRecord]
    stage_idx: int
    stage_name: str
    criterion_idx: int
    max_score: float


class TaskEvaluationContext(BaseModel):
    """Context for evaluating an entire task/rubric."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[ResourceRecord]


class CriterionSpec(BaseModel):
    """Declarative description of one criterion to execute."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    criterion: Any
    criterion_idx: int
    max_score: float
    stage_idx: int = 0
    stage_name: str = "default"
    aggregation_weight: float = 1.0
