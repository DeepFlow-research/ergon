"""Contracts for Phase 1 of the authoring API redesign."""

from collections.abc import AsyncGenerator, Iterable, Mapping, Sequence
from typing import Annotated, Any, ClassVar, get_args, get_origin, get_type_hints
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from ergon_core.api import (
    Benchmark,
    ContainmentViolation,
    Criterion,
    CriterionContext,
    CriterionOutcome,
    EmptyTaskPayload,
    Evaluator,
    Experiment,
    Rubric,
    Sandbox,
    SandboxKindMismatch,
    SandboxNotLiveError,
    Task,
    TaskEvaluationResult,
    TaskNotMaterializedError,
    WeightedCriterion,
    Worker,
    WorkerContext,
    WorkerOutput,
    WorkerStreamItem,
)


class _Sandbox(Sandbox):
    async def provision(self) -> None:
        object.__setattr__(self, "_runtime", _Runtime())


class _OtherSandbox(Sandbox):
    async def provision(self) -> None:
        object.__setattr__(self, "_runtime", _Runtime())


class _Worker(Worker):
    type_slug: ClassVar[str] = "test-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output=f"{task.task_slug}:{sandbox.sandbox_id}", success=True)


class _SandboxBoundWorker(_Worker):
    requires_sandbox: ClassVar[type[Sandbox]] = _Sandbox


class _Criterion(Criterion):
    type_slug: ClassVar[str] = "test-criterion"

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        return CriterionOutcome(slug=self.slug, score=1.0, passed=True)


class _SandboxBoundCriterion(_Criterion):
    requires_sandbox: ClassVar[type[Sandbox]] = _Sandbox


class _Evaluator(Evaluator):
    type_slug: ClassVar[str] = "test-evaluator"

    def criteria_for(self, task: Task) -> Iterable[Criterion]:
        return ()

    def aggregate_task(
        self,
        task: Task,
        criterion_results: Iterable[CriterionOutcome],
    ) -> TaskEvaluationResult:
        return TaskEvaluationResult(
            task_slug=task.task_slug,
            score=1.0,
            passed=True,
            evaluator_name=self.name,
            criterion_results=list(criterion_results),
        )


class _CriterionEvaluator(_Evaluator):
    criteria: tuple[WeightedCriterion, ...]

    def criteria_for(self, task: Task) -> Iterable[Criterion]:
        return tuple(weighted.criterion for weighted in self.criteria)


class _Benchmark(Benchmark):
    type_slug: ClassVar[str] = "test-benchmark"

    tasks: tuple[Task, ...]

    def build_instances(self) -> Mapping[str, Sequence[Task]]:
        return {"default": self.tasks}


class _Runtime:
    sandbox_id = "sandbox-123"

    async def run_command(self, command: str, timeout: int = 30) -> str:
        return f"{command}:{timeout}"

    async def write_file(self, path: str, content: bytes) -> None:
        self.written = (path, content)

    async def read_file(self, path: str) -> bytes:
        return path.encode()

    async def list_files(self, path: str) -> list[str]:
        return [path]


def test_public_exceptions_keep_canonical_context_attributes() -> None:
    task_id = uuid4()
    ancestor = uuid4()
    run_id = uuid4()

    missing = TaskNotMaterializedError("missing task")
    not_live = SandboxNotLiveError("LeanSandbox")
    mismatch = SandboxKindMismatch(
        task_id=task_id,
        component="worker test-worker",
        required=_Sandbox,
        actual=_OtherSandbox,
    )
    containment = ContainmentViolation(target=task_id, ancestor=ancestor, run_id=run_id)

    assert str(missing) == "missing task"
    assert not_live.sandbox_kind == "LeanSandbox"
    assert mismatch.task_id == task_id
    assert mismatch.component == "worker test-worker"
    assert mismatch.required is _Sandbox
    assert mismatch.actual is _OtherSandbox
    assert containment.target == task_id
    assert containment.ancestor == ancestor
    assert containment.run_id == run_id


@pytest.mark.asyncio
async def test_sandbox_proxies_require_and_forward_to_live_runtime() -> None:
    sandbox = _Sandbox()

    with pytest.raises(SandboxNotLiveError, match="_Sandbox method called before provision"):
        await sandbox.run_command("echo hi")

    await sandbox.provision()

    assert sandbox.is_live
    assert sandbox.sandbox_id == "sandbox-123"
    assert await sandbox.run_command("echo hi", timeout=5) == "echo hi:5"
    assert await sandbox.read_file("/tmp/out") == b"/tmp/out"
    assert await sandbox.list_files("/tmp") == ["/tmp"]


