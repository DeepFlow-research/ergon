"""Tests for the SWE-Bench toolkit (bash + str-replace editor)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit


@pytest.mark.asyncio
async def test_bash_tool_runs_command_in_workdir() -> None:
    sandbox = AsyncMock()
    sandbox.commands.run = AsyncMock(
        return_value=SimpleNamespace(exit_code=0, stdout="hello\n", stderr="")
    )
    tk = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")

    tool = next(t for t in tk.get_tools() if t.name == "bash")
    response = await tool.function(command="echo hello")

    assert response.exit_code == 0
    assert "hello" in response.stdout
    invoked = sandbox.commands.run.call_args.args[0]
    assert "/workspace/repo" in invoked


@pytest.mark.asyncio
async def test_str_replace_editor_view_reads_file() -> None:
    sandbox = AsyncMock()
    sandbox.files.read = AsyncMock(return_value="def foo():\n    return 1\n")
    tk = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")

    tool = next(t for t in tk.get_tools() if t.name == "str_replace_editor")
    response = await tool.function(command="view", path="src/foo.py")

    assert "def foo" in response.output
    sandbox.files.read.assert_awaited_with("/workspace/repo/src/foo.py")


@pytest.mark.asyncio
async def test_str_replace_editor_replace_updates_file() -> None:
    sandbox = AsyncMock()
    sandbox.files.read = AsyncMock(return_value="def foo():\n    return 1\n")
    sandbox.files.write = AsyncMock()
    tk = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")

    tool = next(t for t in tk.get_tools() if t.name == "str_replace_editor")
    response = await tool.function(
        command="str_replace",
        path="src/foo.py",
        old_str="    return 1",
        new_str="    return 2",
    )

    assert response.ok is True
    sandbox.files.write.assert_awaited()
    written_path, written_bytes = sandbox.files.write.call_args.args
    assert written_path == "/workspace/repo/src/foo.py"
    assert b"return 2" in written_bytes


@pytest.mark.asyncio
async def test_str_replace_editor_replace_fails_when_old_str_not_unique() -> None:
    sandbox = AsyncMock()
    sandbox.files.read = AsyncMock(return_value="x = 1\nx = 1\n")
    tk = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")

    tool = next(t for t in tk.get_tools() if t.name == "str_replace_editor")
    response = await tool.function(
        command="str_replace", path="x.py", old_str="x = 1", new_str="x = 2"
    )

    assert response.ok is False
    assert "not unique" in response.error.lower()
