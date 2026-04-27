from uuid import UUID, uuid4

import pytest
from ergon_core.core.api.runs import _task_keyed_evaluations
from ergon_core.core.persistence.telemetry.models import RunTaskEvaluation
from ergon_core.core.persistence.telemetry.repositories import CreateTaskEvaluation


def _summary_json() -> dict:
    return {
        "evaluator_name": "dynamic-evaluator",
        "max_score": 1.0,
        "normalized_score": 1.0,
        "stages_evaluated": 1,
        "stages_passed": 1,
        "criterion_results": [
            {
                "criterion_name": "criterion",
                "criterion_type": "test",
                "criterion_description": "Dynamic node criterion",
                "status": "passed",
                "score": 1.0,
                "max_score": 1.0,
                "passed": True,
                "weight": 1.0,
                "contribution": 1.0,
            }
        ],
    }


def test_task_keyed_evaluations_prefers_runtime_node_id_for_dynamic_tasks() -> None:
    run_id = uuid4()
    node_id = uuid4()
    static_definition_task_id = uuid4()

    evaluation = RunTaskEvaluation(
        run_id=run_id,
        node_id=node_id,
        task_execution_id=uuid4(),
        definition_task_id=static_definition_task_id,
        definition_evaluator_id=uuid4(),
        score=1.0,
        passed=True,
        feedback="passed",
        summary_json=_summary_json(),
    )

    result = _task_keyed_evaluations(
        [evaluation],
        str(run_id),
        defn_to_node={},
    )

    assert set(result) == {str(node_id)}
    assert result[str(node_id)].task_id == str(node_id)
    assert result[str(node_id)].total_score == 1.0


def test_task_evaluation_requires_runtime_node_id() -> None:
    node_field = RunTaskEvaluation.model_fields["node_id"]

    assert node_field.annotation is UUID
    assert node_field.is_required()


def test_create_task_evaluation_requires_runtime_node_id() -> None:
    node_field = CreateTaskEvaluation.model_fields["node_id"]

    assert node_field.annotation is UUID
    assert node_field.is_required()
