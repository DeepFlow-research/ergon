"""``MiniF2FSmokeCriterion._verify_sandbox_setup`` health probe."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from ergon_core.api.errors import CriterionCheckError
from tests.fixtures.smoke_components.criteria.minif2f_smoke import MiniF2FSmokeCriterion


def _crit() -> MiniF2FSmokeCriterion:
    return MiniF2FSmokeCriterion(slug="unit-test")


@pytest.mark.asyncio
async def test_sandbox_setup_passes_when_lean_compiles() -> None:
    ctx = MagicMock()
    ctx.has_runtime = True
    ctx.ensure_sandbox = AsyncMock(return_value=None)
    ctx.write_file = AsyncMock(return_value=None)
    ctx.run_command = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="", stderr=""),
    )

    await _crit()._verify_sandbox_setup(ctx)

    ctx.write_file.assert_awaited_once()
    path, content = ctx.write_file.await_args.args
    assert path == "/tmp/smoke_health.lean"
    assert b"theorem health_check" in content
    cmd = ctx.run_command.await_args.args[0]
    assert "lean --check" in cmd
    assert "|| true" not in cmd, (
        "criterion-side health probe must NOT soften exit code with `|| true` "
        "— that would defeat the point of this check"
    )


@pytest.mark.asyncio
async def test_sandbox_setup_raises_on_non_zero_lean_exit() -> None:
    ctx = MagicMock()
    ctx.has_runtime = True
    ctx.ensure_sandbox = AsyncMock(return_value=None)
    ctx.write_file = AsyncMock(return_value=None)
    ctx.run_command = AsyncMock(
        return_value=MagicMock(exit_code=1, stdout="error", stderr="expected 'by'"),
    )

    with pytest.raises(CriterionCheckError, match=r"minif2f sandbox health failed.*exit=1"):
        await _crit()._verify_sandbox_setup(ctx)


@pytest.mark.asyncio
async def test_sandbox_setup_raises_when_runtime_missing() -> None:
    ctx = MagicMock()
    ctx.has_runtime = False
    with pytest.raises(CriterionCheckError, match="CriterionRuntime not injected"):
        await _crit()._verify_sandbox_setup(ctx)
