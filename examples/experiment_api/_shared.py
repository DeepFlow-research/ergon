"""Shared helpers for experiment API examples."""

from __future__ import annotations

from ergon_core.core.application.experiments.submission import ExperimentSubmissionService
from ergon_core.core.persistence.shared.db import ensure_db, get_session


def experiment_submission_service() -> ExperimentSubmissionService:
    """Create the concrete submission service used by example scripts."""
    ensure_db()
    return ExperimentSubmissionService.for_session(get_session())
