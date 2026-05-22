"""Unit tests for ``Benchmark.__init__`` identity kwargs.

Locks in the name/description/created_by asymmetry: name and description
collapse `None` to defaults via `or`; created_by preserves `None` as the
unset attribution sentinel.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from ergon_core.api import Benchmark
from ergon_core.api.benchmark import Task


class _NoopBenchmark(Benchmark):
    type_slug: ClassVar[str] = "test-noop"

    def build_instances(self) -> Mapping[str, Sequence[Task]]:
        return {}


def test_name_defaults_to_class_name_when_none() -> None:
    assert _NoopBenchmark(name=None).name == "_NoopBenchmark"


def test_name_round_trips_when_set() -> None:
    assert _NoopBenchmark(name="custom").name == "custom"


def test_created_by_defaults_to_none() -> None:
    assert _NoopBenchmark().created_by is None


def test_created_by_round_trips_when_set() -> None:
    assert _NoopBenchmark(created_by="alice").created_by == "alice"


def test_description_round_trips() -> None:
    assert _NoopBenchmark(description="bar").description == "bar"
    assert _NoopBenchmark(description=None).description == ""
