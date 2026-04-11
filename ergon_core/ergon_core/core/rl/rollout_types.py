"""Pydantic types for the Rollout-as-a-Service API.

Used by RolloutService (server-side), the HTTP endpoints, and the
HTTP adapters (client-side). Framework-agnostic — no TRL/veRL imports.
"""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class BatchStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubmitRequest(BaseModel):
    """Trainer → Ergon: start a batch of episodes."""

    definition_id: UUID
    num_episodes: int = Field(ge=1)
    policy_version: int | None = None
    model_target_override: str | None = None


class SubmitResponse(BaseModel):
    """Ergon → Trainer: batch accepted."""

    batch_id: UUID
    run_ids: list[UUID]
    status: BatchStatus = BatchStatus.PENDING


class Trajectory(BaseModel):
    """One agent's extracted trajectory from a completed episode.

    Maps 1:1 to AgentTrajectory from extraction.py, plus metadata.
    """

    run_id: UUID
    agent_id: str
    prompt_ids: list[int]
    completion_ids: list[int]
    logprobs: list[float]
    env_mask: list[int]
    reward: float
    num_turns: int


class EpisodeFailure(BaseModel):
    """An episode that didn't complete successfully."""

    run_id: UUID
    error: str


class PollResponse(BaseModel):
    """Ergon → Trainer: current batch status + trajectories if complete."""

    batch_id: UUID
    status: BatchStatus
    completed: int = 0
    total: int = 0
    trajectories: list[Trajectory] = Field(default_factory=list)
    failures: list[EpisodeFailure] = Field(default_factory=list)


class WeightSyncRequest(BaseModel):
    """Trainer → Ergon: restart vLLM with updated checkpoint.

    For full-weight RFT: Ergon kills the vLLM process and restarts it
    with --model pointing to checkpoint_path. Blocks until healthy.
    """

    checkpoint_path: str
    model_name: str


class WeightSyncResponse(BaseModel):
    """Ergon → Trainer: sync result."""

    success: bool
    vllm_model_loaded: str
