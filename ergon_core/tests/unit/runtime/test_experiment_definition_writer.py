from typing import ClassVar
from uuid import uuid4

import pytest

from ergon_core.api.benchmark.task import Task, TaskSpec
from ergon_core.api.criterion import Criterion, CriterionContext, CriterionOutcome
from ergon_core.core.application.experiments.definition_writer import (
    _criterion_snapshot_name,
    _task_to_definition_json,
)
from ergon_core.tests.unit.runtime._test_workers import EchoSandbox, EchoWorker


class _Criterion(Criterion):
    type_slug: ClassVar[str] = "ci-criterion"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        return CriterionOutcome(slug=self.slug, name=self.slug, score=1.0, passed=True)


def test_criterion_snapshot_uses_public_slug_not_missing_name_attribute() -> None:
    criterion = _Criterion(slug="ci-criterion-instance")

    assert _criterion_snapshot_name(criterion) == "ci-criterion-instance"


def test_task_to_definition_json_legacy_taskspec_shape() -> None:
    spec = TaskSpec(
        task_slug="legacy",
        instance_key="sample-1",
        description="legacy task",
        evaluator_binding_keys=("default",),
    )
    result = _task_to_definition_json(spec)

    assert result["_type"].endswith(":TaskSpec")
    assert result["_legacy"] is True
    assert "worker" not in result
    assert result["evaluator_binding_keys"] == ["default"]


def test_task_to_definition_json_object_bound_shape() -> None:
    task = Task(
        task_slug="object",
        instance_key="sample-1",
        description="object-bound task",
        worker=EchoWorker(name="echo", model=None),
        sandbox=EchoSandbox(),
        evaluators=(),
    )
    result = _task_to_definition_json(task)

    assert result["_type"].endswith(":Task")
    assert "_legacy" not in result
    assert result["worker"]["_type"].endswith(":EchoWorker")
    assert result["sandbox"]["_type"].endswith(":EchoSandbox")
    assert isinstance(result["evaluators"], list)


@pytest.mark.asyncio
async def test_object_bound_task_json_round_trips_through_from_definition() -> None:
    task = Task(
        task_slug="object",
        instance_key="sample-1",
        description="object-bound task",
        worker=EchoWorker(name="echo", model=None),
        sandbox=EchoSandbox(),
        evaluators=(),
    )
    task_json = _task_to_definition_json(task)
    task_id = uuid4()

    restored = await Task.from_definition(task_json, task_id=task_id)

    assert restored.task_slug == "object"
    assert restored.task_id == task_id
    assert restored.worker is not None
    assert type(restored.worker).__name__ == "EchoWorker"
    assert restored.sandbox is not None
    assert type(restored.sandbox).__name__ == "EchoSandbox"
