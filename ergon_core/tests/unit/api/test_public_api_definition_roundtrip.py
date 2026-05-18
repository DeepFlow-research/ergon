"""Round-trip contracts for object-bound public API snapshots."""

from collections.abc import AsyncGenerator
from typing import Any, ClassVar
from uuid import uuid4

import pytest

from ergon_core.api.benchmark.task import EmptyTaskPayload, Task
from ergon_core.api.criterion.context import CriterionContext
from ergon_core.api.criterion.criterion import Criterion
from ergon_core.api.criterion.results import CriterionOutcome
from ergon_core.api.rubric.rubric import Rubric
from ergon_core.api.sandbox.runtime import CommandResult
from ergon_core.api.sandbox.sandbox import Sandbox
from ergon_core.api.toolkit import Toolkit
from ergon_core.api.worker.context import WorkerContext
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.api.worker.worker import Worker, WorkerStreamItem


class FakeToolkit(Toolkit):
    label: str = "fake"

    def tools(self, sandbox: Any, task: Any) -> list:
        return []


class FakeCriterion(Criterion):
    type_slug: ClassVar[str] = "fake-criterion"
    threshold: float = 0.5

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        return CriterionOutcome(slug=self.slug, name=self.slug, score=1.0, passed=True)


class FakeSandbox(Sandbox):
    image: str = "fake:latest"

    async def provision(self) -> None:
        return None

    async def _bind_runtime(self, sandbox_id: str) -> None:
        return None

    async def run_command(
        self,
        cmd: str | list[str],
        *,
        timeout: int | None = None,
    ) -> CommandResult:
        return CommandResult(stdout="", stderr="", exit_code=0)


class FakeWorker(Worker):
    type_slug: ClassVar[str] = "fake-worker"

    toolkit: Toolkit

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output="ok")


class FakeTask(Task[EmptyTaskPayload]):
    """Concrete importable task class for round-trip tests."""


@pytest.mark.asyncio
async def test_object_bound_task_definition_round_trips_concrete_nested_components() -> None:
    task = FakeTask(
        task_slug="fake",
        instance_key="sample-1",
        description="Fake object-bound task.",
        worker=FakeWorker(name="worker", model=None, toolkit=FakeToolkit(label="roundtrip")),
        sandbox=FakeSandbox(image="fake:v2"),
        evaluators=(
            Rubric(
                name="default",
                criteria=(FakeCriterion(slug="quality", threshold=0.8),),
            ),
        ),
    )

    dumped = task.model_dump(mode="json")
    loaded = await Task.from_definition(dumped, task_id=uuid4())

    assert type(loaded) is FakeTask
    assert type(loaded.worker) is FakeWorker
    assert loaded.worker is not None
    assert type(loaded.worker.toolkit) is FakeToolkit
    assert loaded.worker.toolkit.label == "roundtrip"
    assert type(loaded.sandbox) is FakeSandbox
    assert loaded.sandbox is not None
    assert loaded.sandbox.image == "fake:v2"
    assert type(loaded.evaluators[0]) is Rubric
    assert type(loaded.evaluators[0].criteria[0]) is FakeCriterion
    assert loaded.evaluators[0].criteria[0].threshold == 0.8


def test_toolkit_from_definition_requires_type_discriminator() -> None:
    with pytest.raises(ValueError, match="Toolkit snapshot.*`_type`"):
        Toolkit.from_definition({"label": "missing"})


def test_toolkit_from_definition_rejects_non_toolkit_type() -> None:
    with pytest.raises(TypeError, match="Toolkit _type.*Toolkit subclass"):
        Toolkit.from_definition(
            {"_type": "ergon_core.api.benchmark.task:Task", "label": "wrong"}
        )


def test_criterion_from_definition_requires_type_discriminator() -> None:
    with pytest.raises(ValueError, match="Criterion snapshot.*`_type`"):
        Criterion.from_definition({"slug": "missing"})


def test_criterion_from_definition_rejects_non_criterion_type() -> None:
    with pytest.raises(TypeError, match="Criterion _type.*Criterion subclass"):
        Criterion.from_definition(
            {"_type": "ergon_core.api.benchmark.task:Task", "slug": "wrong"}
        )


def test_parametrized_generic_task_type_is_rejected_when_persisting() -> None:
    task = Task[EmptyTaskPayload](
        task_slug="generic",
        instance_key="sample-1",
        description="Should use a concrete subclass before persistence.",
    )

    with pytest.raises(ValueError, match="Task snapshot.*concrete Task subclass"):
        task.model_dump(mode="json")
