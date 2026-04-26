"""Runtime-facing sandbox lifecycle helpers."""

from __future__ import annotations

import logging
from enum import StrEnum

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SandboxTerminationReason(StrEnum):
    TERMINATED = "terminated"
    NOT_FOUND_OR_ALREADY_CLOSED = "not_found_or_already_closed"
    MISSING_ID = "missing_id"
    ERROR = "error"


class SandboxTerminationResult(BaseModel):
    sandbox_id: str | None
    terminated: bool
    reason: SandboxTerminationReason


async def terminate_sandbox_by_id(sandbox_id: str | None) -> SandboxTerminationResult:
    """Terminate a sandbox behind a single runtime-facing boundary."""
    if sandbox_id is None:
        return SandboxTerminationResult(
            sandbox_id=None,
            terminated=False,
            reason=SandboxTerminationReason.MISSING_ID,
        )

    try:
        from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

        terminated = await BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.error("Failed to terminate sandbox %s", sandbox_id, exc_info=True)
        return SandboxTerminationResult(
            sandbox_id=sandbox_id,
            terminated=False,
            reason=SandboxTerminationReason.ERROR,
        )

    return SandboxTerminationResult(
        sandbox_id=sandbox_id,
        terminated=terminated,
        reason=(
            SandboxTerminationReason.TERMINATED
            if terminated
            else SandboxTerminationReason.NOT_FOUND_OR_ALREADY_CLOSED
        ),
    )
