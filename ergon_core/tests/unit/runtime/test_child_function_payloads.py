"""Contract tests for typed Inngest child function payloads."""

from uuid import uuid4

import pytest
from ergon_core.core.infrastructure.inngest.contracts import (
    PersistOutputsRequest,
    SandboxSetupRequest,
    TaskEvaluateRequest,
    WorkerExecuteRequest,
)
from pydantic import ValidationError


def test_task_evaluate_request_is_id_only() -> None:
    request = TaskEvaluateRequest(
        run_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        evaluator_index=0,
    )

    assert request.evaluator_index == 0


def test_task_evaluate_request_rejects_legacy_definition_fields() -> None:
    with pytest.raises(ValidationError):
        TaskEvaluateRequest(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            evaluator_id=uuid4(),
            evaluator_binding_key="researchrubrics-rubric",
            evaluator_type="researchrubrics-rubric",
        )


def test_worker_execute_request_requires_static_or_dynamic_identity() -> None:
    with pytest.raises(ValidationError):
        WorkerExecuteRequest(
            run_id=uuid4(),
            definition_id=uuid4(),
            task_id=None,
            execution_id=uuid4(),
            sandbox_id="sbx",
            task_slug="task",
            task_description="description",
            assigned_worker_slug="worker",
            worker_type="react",
            model_target="openai:gpt-4o",
            benchmark_type="researchrubrics",
        )


def test_worker_execute_request_allows_dynamic_worker_without_model_target() -> None:
    task_id = uuid4()
    request = WorkerExecuteRequest(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=task_id,
        execution_id=uuid4(),
        sandbox_id="sbx",
        task_slug="task",
        task_description="description",
        assigned_worker_slug="worker",
        worker_type="worker",
        model_target=None,
        benchmark_type="researchrubrics",
    )

    assert request.model_target is None
    assert request.task_id == task_id


def test_sandbox_and_persist_outputs_require_task_id() -> None:
    with pytest.raises(ValidationError):
        SandboxSetupRequest(
            run_id=uuid4(),
            definition_id=uuid4(),
            benchmark_type="researchrubrics",
        )

    with pytest.raises(ValidationError):
        PersistOutputsRequest(
            run_id=uuid4(),
            definition_id=uuid4(),
            execution_id=uuid4(),
            benchmark_type="researchrubrics",
        )
