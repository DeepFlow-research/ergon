"""Public sample selection contracts."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from ergon_core.api.experiment.sample import Sample


class SamplingContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    experiment_id: UUID | None = None
    candidate_pool_size: int | None = None


class Sampler(BaseModel, ABC):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str

    def config(self) -> dict[str, JsonValue]:
        return self.model_dump(mode="json")

    @abstractmethod
    async def select(
        self,
        *,
        samples: Sequence[Sample],
        k: int,
        context: SamplingContext,
    ) -> Sequence[Sample]:
        raise NotImplementedError


class RandomSampler(Sampler):
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
        del k, context
        shuffled = list(samples)
        random.Random(self.seed).shuffle(shuffled)
        return shuffled
