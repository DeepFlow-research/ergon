from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ergon_builtins.sandbox.e2b_runtime import E2BSandboxRuntime


@pytest.mark.asyncio
async def test_e2b_binary_reads_and_detach_preserve_remote_lifetime():
    content = b"\x00\xff\x80binary"
    sandbox = SimpleNamespace(
        sandbox_id="proof",
        files=SimpleNamespace(read=AsyncMock(return_value=content)),
        kill=AsyncMock(),
    )
    runtime = E2BSandboxRuntime(sandbox)
    assert await runtime.read_file("/workspace/artifact") == content
    sandbox.files.read.assert_awaited_once_with("/workspace/artifact", format="bytes")
    await runtime.close_local()
    sandbox.kill.assert_not_awaited()
    await runtime.close()
    sandbox.kill.assert_awaited_once()
