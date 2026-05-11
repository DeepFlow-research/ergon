"""Contracts for evaluation context DTO required fields."""

from uuid import uuid4

import pytest
from collections.abc import AsyncGenerator
from collections.abc import Iterable
from typing import Any, ClassVar

from ergon_core.api import (
    Evaluator,
    Sandbox,
    SandboxRuntime,
    Task,
    TaskEvaluationResult,
    Worker,
)
from ergon_core.api.criterion import Criterion, CriterionOutcome
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.application.evaluation.models import (
    CriterionContext,
    TaskEvaluationContext,
)
from ergon_core.core.application.evaluation.models import (
    DispatchEvaluatorsCommand,
    PreparedSingleEvaluator,
)
from ergon_core.core.application.evaluation.service import EvaluationService
from pydantic import ValidationError


class _SchemaWorker(Worker):
    type_slug: ClassVar[str] = "schema-worker"

    async def execute(
        self, task: Task, *, context: Any, sandbox: Sandbox
    ) -> AsyncGenerator[Any, None]:
        if False:
            yield None


class _SchemaSandbox(Sandbox):
    type_slug: ClassVar[str] = "schema-sandbox"

    async def provision(self, *, run_id, task_id) -> SandboxRuntime:
        raise NotImplementedError

    async def terminate(self) -> None:
        return None


class _SchemaEvaluator(Evaluator):
    type_slug: ClassVar[str] = "schema-evaluator"

    def criteria_for(self, task: Task) -> Iterable[Criterion]:
        return ()

    def aggregate_task(
        self, task: Task, criterion_results: Iterable[CriterionOutcome]
    ) -> TaskEvaluationResult:
        return TaskEvaluationResult(evaluator_name=self.name, score=1.0, passed=True)


def test_criterion_context_requires_task_input_and_agent_reasoning_field() -> None:
    with pytest.raises(ValidationError):
        CriterionContext(run_id=uuid4())


def test_task_evaluation_context_requires_task_input_and_agent_reasoning_field() -> None:
    with pytest.raises(ValidationError):
        TaskEvaluationContext(run_id=uuid4())


def test_task_evaluation_context_allows_missing_agent_output_value() -> None:
    context = TaskEvaluationContext(
        run_id=uuid4(),
        task_input="prove the theorem",
        agent_reasoning=None,
    )

    assert context.agent_reasoning is None
    assert context.sandbox_id is None


def test_prepared_single_evaluator_requires_task_input() -> None:
    with pytest.raises(ValidationError):
        PreparedSingleEvaluator(
            evaluator_index=0,
            evaluator_name="rubric",
        )


def test_evaluator_dispatch_uses_task_bound_evaluator_and_description(  # noqa: C901
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition_id = uuid4()
    task_id = uuid4()
    node_id = uuid4()
    execution_id = uuid4()

    class _ExecutionRow:
        final_assistant_message = "worker answer"

    task = Task(
        task_slug="task",
        instance_key="instance",
        description="actual task prompt",
        worker=_SchemaWorker(name="worker", model=None),
        sandbox=_SchemaSandbox(),
        evaluators=(_SchemaEvaluator(name="rubric"),),
        task_payload={},
    )

    class _FirstResult:
        def first(self) -> RunGraphNode:
            return RunGraphNode(
                id=node_id,
                run_id=uuid4(),
                task_id=task_id,
                definition_task_id=task_id,
                instance_key="instance",
                task_slug="task",
                description="actual task prompt",
                task_json=task.to_definition(),
                status="completed",
            )

    class _Session:
        def exec(self, _statement) -> _FirstResult:
            return _FirstResult()

        def get(
            self,
            model: type[RunTaskExecution],
            _id,
        ) -> _ExecutionRow | None:
            return _ExecutionRow() if model is RunTaskExecution else None

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "ergon_core.core.application.evaluation.service.get_session",
        _Session,
    )

    dispatch = EvaluationService().prepare_dispatch(
        DispatchEvaluatorsCommand(
            run_id=uuid4(),
            definition_id=definition_id,
            task_id=task_id,
            execution_id=execution_id,
        )
    )

    assert dispatch.valid_evaluators[0].task_input == "actual task prompt"
    assert dispatch.valid_evaluators[0].evaluator_index == 0
    assert dispatch.valid_evaluators[0].evaluator_name == "rubric"
