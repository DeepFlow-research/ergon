"""``ResearchRubricsSmokeCriterion`` env-specific hooks.

- ``_verify_env_content`` reads report_*.md and checks shape.
- ``_verify_sandbox_setup`` runs a bash probe via ``context.runtime``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from ergon_core.api.errors import CriterionCheckError
from tests.fixtures.smoke_components.criteria.researchrubrics_smoke import (
    ResearchRubricsSmokeCriterion,
)


def _crit() -> ResearchRubricsSmokeCriterion:
    return ResearchRubricsSmokeCriterion(slug="unit-test")


# =============================================================================
# _verify_sandbox_setup
# =============================================================================


@pytest.mark.asyncio
async def test_verify_sandbox_setup_passes_on_ok_output() -> None:
    ctx = MagicMock()
    ctx.has_runtime = True
    ctx.ensure_sandbox = AsyncMock(return_value=None)
    ctx.run_command = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="OK\n"),
    )

    await _crit()._verify_sandbox_setup(ctx)

    ctx.ensure_sandbox.assert_awaited_once()
    ctx.run_command.assert_awaited_once()
    cmd = ctx.run_command.await_args.args[0]
    assert "wc -l" in cmd
    assert "/tmp/smoke_health.md" in cmd


@pytest.mark.asyncio
async def test_verify_sandbox_setup_raises_when_runtime_missing() -> None:
    ctx = MagicMock()
    ctx.has_runtime = False
    with pytest.raises(CriterionCheckError, match="CriterionRuntime not injected"):
        await _crit()._verify_sandbox_setup(ctx)


@pytest.mark.asyncio
async def test_verify_sandbox_setup_raises_on_non_zero_exit() -> None:
    ctx = MagicMock()
    ctx.has_runtime = True
    ctx.ensure_sandbox = AsyncMock(return_value=None)
    ctx.run_command = AsyncMock(
        return_value=MagicMock(exit_code=1, stdout=""),
    )
    with pytest.raises(CriterionCheckError, match=r"researchrubrics sandbox health failed.*exit=1"):
        await _crit()._verify_sandbox_setup(ctx)


@pytest.mark.asyncio
async def test_verify_sandbox_setup_raises_when_ok_marker_missing() -> None:
    """Command exited 0 but didn't print OK — toolchain may have
    silently no-op'd.  Treat as failure."""
    ctx = MagicMock()
    ctx.has_runtime = True
    ctx.ensure_sandbox = AsyncMock(return_value=None)
    ctx.run_command = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="nope"),
    )
    with pytest.raises(CriterionCheckError, match="researchrubrics sandbox health failed"):
        await _crit()._verify_sandbox_setup(ctx)
