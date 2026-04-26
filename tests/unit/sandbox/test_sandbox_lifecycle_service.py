from unittest.mock import AsyncMock, patch

import pytest

from ergon_core.core.providers.sandbox.lifecycle import (
    SandboxTerminationReason,
    terminate_sandbox_by_id,
)


@pytest.mark.asyncio
async def test_terminate_sandbox_by_id_dispatches_real_ids() -> None:
    with patch(
        "ergon_core.core.providers.sandbox.manager.BaseSandboxManager.terminate_by_sandbox_id",
        new=AsyncMock(return_value=True),
    ) as terminate:
        result = await terminate_sandbox_by_id("sbx-live-123")

    terminate.assert_awaited_once_with("sbx-live-123")
    assert result.terminated is True
    assert result.reason == SandboxTerminationReason.TERMINATED


@pytest.mark.asyncio
async def test_terminate_sandbox_by_id_handles_missing_id_explicitly() -> None:
    result = await terminate_sandbox_by_id(None)

    assert result.terminated is False
    assert result.reason == SandboxTerminationReason.MISSING_ID
    assert result.sandbox_id is None
