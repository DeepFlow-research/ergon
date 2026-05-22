"""Public criterion evidence models."""

from typing import Any, Literal

from pydantic import BaseModel, Field

JsonObject = dict[str, Any]


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
