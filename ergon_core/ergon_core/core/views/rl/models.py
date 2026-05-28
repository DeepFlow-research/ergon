"""Canonical RL read and projection models."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RlActorIdentity(BaseModel):
    actor_slug: str
    base_worker_slug: str | None = None
    parent_actor_slug: str | None = None
    task_id: UUID | None = None
    parent_task_id: UUID | None = None


class RlActorEvent(BaseModel):
    event_type: str
    event_timestamp: datetime
    worker_slug: str
    task_id: UUID | None = None
    worker_type: str | None = None
    model_target: str | None = None
    worker_snapshot: dict = Field(default_factory=dict)


class RlActorRecord(RlActorIdentity):
    is_available: bool = False
    available_since: datetime | None = None
    unavailable_since: datetime | None = None
    worker_snapshot: dict = Field(default_factory=dict)
    events: list[RlActorEvent] = Field(default_factory=list)


class RlActorTopologyNode(BaseModel):
    actor: RlActorIdentity
    children: list["RlActorTopologyNode"] = Field(default_factory=list)


class RlActorState(BaseModel):
    sample_id: UUID
    actors: list[RlActorRecord] = Field(default_factory=list)
    roots: list[RlActorTopologyNode] = Field(default_factory=list)


class RlTokenLogprob(BaseModel):
    token: str
    logprob: float
    top_logprobs: list[dict] = Field(default_factory=list)


class RlTokenMetadata(BaseModel):
    token_ids: list[int] | None = None
    tokens: list[str] | None = None
    logprobs: list[RlTokenLogprob] | None = None


class RlEpisodeStep(BaseModel):
    step_kind: Literal["observation", "action", "environment"]
    part_kind: str
    text: str
    sequence: int
    sample_id: UUID
    task_id: UUID
    task_attempt_id: UUID
    actor: RlActorIdentity | None = None
    token_metadata: RlTokenMetadata | None = None
    created_at: datetime | None = None


class RlObservationStep(RlEpisodeStep):
    step_kind: Literal["observation"] = "observation"


class RlActionStep(RlEpisodeStep):
    step_kind: Literal["action"] = "action"


class RlEnvironmentStep(RlEpisodeStep):
    step_kind: Literal["environment"] = "environment"


class RlTaskAttempt(BaseModel):
    task_attempt_id: UUID
    attempt_number: int
    worker_binding_key: str | None = None
    actor: RlActorIdentity | None = None
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    steps: list[RlObservationStep | RlActionStep | RlEnvironmentStep] = Field(default_factory=list)


class RlTaskEpisode(BaseModel):
    task_id: UUID
    parent_task_id: UUID | None = None
    task_slug: str
    level: int
    assigned_worker_slug: str | None = None
    actor: RlActorIdentity | None = None
    attempts: list[RlTaskAttempt] = Field(default_factory=list)
    children: list["RlTaskEpisode"] = Field(default_factory=list)


class RlEpisode(BaseModel):
    sample_id: UUID
    experiment_id: UUID | None = None
    environment_id: UUID | None = None
    sample_key: str | None = None
    normalized_reward: float | None = None
    root_tasks: list[RlTaskEpisode] = Field(default_factory=list)


class RlProjectedStep(BaseModel):
    text: str
    step_kind: Literal["observation", "action", "environment"]
    part_kind: str
    sequence: int
    sample_id: UUID
    task_id: UUID
    task_attempt_id: UUID
    attempt_number: int
    status: str
    task_slug: str
    actor: RlActorIdentity
    token_metadata: RlTokenMetadata | None = None
    created_at: datetime | None = None


class RlActorTrainingSpan(BaseModel):
    key: str
    group_by: Literal["actor_slug", "base_worker_slug"]
    records: list[RlProjectedStep] = Field(default_factory=list)


class RlTaskAttemptTrajectory(BaseModel):
    task_id: UUID
    task_slug: str
    task_attempt_id: UUID
    attempt_number: int
    status: str
    actor: RlActorIdentity | None = None
    records: list[RlProjectedStep] = Field(default_factory=list)


class RlJointEpisodeTimeline(BaseModel):
    sample_id: UUID
    records: list[RlProjectedStep] = Field(default_factory=list)
