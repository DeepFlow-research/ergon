"""Unit-level round-trip coverage for task_payload on dispatch DTOs.

Regression coverage for the P0 bug where `task_payload` was dropped between
`ExperimentDefinitionTask` (DB) and `WorkerContext.metadata` (worker). See
`docs/bugs/open/2026-04-21-task-payload-metadata-propagation.md`.

These tests exercise only the DTO layer — the service/Inngest wiring is
covered by the state test at `tests/state/test_task_execution_service_payload.py`.
"""

from uuid import uuid4

from ergon_core.core.runtime.services.child_function_payloads import (
    WorkerExecuteRequest,
)
from ergon_core.core.runtime.services.orchestration_dto import (
    PreparedTaskExecution,
)


def test_prepared_task_execution_round_trips_task_payload() -> None:
    payload = {"toolkit_benchmark": "minif2f", "extra": 7}
    prepared = PreparedTaskExecution(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        task_slug="slug",
        task_description="desc",
        benchmark_type="test",
        execution_id=uuid4(),
        task_payload=payload,
    )

    assert prepared.task_payload == payload

    dumped = prepared.model_dump()
    assert dumped["task_payload"] == payload

    restored = PreparedTaskExecution.model_validate(dumped)
    assert restored.task_payload == payload


def test_prepared_task_execution_defaults_to_empty_dict() -> None:
    prepared = PreparedTaskExecution(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        task_slug="slug",
        task_description="desc",
        benchmark_type="test",
        execution_id=uuid4(),
    )
    assert prepared.task_payload == {}


def test_worker_execute_request_round_trips_task_payload() -> None:
    payload = {"toolkit_benchmark": "minif2f"}
    request = WorkerExecuteRequest(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sbx-1",
        task_slug="slug",
        task_description="desc",
        assigned_worker_slug="researcher",
        worker_type="cloud-llm",
        benchmark_type="test",
        task_payload=payload,
    )

    assert request.task_payload == payload

    dumped = request.model_dump()
    assert dumped["task_payload"] == payload

    restored = WorkerExecuteRequest.model_validate(dumped)
    assert restored.task_payload == payload


def test_worker_execute_request_defaults_to_empty_dict() -> None:
    request = WorkerExecuteRequest(
        run_id=uuid4(),
        definition_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sbx-1",
        task_slug="slug",
        task_description="desc",
        assigned_worker_slug="researcher",
        worker_type="cloud-llm",
        benchmark_type="test",
    )
    assert request.task_payload == {}
