"""Result types for infrastructure Inngest functions.

These are the typed return values for infrastructure-related Inngest functions.
"""

from uuid import UUID

from pydantic import BaseModel


class RunCleanupResult(BaseModel):
    """Result of run_cleanup function."""

    run_id: UUID
    status: str
    sandbox_terminated: bool
    sandbox_id: str | None = None
    error: str | None = None


class TerminateSandboxResult(BaseModel):
    """Result of terminate-sandbox step (internal)."""

    success: bool
    run_id: str
    sandbox_terminated: bool = False
    sandbox_id: str | None = None
    error: str | None = None
    message: str | None = None
