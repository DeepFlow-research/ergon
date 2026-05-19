from uuid import uuid4

import pytest

from ergon_core.core.application.events.task_events import TaskCancelledEvent
from ergon_core.core.application.jobs import cleanup_cancelled_task as cleanup_module
from ergon_core.core.application.tasks.models import CleanupResult


class _FakeStepCtx:
    class _Step:
        async def run(self, _step_id: str, fn):
            result = fn()
            if hasattr(result, "__await__"):
                return await result
            return result

    def __init__(self) -> None:
        self.step = self._Step()


@pytest.mark.asyncio
async def test_cleanup_cancelled_task_marks_execution_without_releasing_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()
    task_id = uuid4()
    execution_id = uuid4()
    payload = TaskCancelledEvent(
        run_id=run_id,
        definition_id=uuid4(),
        task_id=task_id,
        execution_id=execution_id,
        cause="manager_decision",
    )
    cleanup = CleanupResult(
        run_id=run_id,
        task_id=task_id,
        execution_id=execution_id,
        sandbox_id="sbx-cancelled",
        sandbox_released=False,
        execution_row_updated=True,
    )

    class Service:
        def cleanup(self, *_args, **_kwargs):
            return cleanup

    class Emitter:
        async def publish(self, _event):
            return None

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(cleanup_module, "TaskCleanupService", lambda: Service())
    monkeypatch.setattr(cleanup_module, "get_session", lambda: SessionContext())
    monkeypatch.setattr(cleanup_module, "get_dashboard_event_publisher", lambda: Emitter())

    result = await cleanup_module.run_cleanup_cancelled_task_job(_FakeStepCtx(), payload)

    assert result["sandbox_id"] == "sbx-cancelled"
    assert result["sandbox_released"] is False
