"""Step output models for infrastructure inngest functions.

These are service contracts for step.run return types - they define
the shape of data passed between steps within a single Inngest function.
"""

from pydantic import BaseModel


class TerminateSandboxResult(BaseModel):
    """Result of terminate-sandbox step."""

    success: bool
    run_id: str
    sandbox_terminated: bool = False
    sandbox_id: str | None = None
    error: str | None = None
    message: str | None = None


class VerifyRunStatusResult(BaseModel):
    """Result of verify-run-status step."""

    status_updated: bool = False
    status_verified: bool = False
    old_status: str | None = None
    new_status: str | None = None
    status: str | None = None
    error: str | None = None
