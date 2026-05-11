"""Public criterion result models."""

from typing import Literal

from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel, Field, model_validator


class EvidenceMessage(BaseModel):
    """One prompt-like message used while producing criterion evidence."""

    model_config = {"frozen": True}

    role: Literal["system", "user", "assistant", "tool"]
    content: str


class CriterionEvidence(BaseModel):
    """Structured evidence space for a criterion run."""

    model_config = {"frozen": True}

    prompt_messages: list[EvidenceMessage] = Field(default_factory=list)
    evidence_resource_ids: list[str] = Field(default_factory=list)
    evidence_action_ids: list[str] = Field(default_factory=list)
    output: JsonObject | None = None
    model: str | None = None
    details: JsonObject = Field(default_factory=dict)


class CriterionOutcome(BaseModel):
    """Result of a single Criterion.evaluate() invocation."""

    model_config = {"frozen": True}

    slug: str
    name: str
    score: float
    passed: bool
    weight: float = 1.0
    max_score: float = 1.0
    feedback: str | None = None
    model_reasoning: str | None = None
    skipped_reason: str | None = None
    evaluation_input: str | None = None
    evaluated_action_ids: list[str] = Field(default_factory=list)
    evaluated_resource_ids: list[str] = Field(default_factory=list)
    observation: CriterionEvidence | None = None
    error: JsonObject | None = None
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _populate_slug_name(cls, data):
        if isinstance(data, dict):
            if "slug" not in data and "name" in data:
                data["slug"] = data["name"]
            if "name" not in data and "slug" in data:
                data["name"] = data["slug"]
        return data
