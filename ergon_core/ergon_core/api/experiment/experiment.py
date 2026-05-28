"""Public experiment authoring object."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, PrivateAttr

from ergon_core.api.experiment.environment import Environment
from ergon_core.core.application.experiments.results import (
    ExperimentSubmitResult,
    PersistedExperiment,
)
from ergon_core.api.experiment.sampling import RandomSampler, Sampler
from ergon_core.core.application.experiments.persistence import persist_public_experiment
from ergon_core.core.application.experiments.submission import submit_experiment


class Experiment(BaseModel):
    """User-facing grouping and submission object for sample environments."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    environments: Sequence[Environment]
    description: str | None = None
    created_by: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    _persisted_experiment: PersistedExperiment | None = PrivateAttr(default=None)

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

    def persisted_experiment(self) -> PersistedExperiment | None:
        return self._persisted_experiment

    def mark_persisted(self, persisted: PersistedExperiment) -> None:
        self._persisted_experiment = persisted

    async def persist(
        self,
        *,
        session: Any | None = None,
    ) -> PersistedExperiment:
        self.validate_authoring()
        return await persist_public_experiment(self, session=session)

    async def submit(
        self,
        *,
        k: int,
        sampler: Sampler | None = None,
        candidate_pool_size: int | None = None,
        policy_version: int | None = None,
        session: Any | None = None,
        event_bus: Any | None = None,
    ) -> ExperimentSubmitResult:
        self.validate_authoring()
        return await submit_experiment(
            experiment=self,
            k=k,
            sampler=sampler or RandomSampler(),
            candidate_pool_size=candidate_pool_size,
            policy_version=policy_version,
            session=session,
            event_bus=event_bus,
        )