def test_authoring_models_round_trip_through_type_discriminators() -> None:
    worker = _Worker(name="primary", model="stub:model", metadata={"role": "test"})
    sandbox = _Sandbox(env={"A": "B"})
    criterion = _Criterion(slug="quality", weight=2.0)
    evaluator = _CriterionEvaluator(
        name="rubric",
        criteria=(WeightedCriterion(criterion=criterion, weight=2.0),),
    )
    task = Task(
        task_slug="root",
        instance_key="default",
        description="Definition-time task",
        worker=worker,
        sandbox=sandbox,
        evaluators=(evaluator,),
        task_payload=EmptyTaskPayload(),
    )
    benchmark = _Benchmark(name="bench", tasks=(task,))
    task_id = uuid4()

    assert "_type" not in worker.model_dump(mode="json")
    assert "_type" not in sandbox.model_dump(mode="json")
    assert "_type" not in criterion.model_dump(mode="json")
    assert "_type" not in evaluator.model_dump(mode="json")
    assert "_type" not in benchmark.model_dump(mode="json")
    assert "_type" not in task.model_dump(mode="json")

    worker_json = worker.to_definition()
    sandbox_json = sandbox.to_definition()
    criterion_json = criterion.to_definition()
    evaluator_json = evaluator.to_definition()
    benchmark_json = benchmark.to_definition()
    task_json = task.to_definition()

    assert worker_json["_type"].endswith(":_Worker")
    assert task_json["worker"]["_type"].endswith(":_Worker")
    assert task_json["sandbox"]["_type"].endswith(":_Sandbox")
    assert task_json["evaluators"][0]["_type"].endswith(":_CriterionEvaluator")
    assert task_json["evaluators"][0]["criteria"][0]["criterion"]["_type"].endswith(":_Criterion")
    assert Worker.from_definition(worker_json) == worker
    assert Sandbox.from_definition(sandbox_json) == sandbox
    assert Criterion.from_definition(criterion_json) == criterion
    assert Evaluator.from_definition(evaluator_json) == evaluator
    assert Benchmark.from_definition(benchmark_json) == benchmark

    with pytest.raises(TaskNotMaterializedError, match="has no task_id"):
        task.task_id

    materialized = Task.from_definition(task_json, task_id=task_id)

    assert isinstance(materialized.worker, _Worker)
    assert isinstance(materialized.sandbox, _Sandbox)
    assert isinstance(materialized.evaluators[0], _CriterionEvaluator)
    assert materialized.task_id == task_id


def test_task_fields_have_typed_direct_bindings() -> None:
    hints = get_type_hints(Task, include_extras=True)

    assert _serialize_as_any_target(hints["worker"]) is Worker
    assert _serialize_as_any_target(hints["sandbox"]) is Sandbox
    assert get_origin(hints["evaluators"]) is tuple
    evaluator_binding = get_args(hints["evaluators"])[0]
    assert _serialize_as_any_target(evaluator_binding) is Evaluator


def test_rubric_uses_weighted_criteria_wrappers() -> None:
    criterion = _Criterion(slug="quality")
    rubric = Rubric(
        name="default",
        criteria=[WeightedCriterion(criterion=criterion, weight=2.5)],
    )
    task = Task(
        task_slug="root",
        instance_key="default",
        description="Definition-time task",
        worker=_Worker(name="primary", model="stub:model"),
        sandbox=_Sandbox(),
    )
    result = rubric.aggregate_task(
        task,
        [
            CriterionOutcome(slug="quality", score=0.5, passed=True, weight=1.0),
        ],
    )

    assert rubric.criteria == (WeightedCriterion(criterion=criterion, weight=2.5),)
    assert tuple(rubric.criteria_for(task)) == (criterion,)
    assert result.criterion_results[0].weight == 2.5


def test_experiment_is_public_pydantic_root_without_legacy_binding_pools() -> None:
    task = Task(
        task_slug="root",
        instance_key="default",
        description="Definition-time task",
        worker=_Worker(name="primary", model="stub:model"),
        sandbox=_Sandbox(),
    )
    benchmark = _Benchmark(name="bench", tasks=(task,))

    experiment = Experiment(benchmark=benchmark, metadata={"cohort": "smoke"})

    assert experiment.benchmark is benchmark
    assert experiment.metadata == {"cohort": "smoke"}
    assert not hasattr(experiment, "workers")
    assert not hasattr(experiment, "evaluators")
    assert not hasattr(experiment, "assignments")
    with pytest.raises(ValidationError):
        Experiment(benchmark=benchmark, workers={})  # type: ignore[call-arg]


def test_experiment_rejects_worker_sandbox_kind_mismatch() -> None:
    task = Task(
        task_slug="root",
        instance_key="default",
        description="Definition-time task",
        worker=_SandboxBoundWorker(name="primary", model="stub:model"),
        sandbox=_OtherSandbox(),
    )
    benchmark = _Benchmark(name="bench", tasks=(task,))

    with pytest.raises(SandboxKindMismatch) as exc_info:
        Experiment(benchmark=benchmark)

    assert exc_info.value.component == "worker primary"
    assert exc_info.value.required is _Sandbox
    assert exc_info.value.actual is _OtherSandbox


def _serialize_as_any_target(hint: object) -> object:
    assert get_origin(hint) is Annotated
    target, *metadata = get_args(hint)
    assert any(type(item).__name__ == "SerializeAsAny" for item in metadata)
    return target


def test_experiment_rejects_evaluator_criterion_sandbox_kind_mismatch() -> None:
    evaluator = _CriterionEvaluator(
        name="rubric",
        criteria=(WeightedCriterion(criterion=_SandboxBoundCriterion(slug="quality")),),
    )
    task = Task(
        task_slug="root",
        instance_key="default",
        description="Definition-time task",
        worker=_Worker(name="primary", model="stub:model"),
        sandbox=_OtherSandbox(),
        evaluators=(evaluator,),
    )
    benchmark = _Benchmark(name="bench", tasks=(task,))

    with pytest.raises(SandboxKindMismatch) as exc_info:
        Experiment(benchmark=benchmark)

    assert exc_info.value.component == "criterion quality"
    assert exc_info.value.required is _Sandbox
    assert exc_info.value.actual is _OtherSandbox
