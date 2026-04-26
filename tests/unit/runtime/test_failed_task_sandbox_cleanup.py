from unittest.mock import AsyncMock, patch

import pytest

from ergon_core.core.providers.sandbox.lifecycle import (
    SandboxTerminationReason,
    SandboxTerminationResult,
)
from ergon_core.core.runtime.inngest.propagate_execution import _terminate_failed_task_sandbox


@pytest.mark.asyncio
async def test_failed_task_sandbox_cleanup_delegates_to_lifecycle_service() -> None:
    result = SandboxTerminationResult(
        sandbox_id="sandbox-real",
        terminated=True,
        reason=SandboxTerminationReason.TERMINATED,
    )
    with patch(
        "ergon_core.core.runtime.inngest.propagate_execution.terminate_sandbox_by_id",
        new=AsyncMock(return_value=result),
    ) as terminate:
        await _terminate_failed_task_sandbox("sandbox-real")

    terminate.assert_awaited_once_with("sandbox-real")
