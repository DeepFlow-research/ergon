"""Pydantic types for the Rollout-as-a-Service API.

Used by RolloutService (server-side), the HTTP endpoints, and the
HTTP adapters (client-side). Framework-agnostic — no TRL/veRL imports.
"""

from uuid import UUID

from ergon_core.core.shared.rollout_status import RolloutStatus as BatchStatus
from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class TrainingRolloutRequest(BaseModel):
    """Trainer → Ergon: select and launch samples from a persisted experiment."""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    experiment_id: UUID
    k: int = Field(ge=1)
    sampler: str = "random"
    sampler_config: dict[str, object] = Field(default_factory=dict)
    candidate_pool_size: int | None = None


class RolloutBatchSummary(BaseModel):
    """Durable trainer batch membership exposed by sample id."""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    batch_id: UUID
    sample_ids: list[UUID]
    status: BatchStatus
    experiment_id: UUID | None = None
    sampler_invocation_id: UUID | None = None


class TrainerActorIdentity(BaseModel):
    """Trace identity for one trainer-facing projected actor record."""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    actor_slug: str
    base_worker_slug: str | None = None
    parent_actor_slug: str | None = None
    task_id: UUID | None = None
    parent_task_id: UUID | None = None


class TrainerTrainingRecord(BaseModel):
    """One projected parent-visible training record for adapter examples."""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    sample_id: UUID
    actor: TrainerActorIdentity
    prompt_ids: list[int] = Field(default_factory=list)
    completion_ids: list[int] = Field(default_factory=list)
    logprobs: list[float] = Field(default_factory=list)
    reward: float
    task_id: UUID | None = None
    task_attempt_id: UUID | None = None


class EpisodeFailure(BaseModel):
    """An episode that didn't complete successfully."""

    sample_id: UUID
    error: str


class PollResponse(BaseModel):
    """Ergon → Trainer: current batch status + projected records if complete."""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    batch_id: UUID
    status: BatchStatus
    completed: int = 0
    total: int = 0
    training_records: list[TrainerTrainingRecord] = Field(default_factory=list)
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
