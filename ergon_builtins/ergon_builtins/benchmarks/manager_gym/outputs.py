"""
Agent output data models for different agent types.
"""

import json
from pydantic import BaseModel, Field, field_validator


class ResourceDraft(BaseModel):
    """Model-authored content; native work publication assigns its identity."""

    name: str = Field(description="Human-readable resource name")
    description: str = Field(description="What this resource contains and how it is used")
    content: str | None = Field(default=None, description="The resource's inline deliverable")
    content_type: str = Field(default="text/plain", description="The resource's MIME type")


class ResourceOutput(BaseModel):
    @field_validator("resources", mode="before", check_fields=False)
    @classmethod
    def decode_resources(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value


class AITaskOutput(ResourceOutput):
    """
    Structured output representing the result of an AI task execution.

    It should have the reasoning be the reasoning as to what the resources be, and ALWAYS have at least one resource.
    """

    reasoning: str
    resources: list[ResourceDraft] = Field(
        description="Resources created by the AI agent. There MUST BE AT LEAST ONE RESOURCE."
    )
    confidence: float
    execution_notes: list[str]


class HumanWorkOutput(ResourceOutput):
    """Structured output format for human work simulation."""

    reasoning: str
    resources: list[ResourceDraft] = Field(
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
