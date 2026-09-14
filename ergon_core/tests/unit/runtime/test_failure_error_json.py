from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import inngest
from ergon_core.core.application.runtime.orchestration import FailTaskExecutionCommand
from ergon_core.core.infrastructure.inngest.errors import execution_error_details


@pytest.mark.parametrize("wrapped", [False, True])
def test_execution_error_preserves_original_type_stack_and_context(wrapped) -> None:
    error = TimeoutError()
    error.add_note("retained response accounting")
    if wrapped:
        error = inngest.StepError(
            message="", name="TimeoutError", stack="original stack\nretained response accounting"
        )
    context = {"task_id": "task-123"}
    details = execution_error_details(error, phase="task_execute", context=context)
    assert details["message"] == "TimeoutError"
    assert details["exception_type"] == "TimeoutError"
    assert "retained response accounting" in details["stack"]
    assert details["context"]["task_id"] == "task-123"
    assert context == {"task_id": "task-123"}
    if wrapped:
        assert details["context"]["workflow_error_type"] == "StepError"
        assert "original stack" in details["stack"]
        assert "Workflow replay:" in details["stack"]


@pytest.mark.asyncio
async def test_finalize_failure_preserves_structured_error_json(monkeypatch) -> None:
    from ergon_core.core.application.runtime import execution as module
    from ergon_core.core.application.runtime.task_execution import TaskExecutionService

    execution_id = uuid4()
    sample_id = uuid4()
    task_id = uuid4()
    execution = SimpleNamespace(
        id=execution_id,
        sample_id=sample_id,
        task_id=task_id,
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
    monkeypatch.setattr(TaskExecutionService, "_cancelled", AsyncMock(return_value=False))

    async def fake_mark_failed_by_node(*args, **kwargs):
        return None

    async def fake_emit_task_status(*args, **kwargs):
        return None

    monkeypatch.setattr(module, "mark_task_failed_by_node", fake_mark_failed_by_node)
    monkeypatch.setattr(module, "_emit_task_status", fake_emit_task_status)

    await TaskExecutionService().finalize_failure(
        FailTaskExecutionCommand(
            execution_id=execution_id,
            sample_id=sample_id,
            task_id=None,
            error_message="provider returned malformed response",
            error_json=structured_error,
        )
    )

    assert execution.error_json == structured_error
