from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import httpx
import pytest
from ergon_builtins.sandbox import e2b_runtime
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


@pytest.mark.asyncio
async def test_lost_upload_response_retries_identical_bytes_without_duplicating_content(
    monkeypatch,
):
    files = {}
    uploads = 0

    async def write(path, content):
        nonlocal uploads
        files[path] = content
        uploads += 1
        if uploads == 1:
            raise httpx.ReadError("Response lost after the file was written")

    sleep = AsyncMock()
    monkeypatch.setattr(e2b_runtime.asyncio, "sleep", sleep)
    sandbox = SimpleNamespace(sandbox_id="proof", files=SimpleNamespace(write=write))
    content = b"\x00\xffone complete artifact"
    await E2BSandboxRuntime(sandbox).write_file("/workspace/artifact", content)
    assert files == {"/workspace/artifact": content}
    assert uploads == 2
    sleep.assert_awaited_once_with(1)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [httpx.ReadError("unavailable"), ValueError("invalid path")])
async def test_upload_failure_stays_bounded_and_preserves_original_error(monkeypatch, error):
    sleep = AsyncMock()
    monkeypatch.setattr(e2b_runtime.asyncio, "sleep", sleep)
    write = AsyncMock(side_effect=error)
    sandbox = SimpleNamespace(sandbox_id="proof", files=SimpleNamespace(write=write))
    with pytest.raises(type(error)) as raised:
        await E2BSandboxRuntime(sandbox).write_file("/workspace/artifact", b"content")
    assert raised.value is error
    attempts = 3 if isinstance(error, httpx.ReadError) else 1
    assert write.await_args_list == [call("/workspace/artifact", b"content")] * attempts
    assert sleep.await_args_list == ([call(1), call(2)] if attempts == 3 else [])
