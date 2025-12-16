"""Schemas for evaluation results and structured outputs."""

from pydantic import BaseModel, Field


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
