from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from ergon_core.core.infrastructure.sandbox.lifecycle import (
    SandboxTerminationReason,
    SandboxTerminationResult,
)
from ergon_core.core.application.jobs.propagate_execution import _terminate_failed_task_sandbox


@pytest.mark.asyncio
async def test_failed_task_sandbox_cleanup_delegates_to_lifecycle_service() -> None:
    result = SandboxTerminationResult(
        sandbox_id="sandbox-real",
        terminated=True,
        reason=SandboxTerminationReason.TERMINATED,
    )
    with patch(
        "ergon_core.core.application.jobs.propagate_execution.terminate_sandbox_by_id",
        new=AsyncMock(return_value=result),
    ) as terminate:
        await _terminate_failed_task_sandbox(
            "sandbox-real",
            run_id=uuid4(),
            task_id=uuid4(),
        )

    terminate.assert_awaited_once_with("sandbox-real")
