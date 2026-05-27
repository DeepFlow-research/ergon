"""Public experiment authoring object."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, PrivateAttr

from ergon_core.api.experiment.environment import Environment
from ergon_core.api.experiment.sampling import RandomSampler, Sampler


@runtime_checkable
class ExperimentSubmissionPort(Protocol):
    async def submit(
        self,
        *,
        experiment: "Experiment",
        k: int,
        sampler: Sampler,
        candidate_pool_size: int | None,
        policy_version: int | None,
    ) -> "ExperimentSubmitResult": ...


class ExperimentRef(BaseModel):
    experiment_id: UUID
    name: str
    environment_ids: Mapping[str, UUID] = Field(default_factory=dict)
    created_at: datetime | None = None
    dashboard_url: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ExperimentSubmitResult(BaseModel):
    experiment_id: UUID
    sampler_invocation_id: UUID | None = None
    batch_id: UUID | None = None
    requested_k: int
    candidate_pool_size: int
    selected_count: int
    sample_ids: Sequence[UUID]
    dashboard_url: str | None = None


class Experiment(BaseModel):
    """User-facing grouping and submission object for sample environments."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    environments: Sequence[Environment]
    description: str | None = None
    created_by: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    _persisted_ref: ExperimentRef | None = PrivateAttr(default=None)

    def environment_names(self) -> Sequence[str]:
        return [environment.name for environment in self.environments]

    def environment_by_name(self, name: str) -> Environment:
        for environment in self.environments:
            if environment.name == name:
                return environment
        raise KeyError(name)

    def validate_authoring(self) -> None:
        if not self.name:
            raise ValueError("Experiment name is required")
        if not self.environments:
            raise ValueError("Experiment requires at least one environment")
        names = self.environment_names()
        if len(names) != len(set(names)):
            raise ValueError("Environment names must be unique")
        for environment in self.environments:
            environment.validate_authoring()

    def persisted_ref(self) -> ExperimentRef | None:
        return self._persisted_ref

    def mark_persisted(self, ref: ExperimentRef) -> None:
        self._persisted_ref = ref

    async def submit(
        self,
        *,
        service: ExperimentSubmissionPort,
        k: int,
        sampler: Sampler | None = None,
        candidate_pool_size: int | None = None,
        policy_version: int | None = None,
    ) -> ExperimentSubmitResult:
        self.validate_authoring()
        return await service.submit(
            experiment=self,
            k=k,
            sampler=sampler or RandomSampler(),
            candidate_pool_size=candidate_pool_size,
            policy_version=policy_version,
        )
