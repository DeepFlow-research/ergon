"""Core schemas for the evaluation engine."""

from typing import Any
from uuid import UUID

from h_arcane.api.criterion import Criterion
from pydantic import BaseModel, ConfigDict, Field


class SandboxResult(BaseModel):
    """Result from sandbox code execution."""

    stdout: list[str] = Field(default_factory=list)
    stderr: list[str] = Field(default_factory=list)


class CommandResult(BaseModel):
    """Result from command execution in a sandbox."""

    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None


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
    task_input: str = ""
    agent_reasoning: str = ""
    agent_outputs: list[dict[str, Any]] = Field(default_factory=list)
    stage_idx: int = 0
    stage_name: str = "default"
    criterion_idx: int = 0
    max_score: float = 1.0


class TaskEvaluationContext(BaseModel):
    """Context for evaluating an entire task/rubric."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID
    task_input: str = ""
    agent_reasoning: str = ""
    agent_outputs: list[dict[str, Any]] = Field(default_factory=list)


class CriterionSpec(BaseModel):
    """Declarative description of one criterion to execute."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    criterion: Criterion
    criterion_idx: int = 0
    max_score: float = 1.0
    stage_idx: int = 0
    stage_name: str = "default"
    aggregation_weight: float = 1.0
