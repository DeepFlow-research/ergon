"""Observation output helpers for getting-started examples."""

import os
from collections.abc import Mapping
from uuid import UUID


def dashboard_run_url(run_id: UUID, environ: Mapping[str, str] | None = None) -> str | None:
    """Build a dashboard run URL when the dashboard base URL is configured."""
    source = environ if environ is not None else os.environ
    base_url = source.get("ERGON_DASHBOARD_URL")
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/run/{run_id}"


def cli_status_command(run_id: UUID) -> str:
    """Build the CLI command for checking a run's status."""
    return f"uv run ergon run status {run_id}"
