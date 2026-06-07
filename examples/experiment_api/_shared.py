"""Shared helpers for experiment API examples."""

from __future__ import annotations

from ergon_core.core.persistence.shared.db import ensure_db


def prepare_experiment_runtime() -> None:
    """Prepare persistence before examples submit through the public API."""
    ensure_db()
