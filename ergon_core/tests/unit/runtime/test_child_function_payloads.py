"""Contract tests for typed Inngest child function payloads."""

from uuid import uuid4

import pytest
from ergon_core.core.infrastructure.inngest.contracts import (
    EvaluateTaskRunRequest,
    PersistOutputsRequest,
    SandboxSetupRequest,
    WorkerExecuteRequest,
)
from pydantic import ValidationError


def test_evaluate_task_request_requires_task_identity() -> None:
    with pytest.raises(ValidationError):
        EvaluateTaskRunRequest(
            run_id=uuid4(),
            definition_id=uuid4(),
            execution_id=uuid4(),
            evaluator_index=0,
            evaluator_name="rubric",
        )


def test_evaluate_task_request_uses_positional_evaluator_identity() -> None:
    payload = EvaluateTaskRunRequest(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        evaluator_index=0,
        evaluator_name="rubric",
    )

    assert payload.evaluator_index == 0
    assert payload.evaluator_name == "rubric"
    assert "node_id" not in payload.model_dump()
    assert "definition_evaluator_id" not in payload.model_dump()


def test_evaluate_task_request_requires_evaluator_index() -> None:
    with pytest.raises(ValidationError):
        EvaluateTaskRunRequest(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            evaluator_name="rubric",
        )


@pytest.mark.parametrize(
    ("payload_cls", "base_kwargs"),
    [
        (SandboxSetupRequest, {"benchmark_type": "researchrubrics"}),
        (
            WorkerExecuteRequest,
            {
                "execution_id": uuid4(),
                "sandbox_id": "sbx",
            },
        ),
        (
            PersistOutputsRequest,
            {
                "execution_id": uuid4(),
                "benchmark_type": "researchrubrics",
            },
        ),
    ],
)
def test_task_child_payloads_require_static_or_dynamic_identity(
    payload_cls: type[SandboxSetupRequest | WorkerExecuteRequest | PersistOutputsRequest],
    base_kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        payload_cls(
            run_id=uuid4(),
            definition_id=uuid4(),
            **base_kwargs,
        )
