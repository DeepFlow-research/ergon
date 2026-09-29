# ruff: noqa: E501 -- upstream's output docstrings are model-facing schema text, kept word for word.
"""Structured outputs of the work roles.

These are upstream MAG's ``schemas/workflow_agents/outputs.py`` models, and the
model sees them as its output schema, so their docstrings and descriptions are
kept word for word. One change: resources are drafts without an id, because the
worker assigns each resource a deterministic id. "At least one resource" is
stated to the model but not enforced here; the worker handles an empty list the
way upstream does for each role.
"""

from typing import Annotated

from pydantic import BaseModel, Field

from ergon_builtins.benchmarks.manager_gym.parsing import JsonDecoded


class ResourceDraft(BaseModel):
    """Model-authored content; native work publication assigns its identity."""

    name: str = Field(description="Human-readable resource name")
    description: str = Field(description="What this resource contains and how it is used")
    content: str | None = Field(default=None, description="The resource's inline deliverable")
    content_type: str = Field(default="text/plain", description="The resource's MIME type")


class AITaskOutput(BaseModel):
    """
    Structured output representing the result of an AI task execution.

    It should have the reasoning be the reasoning as to what the resources be, and ALWAYS have at least one resource.
    """

    reasoning: str
    resources: Annotated[list[ResourceDraft], JsonDecoded] = Field(
        description="Resources created by the AI agent. There MUST BE AT LEAST ONE RESOURCE."
    )
    confidence: float
    execution_notes: list[str]


class HumanWorkOutput(BaseModel):
    """Structured output format for human work simulation."""

    reasoning: str
    resources: Annotated[list[ResourceDraft], JsonDecoded] = Field(
        description="Resources created by the human agent. There MUST BE AT LEAST ONE RESOURCE."
    )
    work_process: str
    challenges_encountered: list[str]
    quality_notes: str
    confidence_level: str


class HumanTimeEstimation(BaseModel):
    """Structured output format for human time estimation."""

    reasoning: str
    estimated_hours: float
