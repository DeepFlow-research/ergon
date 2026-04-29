"""``SweBenchSmokeCriterion._verify_sandbox_setup`` health probe."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from ergon_core.api.errors import CriterionCheckError
from tests.fixtures.smoke_components.criteria.swebench_smoke import SweBenchSmokeCriterion


def _crit() -> SweBenchSmokeCriterion:
    return SweBenchSmokeCriterion(slug="unit-test")


@pytest.mark.asyncio
async def test_sandbox_setup_passes_on_health_ok_marker() -> None:
    ctx = MagicMock()
    ctx.has_runtime = True
    ctx.ensure_sandbox = AsyncMock(return_value=None)
    ctx.write_file = AsyncMock(return_value=None)
    ctx.run_command = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="HEALTH_OK\n7.4.0\n", stderr=""),
    )

    await _crit()._verify_sandbox_setup(ctx)

    path, content = ctx.write_file.await_args.args
    assert path == "/tmp/smoke_health.py"
    assert b"HEALTH_OK" in content
    cmd = ctx.run_command.await_args.args[0]
    assert "python /tmp/smoke_health.py" in cmd
    assert "import pytest" in cmd


@pytest.mark.asyncio
async def test_sandbox_setup_raises_when_ok_marker_missing() -> None:
    """Exit 0 but no HEALTH_OK → command silently no-op'd."""
    ctx = MagicMock()
    ctx.has_runtime = True
    ctx.ensure_sandbox = AsyncMock(return_value=None)
    ctx.write_file = AsyncMock(return_value=None)
    ctx.run_command = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="something else", stderr=""),
    )

    with pytest.raises(CriterionCheckError, match="swebench sandbox health failed"):
        await _crit()._verify_sandbox_setup(ctx)


@pytest.mark.asyncio
async def test_sandbox_setup_raises_on_pytest_import_error() -> None:
    ctx = MagicMock()
    ctx.has_runtime = True
    ctx.ensure_sandbox = AsyncMock(return_value=None)
    ctx.write_file = AsyncMock(return_value=None)
    ctx.run_command = AsyncMock(
        return_value=MagicMock(
            exit_code=1,
            stdout="HEALTH_OK\n",
            stderr="ModuleNotFoundError: pytest",
        ),
    )

    with pytest.raises(CriterionCheckError, match=r"swebench sandbox health failed.*exit=1"):
        await _crit()._verify_sandbox_setup(ctx)


@pytest.mark.asyncio
async def test_sandbox_setup_raises_when_runtime_missing() -> None:
    ctx = MagicMock()
    ctx.has_runtime = False
    with pytest.raises(CriterionCheckError, match="CriterionRuntime not injected"):
        await _crit()._verify_sandbox_setup(ctx)
