from uuid import uuid4

from ergon_core.core.application.evaluation.dto_mapping import evaluation_row_to_dto
from ergon_core.core.application.evaluation.summary import EvaluationSummary
from ergon_core.core.persistence.telemetry.models import RunTaskEvaluation


def test_evaluation_row_to_dto_maps_multiple_criterion_outcomes() -> None:
    evaluation_id = uuid4()
    run_id = uuid4()
    task_id = uuid4()
    summary = EvaluationSummary(
        evaluator_name="judge",
        max_score=2.0,
        normalized_score=0.75,
        stages_evaluated=1,
        stages_passed=0,
        criterion_results=[
            {
                "criterion_slug": "accuracy",
                "criterion_name": "Accuracy",
                "criterion_type": "rubric",
                "criterion_description": "Answer is accurate.",
                "stage_num": 0,
                "stage_name": "default",
                "criterion_num": 0,
                "status": "passed",
                "score": 1.0,
                "max_score": 1.0,
                "passed": True,
                "weight": 1.0,
                "contribution": 1.0,
                "feedback": "good",
                "evaluation_input": "answer",
            },
            {
                "criterion_slug": "citation",
                "criterion_name": "Citation",
                "criterion_type": "rubric",
                "criterion_description": "Answer cites evidence.",
                "stage_num": 0,
                "stage_name": "default",
                "criterion_num": 1,
                "status": "failed",
                "score": 0.5,
                "max_score": 1.0,
                "passed": False,
                "weight": 1.0,
                "contribution": 0.5,
                "feedback": "missing source",
                "evaluated_resource_ids": ["resource-1"],
            },
        ],
    )
    row = RunTaskEvaluation(
        id=evaluation_id,
        run_id=run_id,
        task_execution_id=uuid4(),
        task_id=task_id,
        definition_evaluator_id=uuid4(),
        score=1.5,
        passed=False,
        feedback="mixed",
        summary_json=summary.model_dump(mode="json"),
    )

    dto = evaluation_row_to_dto(row)

    assert dto.id == str(evaluation_id)
    assert dto.run_id == str(run_id)
    assert dto.task_id == str(task_id)
    assert dto.evaluator_name == "judge"
    assert dto.total_score == 1.5
    assert [criterion.id for criterion in dto.criterion_results] == [
        f"{evaluation_id}-0",
        f"{evaluation_id}-1",
    ]
    assert [criterion.criterion_slug for criterion in dto.criterion_results] == [
        "accuracy",
        "citation",
    ]
    assert dto.criterion_results[1].evaluated_resource_ids == ["resource-1"]
