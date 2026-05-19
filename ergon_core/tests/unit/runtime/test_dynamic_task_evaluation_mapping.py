from uuid import uuid4
from types import SimpleNamespace

from ergon_core.core.persistence.telemetry.models import RunTaskEvaluation
from ergon_core.core.application.read_models.run_snapshot import _task_keyed_evaluations
from ergon_core.core.application.jobs.evaluate_task_run import _evaluator_binding_key


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


def test_task_keyed_evaluations_use_runtime_task_id_for_dynamic_tasks() -> None:
    run_id = uuid4()
    dynamic_task_id = uuid4()

    evaluation = RunTaskEvaluation(
        run_id=run_id,
        task_execution_id=uuid4(),
        task_id=dynamic_task_id,
        definition_evaluator_id=uuid4(),
        score=1.0,
        passed=True,
        feedback="passed",
        summary_json=_summary_json(),
    )

    result = _task_keyed_evaluations(
        [evaluation],
        str(run_id),
    )

    assert set(result) == {str(dynamic_task_id)}
    assert result[str(dynamic_task_id)].task_id == str(dynamic_task_id)
    assert result[str(dynamic_task_id)].total_score == 1.0


def test_blank_inline_evaluator_name_uses_definition_writer_fallback_key() -> None:
    assert _evaluator_binding_key(SimpleNamespace(name=""), 1) == "inline-1"
    assert _evaluator_binding_key(SimpleNamespace(name="judge"), 1) == "judge"
