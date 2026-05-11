"""Public experiment composition root."""

from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, PrivateAttr, model_validator

from ergon_core.api.benchmark import Benchmark, Task
from ergon_core.api.criterion import Criterion
from ergon_core.api.errors import SandboxKindMismatch, TaskNotMaterializedError
from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.core.domain.experiments.validation import ExperimentValidationService
from ergon_core.core.domain.experiments.handles import DefinitionHandle


class Experiment(BaseModel):
    """Composition root for a benchmark definition."""

    model_config = {"arbitrary_types_allowed": True, "extra": "forbid", "frozen": False}

    benchmark: Benchmark
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]

    _persisted: DefinitionHandle | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _validate_sandbox_compatibility(self) -> "Experiment":
        for tasks in self.benchmark.build_instances().values():
            for task in tasks:
                _check_component_requirement(
                    task=task,
                    component=f"worker {task.worker.name}",
                    required=task.worker.requires_sandbox,
                )
                for evaluator in task.evaluators:
                    _check_component_requirement(
                        task=task,
                        component=f"evaluator {evaluator.name}",
                        required=evaluator.requires_sandbox,
                    )
                    for criterion in _criteria_for(task, evaluator):
                        _check_component_requirement(
                            task=task,
                            component=f"criterion {criterion.slug}",
                            required=criterion.requires_sandbox,
                        )
        return self

    def validate(self) -> None:
        """Run cross-component validation before persistence."""
        ExperimentValidationService().validate(self)


def _criteria_for(task: Task, evaluator: Evaluator) -> Iterable[Criterion]:
    criteria = getattr(evaluator, "criteria", None)
    if criteria is not None:
        return tuple(getattr(criterion, "criterion", criterion) for criterion in criteria)
    return evaluator.criteria_for(task)


def _check_component_requirement(
    *,
    task: Task,
    component: str,
    required: type[Sandbox] | None,
) -> None:
    if required is None or isinstance(task.sandbox, required):
        return
    raise SandboxKindMismatch(
        task_id=_task_id_for_error(task),
        component=component,
        required=required,
        actual=type(task.sandbox),
    )


def _task_id_for_error(task: Task) -> UUID:
    try:
        return task.task_id
    except TaskNotMaterializedError:
        return UUID(int=0)
