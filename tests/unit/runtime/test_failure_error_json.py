from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ergon_core.core.runtime.services.orchestration_dto import FailTaskExecutionCommand


def test_build_error_json_includes_stack_without_inferred_triage() -> None:
    from ergon_core.core.runtime.errors.error_payload import (
        RuntimeErrorPayload,
        build_error_json,
    )

    try:
        raise RuntimeError(
            "Invalid response from OpenAI chat completions endpoint: "
            "choices.0.finish_reason input_value=None"
        )
    except RuntimeError as exc:
        payload = build_error_json(exc, phase="worker_execute")

    assert payload["message"].startswith("Invalid response from OpenAI")
    assert payload["exception_type"] == "RuntimeError"
    assert payload["phase"] == "worker_execute"
    assert "Traceback" in payload["stack"]
    assert "finish_reason" in payload["stack"]
    assert "category" not in payload
    assert "retryable" not in payload
    assert RuntimeErrorPayload.model_validate(payload).message == payload["message"]


def test_worker_exception_result_carries_structured_error_json() -> None:
    from ergon_core.core.runtime.inngest.worker_execute import (
        _worker_execute_result_from_exception,
    )

    try:
        raise RuntimeError("provider timeout")
    except RuntimeError as exc:
        result = _worker_execute_result_from_exception(exc)

    assert result.success is False
    assert result.error == "provider timeout"
    assert result.error_json is not None
    assert result.error_json["phase"] == "worker_execute"
    assert result.error_json["exception_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_finalize_failure_preserves_structured_error_json(monkeypatch) -> None:
    from ergon_core.core.runtime.services import task_execution_service as module
    from ergon_core.core.runtime.services.task_execution_service import TaskExecutionService

    execution_id = uuid4()
    run_id = uuid4()
    node_id = uuid4()
    execution = SimpleNamespace(
        id=execution_id,
        run_id=run_id,
        node_id=node_id,
        definition_task_id=None,
    )

    class Session:
        def get(self, model, key):
            assert key == execution_id
            return execution

        def add(self, row):
            assert row is execution

        def commit(self):
            pass

    @contextmanager
    def fake_get_session():
        yield Session()

    structured_error = {
        "message": "provider returned malformed response",
        "exception_type": "UnexpectedModelBehavior",
        "phase": "worker_execute",
        "stack": "Traceback ...",
    }

    monkeypatch.setattr(module, "get_session", fake_get_session)

    async def fake_mark_failed_by_node(*args, **kwargs):
        return None

    async def fake_emit_task_status(*args, **kwargs):
        return None

    monkeypatch.setattr(module, "mark_task_failed_by_node", fake_mark_failed_by_node)
    monkeypatch.setattr(module, "_emit_task_status", fake_emit_task_status)

    await TaskExecutionService().finalize_failure(
        FailTaskExecutionCommand(
            execution_id=execution_id,
            run_id=run_id,
            task_id=None,
            error_message="provider returned malformed response",
            error_json=structured_error,
        )
    )

    assert execution.error_json == structured_error
