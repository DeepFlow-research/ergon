"""Contracts for evaluation context DTO required fields."""

from uuid import uuid4

import pytest
from ergon_core.core.persistence.definitions.models import ExperimentDefinitionTask
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.telemetry.models import RunTaskExecution
from ergon_core.core.runtime.evaluation.evaluation_schemas import (
    CriterionContext,
    TaskEvaluationContext,
)
from ergon_core.core.runtime.services.evaluation_dto import (
    DispatchEvaluatorsCommand,
    PreparedSingleEvaluator,
)
from ergon_core.core.runtime.services.evaluator_dispatch_service import EvaluatorDispatchService
from pydantic import ValidationError


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
            evaluator_id=uuid4(),
            evaluator_binding_key="rubric",
            evaluator_type="researchrubrics-rubric",
        )


def test_evaluator_dispatch_uses_definition_task_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition_id = uuid4()
    task_id = uuid4()
    node_id = uuid4()
    evaluator_id = uuid4()
    execution_id = uuid4()

    class _TaskEvaluatorRow:
        evaluator_binding_key = "rubric"

    class _EvaluatorDefinitionRow:
        id = evaluator_id
        evaluator_type = "researchrubrics-rubric"

    class _TaskRow:
        description = "actual task prompt"

    class _ExecutionRow:
        final_assistant_message = "worker answer"

    class _AllResult:
        def all(self) -> list[_TaskEvaluatorRow]:
            return [_TaskEvaluatorRow()]

    class _FirstResult:
        def first(self) -> _EvaluatorDefinitionRow:
            return _EvaluatorDefinitionRow()

    class _Session:
        def __init__(self) -> None:
            self.exec_calls = 0

        def exec(self, _statement) -> _AllResult | _FirstResult:
            self.exec_calls += 1
            if self.exec_calls == 1:
                return _AllResult()
            return _FirstResult()

        def get(
            self,
            model: type[RunTaskExecution] | type[ExperimentDefinitionTask] | type[RunGraphNode],
            _id,
        ) -> _ExecutionRow | _TaskRow | RunGraphNode | None:
            graph_node = RunGraphNode(
                id=node_id,
                run_id=uuid4(),
                definition_task_id=task_id,
                instance_key="instance",
                task_slug="task",
                description="actual task prompt",
                status="completed",
            )
            rows = {
                RunGraphNode: graph_node,
                RunTaskExecution: _ExecutionRow(),
                ExperimentDefinitionTask: _TaskRow(),
            }
            return rows.get(model)

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "ergon_core.core.runtime.services.evaluator_dispatch_service.get_session",
        _Session,
    )

    dispatch = EvaluatorDispatchService().prepare_dispatch(
        DispatchEvaluatorsCommand(
            run_id=uuid4(),
            definition_id=definition_id,
            node_id=node_id,
            task_id=task_id,
            execution_id=execution_id,
        )
    )

    assert dispatch.valid_evaluators[0].task_input == "actual task prompt"
