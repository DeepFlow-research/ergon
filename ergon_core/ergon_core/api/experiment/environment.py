"""Public sample-producing environment contract."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ergon_core.api.experiment.sample import Sample


class Environment(BaseModel):
    """Base class for user-defined sample sources."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    source_mode: Literal["materialized", "streaming"] = "streaming"
    source_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    def all_samples(self) -> Sequence[Sample]:
        if self.source_mode == "streaming":
            raise NotImplementedError("Streaming environments may not materialize all samples")
        return list(self.iter_samples())

    def iter_samples(self) -> Iterator[Sample]:
        # TODO(PR06): builtin environments implement this for MiniF2F,
        # SWE-bench Verified, ResearchRubrics, and GDPEval. User-defined
        # environments continue to override it directly.
        raise NotImplementedError

    def validate_authoring(self) -> None:
        if not self.name:
            raise ValueError("Environment name is required")
