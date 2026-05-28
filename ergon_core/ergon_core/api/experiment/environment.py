"""Public sample-producing environment contract."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, JsonValue, PrivateAttr

from ergon_core.api.experiment.sample import Sample

RowT = TypeVar("RowT")


class Environment(BaseModel):
    """Base class for user-defined sample sources."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    source_mode: Literal["materialized", "streaming"] = "streaming"
    source_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    _stream_cursor: Iterator[Sample] | None = PrivateAttr(default=None)

    @classmethod
    def from_dataset(
        cls,
        *,
        name: str,
        dataset: Iterable[RowT],
        make_sample: Callable[[RowT], Sample],
        source_mode: Literal["materialized", "streaming"] = "streaming",
        source_metadata: Mapping[str, JsonValue] | None = None,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> "Environment":
        return _RowEnvironment(
            name=name,
            rows=dataset,
            make_sample=make_sample,
            source_mode=source_mode,
            source_metadata=dict(source_metadata or {}),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_records(
        cls,
        *,
        name: str,
        records: Iterable[RowT],
        make_sample: Callable[[RowT], Sample],
        source_mode: Literal["materialized", "streaming"] = "materialized",
        source_metadata: Mapping[str, JsonValue] | None = None,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> "Environment":
        return cls.from_dataset(
            name=name,
            dataset=records,
            make_sample=make_sample,
            source_mode=source_mode,
            source_metadata=source_metadata,
            metadata=metadata,
        )

    def all_samples(self) -> Sequence[Sample]:
        if self.source_mode == "streaming":
            raise NotImplementedError("Streaming environments may not materialize all samples")
        return list(self.iter_samples())

    def iter_samples(self) -> Iterator[Sample]:
        # TODO(PR06): builtin environments implement this for MiniF2F,
        # SWE-bench Verified, ResearchRubrics, and GDPEval. User-defined
        # environments continue to override it directly.
        raise NotImplementedError

    def iter_candidate_samples(self) -> Iterator[Sample]:
        """Return samples for candidate-pool refill without replaying streams."""
        if self.source_mode == "streaming":
            if self._stream_cursor is None:
                self._stream_cursor = self.iter_samples()
            return self._stream_cursor
        return iter(self.all_samples())

    def reset_stream_cursor(self) -> None:
        self._stream_cursor = None

    def validate_authoring(self) -> None:
        if not self.name:
            raise ValueError("Environment name is required")


class _RowEnvironment(Environment):
    """Adapter for row-backed user environments."""

    _make_sample: Callable[[Any], Sample] = PrivateAttr()
    _rows: Iterable[Any] | None = PrivateAttr(default=None)
    _samples: Sequence[Sample] | None = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        rows: Iterable[Any],
        make_sample: Callable[[Any], Sample],
        **data: Any,
    ) -> None:
        super().__init__(**data)
        self._make_sample = make_sample
        if self.source_mode == "materialized":
            self._samples = [make_sample(row) for row in rows]
            self._rows = None
        else:
            self._samples = None
            self._rows = iter(rows)

    def iter_samples(self) -> Iterator[Sample]:
        if self.source_mode == "materialized":
            yield from self._samples or []
            return

        if self._rows is None:
            return
        for row in self._rows:
            yield self._make_sample(row)
