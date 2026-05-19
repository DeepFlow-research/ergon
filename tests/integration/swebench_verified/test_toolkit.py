"""Tests for the SWE-Bench toolkit (bash + str-replace editor)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit


@pytest.mark.asyncio
async def test_bash_tool_runs_command_in_workdir() -> None:
    sandbox = AsyncMock()
    sandbox.run_command = AsyncMock(
        return_value=SimpleNamespace(exit_code=0, stdout="hello\n", stderr="")
    )
    tk = SWEBenchToolkit(repo_root="/workspace/repo")

    tool = next(t for t in tk.tools(sandbox, task=SimpleNamespace()) if t.name == "bash")
    response = await tool.function(command="echo hello")

    assert response.exit_code == 0
    assert "hello" in response.stdout
    invoked = sandbox.run_command.call_args.args[0]
    assert "/workspace/repo" in invoked


@pytest.mark.asyncio
async def test_str_replace_editor_view_reads_file() -> None:
    sandbox = AsyncMock()
    sandbox.read_file = AsyncMock(return_value=b"def foo():\n    return 1\n")
    tk = SWEBenchToolkit(repo_root="/workspace/repo")

    tool = next(
        t for t in tk.tools(sandbox, task=SimpleNamespace()) if t.name == "str_replace_editor"
    )
    response = await tool.function(command="view", path="src/foo.py")

    assert "def foo" in response.output
    sandbox.read_file.assert_awaited_with("/workspace/repo/src/foo.py")


@pytest.mark.asyncio
async def test_str_replace_editor_replace_updates_file() -> None:
    sandbox = AsyncMock()
    sandbox.read_file = AsyncMock(return_value=b"def foo():\n    return 1\n")
    sandbox.write_file = AsyncMock()
    tk = SWEBenchToolkit(repo_root="/workspace/repo")

    tool = next(
        t for t in tk.tools(sandbox, task=SimpleNamespace()) if t.name == "str_replace_editor"
    )
    response = await tool.function(
        command="str_replace",
        path="src/foo.py",
        old_str="    return 1",
        new_str="    return 2",
    )

    assert response.ok is True
    sandbox.write_file.assert_awaited()
    written_path, written_bytes = sandbox.write_file.call_args.args
    assert written_path == "/workspace/repo/src/foo.py"
    assert b"return 2" in written_bytes


@pytest.mark.asyncio
async def test_str_replace_editor_replace_fails_when_old_str_not_unique() -> None:
    sandbox = AsyncMock()
    sandbox.read_file = AsyncMock(return_value=b"x = 1\nx = 1\n")
    tk = SWEBenchToolkit(repo_root="/workspace/repo")

    tool = next(
        t for t in tk.tools(sandbox, task=SimpleNamespace()) if t.name == "str_replace_editor"
    )
    response = await tool.function(
        command="str_replace", path="x.py", old_str="x = 1", new_str="x = 2"
    )

    assert response.ok is False
    assert "not unique" in response.error.lower()
