"""Cohort submission helper for canonical smoke drivers.

POSTs ``/api/test/write/cohort`` on the api container; returns the
run_ids in the same order as the slots passed in.

Tests are a pure black-box client of the stack: they do not import any
ergon internals, do not call ``build_experiment`` / ``create_run`` /
``inngest.send`` in-process, and do not register worker / evaluator
slugs in the test process.  All of that lives inside the api container
(see ``tests.e2e._fixtures`` imported by ``app.py`` when
``ENABLE_TEST_HARNESS=1``).  Single source of truth for fixtures ⇒ no
host / container staleness risk.

Each slot can use a different ``(worker_slug, criterion_slug)`` pair —
used by the researchrubrics leg which has 2 happy + 1 sad slot.  Empty
slots list is valid (returns ``[]``) but unlikely in practice.
"""

from __future__ import annotations

import os
from uuid import UUID

import httpx

_DEFAULT_API = "http://127.0.0.1:9000"


def _api_base() -> str:
    return os.environ.get("ERGON_API_BASE_URL", _DEFAULT_API)


async def submit_cohort(
    *,
    benchmark_slug: str,
    slots: list[tuple[str, str]],
    cohort_key: str,
    timeout: int = 300,  # noqa: ARG001  # reserved — server-side per-run timeout
) -> list[UUID]:
    """Submit one run per slot under ``cohort_key``; return run_ids in order.

    Args:
        benchmark_slug:  e.g. ``"researchrubrics"``
        slots:           list of ``(worker_slug, criterion_slug)`` tuples
        cohort_key:      shared cohort name (all runs group under this)
        timeout:         reserved for future use; the api endpoint does
                         not block on run completion, so there is no
                         client-side timeout to propagate.
    """
    payload = {
        "benchmark_slug": benchmark_slug,
        "slots": [
            {"worker_slug": worker, "evaluator_slug": criterion} for worker, criterion in slots
        ],
        "cohort_key": cohort_key,
    }
    async with httpx.AsyncClient(base_url=_api_base(), timeout=30.0) as client:
        response = await client.post("/api/test/write/cohort", json=payload)
        response.raise_for_status()
        body = response.json()
    return [UUID(rid) for rid in body["run_ids"]]


__all__ = ["submit_cohort"]
