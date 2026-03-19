"""Pydantic schemas for deterministic benchmark cases."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from h_arcane.core.task import Resource


class ScriptedToolCall(BaseModel):
    """One deterministic tool call executed by the scripted worker."""

    kind: Literal["tool"] = "tool"
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ScriptedJudgeResponse(BaseModel):
    """Deterministic LLM-judge response for rubric evaluation."""

    reasoning: str
    final_verdict: bool


class SkillResponseSequence(BaseModel):
    """Deterministic responses returned by selected sandbox skills."""

    skill_name: str
    responses: list[dict[str, Any]] = Field(default_factory=list)


class DeterministicCase(BaseModel):
    """Full benchmark case specification for the deterministic harness."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    benchmark_name: Literal["minif2f", "researchrubrics"]
    task_name: str
    task_description: str
    resources: list[Resource] = Field(default_factory=list)
    evaluator: Any
    stakeholder_answers: list[str] = Field(default_factory=list)
    scripted_steps: list[ScriptedToolCall] = Field(default_factory=list)
    scripted_skill_responses: list[SkillResponseSequence] = Field(default_factory=list)
    scripted_judge_responses: list[ScriptedJudgeResponse] = Field(default_factory=list)
    final_output_text: str
    expected_action_names: list[str]
    expected_output_names: list[str]
    expected_questions_asked: int
    expected_total_cost_usd: float = 0.0


class TranscriptEventRecord(BaseModel):
    """Normalized trace event for test assertions."""

    span_name: str
    event_name: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None


class TranscriptSpanRecord(BaseModel):
    """Normalized completed span for test assertions."""

    span_name: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    status_code: str
    status_message: str | None = None


class RunTranscript(BaseModel):
    """Structured transcript captured from deterministic tracing."""

    spans: list[TranscriptSpanRecord] = Field(default_factory=list)
    events: list[TranscriptEventRecord] = Field(default_factory=list)


class DeterministicRunResult(BaseModel):
    """Result returned by the deterministic harness."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    case: DeterministicCase
    run_id: UUID
    experiment_id: UUID
    task_id: UUID
    execution_id: UUID
    transcript: RunTranscript
