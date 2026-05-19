from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from ergon_core.core.application.workflows.orchestration import FailTaskExecutionCommand


@pytest.mark.asyncio
async def test_finalize_failure_preserves_structured_error_json(monkeypatch) -> None:
    from ergon_core.core.application.tasks import execution as module
    from ergon_core.core.application.tasks.execution import TaskExecutionService

    execution_id = uuid4()
    run_id = uuid4()
    node_id = uuid4()
    execution = SimpleNamespace(
        id=execution_id,
        run_id=run_id,
        node_id=node_id,
        task_id=None,
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
