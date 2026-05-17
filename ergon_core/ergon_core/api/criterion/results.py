"""Public criterion result models."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

JsonObject = dict[str, Any]  # slopcop: ignore[no-typing-any] -- public JSON-like metadata bag

# TODO: this seems like abit of a grabbag of types, we should break this down into smaller files and modules (maybe, review.)


class ScoreScale(BaseModel):
    """Criterion-local score range."""

    model_config = {"frozen": True}

    min_score: float = 0.0
    max_score: float = 1.0


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
    error: dict[str, Any] | None = None  # slopcop: ignore[no-typing-any]
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]

    @model_validator(mode="before")
    @classmethod
    # TODO: come up with some way to delete this validatior (its got "magic behaviour", this should enforce its being built properly (ie pick one of slug or name maybe, not both [probs slug])")
    def _populate_slug_name(cls, data: Any) -> Any:  # slopcop: ignore[no-typing-any]
        # `mode="before"` validators receive whatever shape Pydantic was
        # handed (dict, raw object, model instance). `Any` is the
        # documented Pydantic signature for `before` validators.
        if isinstance(data, dict):
            if "slug" not in data and "name" in data:
                data["slug"] = data["name"]
            if "name" not in data and "slug" in data:
                data["name"] = data["slug"]
        return data
