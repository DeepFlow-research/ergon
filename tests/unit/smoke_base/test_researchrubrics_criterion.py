"""``ResearchRubricsSmokeCriterion`` env-specific hooks.

- ``_verify_env_content`` reads report_*.md and checks shape.
- ``_verify_sandbox_setup`` runs a bash probe via ``context.runtime``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ergon_core.api.errors import CriteriaCheckError
from tests.e2e._fixtures.criteria.researchrubrics_smoke import (
    ResearchRubricsSmokeCriterion,
)


def _crit() -> ResearchRubricsSmokeCriterion:
    return ResearchRubricsSmokeCriterion(name="unit-test")


# =============================================================================
# _verify_sandbox_setup
# =============================================================================


@pytest.mark.asyncio
async def test_verify_sandbox_setup_passes_on_ok_output() -> None:
    ctx = MagicMock()
    ctx.runtime = MagicMock()
    ctx.runtime.ensure_sandbox = AsyncMock(return_value=None)
    ctx.runtime.run_command = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="OK\n"),
    )

    await _crit()._verify_sandbox_setup(ctx)

    ctx.runtime.ensure_sandbox.assert_awaited_once()
    ctx.runtime.run_command.assert_awaited_once()
    cmd = ctx.runtime.run_command.await_args.args[0]
    assert "wc -l" in cmd
    assert "/tmp/smoke_health.md" in cmd


@pytest.mark.asyncio
async def test_verify_sandbox_setup_raises_when_runtime_missing() -> None:
    ctx = MagicMock()
    ctx.runtime = None
    with pytest.raises(CriteriaCheckError, match="CriterionRuntime not injected"):
        await _crit()._verify_sandbox_setup(ctx)


@pytest.mark.asyncio
async def test_verify_sandbox_setup_raises_on_non_zero_exit() -> None:
    ctx = MagicMock()
    ctx.runtime = MagicMock()
    ctx.runtime.ensure_sandbox = AsyncMock(return_value=None)
    ctx.runtime.run_command = AsyncMock(
        return_value=MagicMock(exit_code=1, stdout=""),
    )
    with pytest.raises(CriteriaCheckError, match=r"researchrubrics sandbox health failed.*exit=1"):
        await _crit()._verify_sandbox_setup(ctx)


@pytest.mark.asyncio
async def test_verify_sandbox_setup_raises_when_ok_marker_missing() -> None:
    """Command exited 0 but didn't print OK — toolchain may have
    silently no-op'd.  Treat as failure."""
    ctx = MagicMock()
    ctx.runtime = MagicMock()
    ctx.runtime.ensure_sandbox = AsyncMock(return_value=None)
    ctx.runtime.run_command = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="nope"),
    )
    with pytest.raises(CriteriaCheckError, match="researchrubrics sandbox health failed"):
        await _crit()._verify_sandbox_setup(ctx)
