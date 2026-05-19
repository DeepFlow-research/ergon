"""Public criterion outcome model."""

from typing import Any

from pydantic import BaseModel, Field

from ergon_core.api.criterion.evidence import CriterionEvidence


class CriterionOutcome(BaseModel):
    """Result of a single Criterion.evaluate() invocation."""

    model_config = {"frozen": True}

    slug: str
    name: str | None = None
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
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
