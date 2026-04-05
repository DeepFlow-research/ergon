"""Public experiment composition root."""

from collections.abc import Mapping, Sequence
from typing import Any

from h_arcane.api.benchmark import Benchmark
from h_arcane.api.evaluator import Evaluator
from h_arcane.api.handles import ExperimentRunHandle, PersistedExperimentDefinition
from h_arcane.api.worker import Worker
from h_arcane.core.runtime.services.run_service import create_experiment_run


class Experiment:
    """Composition root binding a benchmark, workers, evaluators, and assignments.

    This is the main object users build and hand to ``persist()`` / ``run()``.
    """

    def __init__(
        self,
        *,
        benchmark: Benchmark,
        workers: Mapping[str, Worker],
        evaluators: Mapping[str, Evaluator] | None = None,
        assignments: Mapping[str, str | Sequence[str]] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.benchmark = benchmark
        self.workers: dict[str, Worker] = dict(workers)
        self.evaluators: dict[str, Evaluator] = dict(evaluators or {})
        self.assignments: dict[str, str | list[str]] | None = (
            _normalise_assignments(assignments) if assignments is not None else None
        )
        self.metadata: dict[str, Any] = dict(metadata or {})
        self._persisted: PersistedExperimentDefinition | None = None

    @classmethod
    def from_single_worker(
        cls,
        *,
        benchmark: Benchmark,
        worker: Worker,
        evaluators: Mapping[str, Evaluator] | None = None,
        metadata: Mapping[str, Any] | None = None,
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
        - no duplicate task keys within an instance
        - parent_task_key and dependency_task_keys reference valid tasks
        - assignment worker keys and task keys reference valid objects
        """
        self.benchmark.validate()
        for worker in self.workers.values():
            worker.validate()
        for evaluator in self.evaluators.values():
            evaluator.validate()

        required_slots = set(self.benchmark.evaluator_requirements())
        missing_slots = required_slots - set(self.evaluators)
        if missing_slots:
            missing = ", ".join(sorted(missing_slots))
            raise ValueError(f"Missing required evaluator bindings: {missing}")

        instances = self.benchmark.build_instances()
        all_task_keys_by_instance: dict[str, set[str]] = {}

        for instance_key, tasks in instances.items():
            task_keys: set[str] = set()
            for task in tasks:
                if task.instance_key != instance_key:
                    raise ValueError(
                        f"Task {task.task_key!r} declares instance_key "
                        f"{task.instance_key!r} but belongs to instance {instance_key!r}"
                    )
                if task.task_key in task_keys:
                    raise ValueError(
                        f"Duplicate task_key {task.task_key!r} in instance {instance_key!r}"
                    )
                task_keys.add(task.task_key)

            for task in tasks:
                if task.parent_task_key is not None and task.parent_task_key not in task_keys:
                    raise ValueError(
                        f"Unknown parent_task_key {task.parent_task_key!r} "
                        f"in instance {instance_key!r}"
                    )
                for dep_key in task.dependency_task_keys:
                    if dep_key not in task_keys:
                        raise ValueError(
                            f"Unknown dependency_task_key {dep_key!r} for task "
                            f"{task.task_key!r} in instance {instance_key!r}"
                        )
                for eval_key in task.evaluator_binding_keys:
                    if eval_key not in self.evaluators:
                        raise ValueError(
                            f"Task {task.task_key!r} references undeclared evaluator "
                            f"binding key {eval_key!r}"
                        )

            all_task_keys_by_instance[instance_key] = task_keys

        if self.assignments is not None:
            all_task_keys_flat = {
                tk for keys in all_task_keys_by_instance.values() for tk in keys
            }
            for worker_key, task_ref in self.assignments.items():
                if worker_key not in self.workers:
                    raise ValueError(
                        f"Assignment references unknown worker key {worker_key!r}"
                    )
                task_keys_list = [task_ref] if isinstance(task_ref, str) else task_ref
                for tk in task_keys_list:
                    if tk not in all_task_keys_flat:
                        raise ValueError(
                            f"Assignment references unknown task key {tk!r} "
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
        from h_arcane.core.runtime.services.experiment_persistence_service import (
            persist_experiment_definition,
        )

        self.validate()
        persisted = persist_experiment_definition(self)
        self._persisted = persisted
        return persisted

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(self) -> ExperimentRunHandle:
        """Ensure a persisted definition exists, create a run, and dispatch execution."""
        if self._persisted is None:
            self.persist()
        assert self._persisted is not None
        return await create_experiment_run(self._persisted)


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
