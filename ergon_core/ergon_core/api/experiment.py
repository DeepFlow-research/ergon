"""Public experiment composition root."""

from collections.abc import Mapping, Sequence
from typing import Any

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.evaluator import Evaluator
from ergon_core.api.handles import PersistedExperimentDefinition
from ergon_core.api.worker_spec import WorkerSpec


class Experiment:
    """Composition root binding a benchmark, worker specs, evaluators, and assignments.

    This is the main object users build and hand to ``persist()``.

    reason: RFC 2026-04-22 §1 — workers are described here as ``WorkerSpec``
    (config-time descriptor), not as live ``Worker`` instances. The
    registry factory is invoked exactly once per task at execute time with
    the real ``task_id`` / ``sandbox_id``. Holding a ``Worker`` here would
    force either sentinel identity fields or constructing the same worker
    twice.
    """

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
        self._persisted: PersistedExperimentDefinition | None = None

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

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Cheap composition validation of the full experiment object graph.

        Checks:
        - benchmark validates
        - every worker validates
        - every evaluator validates
        - required evaluator slots are filled
        - no duplicate task slugs within an instance
        - parent_task_slug and dependency_task_slugs reference valid tasks
        - assignment worker keys and task slugs reference valid objects
        """
        self.benchmark.validate()
        for spec in self.workers.values():
            spec.validate_spec()
        for evaluator in self.evaluators.values():
            evaluator.validate()

        if self.evaluators:
            required_slots = set(self.benchmark.evaluator_requirements())
            missing_slots = required_slots - set(self.evaluators)
            if missing_slots:
                missing = ", ".join(sorted(missing_slots))
                raise ValueError(f"Missing required evaluator bindings: {missing}")

        instances = self.benchmark.build_instances()
        all_task_slugs_by_instance: dict[str, set[str]] = {}

        for instance_key, tasks in instances.items():
            task_slugs: set[str] = set()
            for task in tasks:
                if task.instance_key != instance_key:
                    raise ValueError(
                        f"Task {task.task_slug!r} declares instance_key "
                        f"{task.instance_key!r} but belongs to instance {instance_key!r}"
                    )
                if task.task_slug in task_slugs:
                    raise ValueError(
                        f"Duplicate task_slug {task.task_slug!r} in instance {instance_key!r}"
                    )
                task_slugs.add(task.task_slug)

            for task in tasks:
                if task.parent_task_slug is not None and task.parent_task_slug not in task_slugs:
                    raise ValueError(
                        f"Unknown parent_task_slug {task.parent_task_slug!r} "
                        f"in instance {instance_key!r}"
                    )
                for dep_slug in task.dependency_task_slugs:
                    if dep_slug not in task_slugs:
                        raise ValueError(
                            f"Unknown dependency_task_slug {dep_slug!r} for task "
                            f"{task.task_slug!r} in instance {instance_key!r}"
                        )
                for eval_key in task.evaluator_binding_keys:
                    if eval_key not in self.evaluators:
                        raise ValueError(
                            f"Task {task.task_slug!r} references undeclared evaluator "
                            f"binding key {eval_key!r}"
                        )

            all_task_slugs_by_instance[instance_key] = task_slugs

        if self.assignments is not None:
            all_task_slugs_flat = {
                ts for slugs in all_task_slugs_by_instance.values() for ts in slugs
            }
            for worker_key, task_ref in self.assignments.items():
                if worker_key not in self.workers:
                    raise ValueError(f"Assignment references unknown worker key {worker_key!r}")
                task_slugs_list = [task_ref] if isinstance(task_ref, str) else task_ref
                for ts in task_slugs_list:
                    if ts not in all_task_slugs_flat:
                        raise ValueError(
                            f"Assignment references unknown task_slug {ts!r} "
                            f"for worker {worker_key!r}"
                        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def persist(self) -> PersistedExperimentDefinition:
        """Validate, materialise instances, and write immutable definition rows.

        Returns a rich ``PersistedExperimentDefinition`` handle.
        """
        # Deferred: api/ should not depend on core/ at module level.
        # These are the only api->core imports. Extracting to a composition
        # layer is flagged for v2.
        from ergon_core.core.runtime.services.experiment_persistence_service import (
            ExperimentPersistenceService,
        )

        self.validate()
        persisted = ExperimentPersistenceService().persist_definition(self)
        self._persisted = persisted
        return persisted


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


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
