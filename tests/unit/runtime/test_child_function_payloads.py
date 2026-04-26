"""Contract tests for typed Inngest child function payloads."""

from uuid import uuid4

import pytest
from ergon_core.core.runtime.services.child_function_payloads import (
    EvaluateTaskRunRequest,
    PersistOutputsRequest,
    SandboxSetupRequest,
    WorkerExecuteRequest,
)
from pydantic import ValidationError


def test_evaluate_task_request_requires_runtime_node_identity() -> None:
    with pytest.raises(ValidationError):
        EvaluateTaskRunRequest(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            evaluator_id=uuid4(),
            evaluator_binding_key="researchrubrics-rubric",
            evaluator_type="researchrubrics-rubric",
        )


def test_evaluate_task_request_requires_evaluator_binding_key() -> None:
    with pytest.raises(ValidationError):
        EvaluateTaskRunRequest(
            run_id=uuid4(),
            definition_id=uuid4(),
            node_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            evaluator_id=uuid4(),
            evaluator_type="researchrubrics-rubric",
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
                "task_slug": "task",
                "task_description": "description",
                "assigned_worker_slug": "worker",
                "worker_type": "react",
                "benchmark_type": "researchrubrics",
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
