"""Core experiment composition root."""

from collections.abc import Mapping, Sequence
from typing import Any

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.rubric import Evaluator
from ergon_core.core.domain.experiments.handles import DefinitionHandle
from ergon_core.core.domain.experiments.worker_spec import WorkerSpec


class Experiment:
    """Composition root binding a benchmark, worker specs, evaluators, and assignments."""

    def __init__(
        self,
        *,
        benchmark: Benchmark,
        workers: Mapping[str, WorkerSpec],
        evaluators: Mapping[str, Evaluator] | None = None,
        assignments: Mapping[str, str | Sequence[str]] | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        self.benchmark = benchmark
        self.workers: dict[str, WorkerSpec] = dict(workers)
        self.evaluators: dict[str, Evaluator] = dict(evaluators or {})
        self.assignments: dict[str, str | list[str]] | None = (
            _normalise_assignments(assignments) if assignments is not None else None
        )
        self.metadata: dict[str, Any] = dict(metadata or {})  # slopcop: ignore[no-typing-any]
        self._persisted: DefinitionHandle | None = None

    @classmethod
    def from_single_worker(
        cls,
        *,
        benchmark: Benchmark,
        worker: WorkerSpec,
        evaluators: Mapping[str, Evaluator] | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> "Experiment":
        """Convenience constructor for the common single-worker case."""
        binding_key = worker.name
        return cls(
            benchmark=benchmark,
            workers={binding_key: worker},
            evaluators=evaluators,
            assignments=None,
            metadata=metadata,
        )

    def validate(self) -> None:
        """Cheap composition validation of the full experiment object graph."""
        from ergon_core.core.domain.experiments.validation import (
            ExperimentValidationService,
        )

        ExperimentValidationService().validate(self)


def _normalise_assignments(
    raw: Mapping[str, str | Sequence[str]],
) -> dict[str, str | list[str]]:
    """Convert immutable mapping values to mutable lists where needed."""
    out: dict[str, str | list[str]] = {}
    for key, value in raw.items():
        if isinstance(value, str):
            out[key] = value
        else:
            out[key] = list(value)
    return out
