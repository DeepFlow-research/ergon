"""Public sample selection contracts."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from ergon_core.api.experiment.sample import Sample


@runtime_checkable
class SamplingHistory(Protocol):
    def completed_sample_keys(
        self,
        *,
        experiment_id: UUID,
        environment_name: str | None = None,
    ) -> set[str]: ...


class SamplingContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    experiment_id: UUID | None = None
    candidate_pool_size: int | None = None
    history: SamplingHistory | None = None


@runtime_checkable
class Sampler(Protocol):
    name: str

    def config(self) -> dict[str, JsonValue]: ...

    async def select(
        self,
        *,
        samples: Sequence[Sample],
        k: int,
        context: SamplingContext,
    ) -> Sequence[Sample]: ...


class RandomSampler(BaseModel):
    name: str = "random"
    seed: int | None = None

    def config(self) -> dict[str, JsonValue]:
        return {"seed": self.seed}

    async def select(
        self,
        *,
        samples: Sequence[Sample],
        k: int,
        context: SamplingContext,
    ) -> Sequence[Sample]:
        shuffled = list(samples)
        random.Random(self.seed).shuffle(shuffled)
        return shuffled
