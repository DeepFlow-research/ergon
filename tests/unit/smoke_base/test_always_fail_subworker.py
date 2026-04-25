"""``AlwaysFailSubworker`` does write → probe → failing result in that order.

Order matters: the partial-artifact invariant depends on the write
completing before task failure so the runtime's persist step can still
serialize the partial file.  If failure happens before the write, nothing
lands in blob storage and the sad-path driver's
``_assert_sadpath_partial_artifact`` fails for the wrong reason.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.e2e._fixtures.workers.researchrubrics_smoke_sadpath import (
    AlwaysFailSubworker,
)


def _fake_sandbox_with_clean_probe() -> MagicMock:
    """Sandbox whose ``commands.run`` returns exit_code=0 (clean probe)."""
    sandbox = MagicMock()
    probe_result = MagicMock(exit_code=0, stdout="1 /workspace/final_output/partial_abc.md")
    sandbox.files.write = AsyncMock()
    sandbox.commands.run = AsyncMock(return_value=probe_result)
    return sandbox


@pytest.mark.asyncio
async def test_work_writes_file_before_failing() -> None:
    sandbox = _fake_sandbox_with_clean_probe()
    sw = AlwaysFailSubworker()

    result = await sw.work(node_id="abc12345", sandbox=sandbox)

    assert sandbox.files.write.await_count == 1, (
        "expected one file write before the deliberate failure result"
    )
    written_path, written_content = sandbox.files.write.await_args.args
    assert written_path == "/workspace/final_output/partial_abc12345.md"
    assert "Partial work abc12345" in written_content
    assert result.file_path == written_path
    assert result.probe_exit_code == 1


@pytest.mark.asyncio
async def test_work_runs_probe_before_failing() -> None:
    sandbox = _fake_sandbox_with_clean_probe()
    sw = AlwaysFailSubworker()

    await sw.work(node_id="abc", sandbox=sandbox)

    assert sandbox.commands.run.await_count == 1, (
        "expected one sandbox command (the wc probe) before the failure result"
    )
    cmd = sandbox.commands.run.await_args.args[0]
    assert "wc -l" in cmd
    assert "partial_abc.md" in cmd


@pytest.mark.asyncio
async def test_work_returns_failure_message_with_node_id_and_path() -> None:
    """The failure output must name the node and the written path so an
    operator reading the failed-run log can correlate the partial
    artifact with the failure reason."""
    sandbox = _fake_sandbox_with_clean_probe()
    sw = AlwaysFailSubworker()

    result = await sw.work(node_id="abc", sandbox=sandbox)

    assert "deliberate failure of abc" in result.probe_stdout
    assert "partial_abc.md" in result.probe_stdout


@pytest.mark.asyncio
async def test_work_raises_if_pre_probe_fails_unexpectedly() -> None:
    """If the pre-failure probe itself fails, we raise a different error
    (precondition failure) — the sad-path design requires the probe to
    succeed cleanly before the deliberate raise so the WAL invariant
    holds."""
    sandbox = MagicMock()
    probe_result = MagicMock(exit_code=42, stdout="unexpected")
    sandbox.files.write = AsyncMock()
    sandbox.commands.run = AsyncMock(return_value=probe_result)
    sw = AlwaysFailSubworker()

    with pytest.raises(RuntimeError, match="precondition failed"):
        await sw.work(node_id="abc", sandbox=sandbox)
