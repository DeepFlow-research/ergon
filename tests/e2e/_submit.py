"""Experiment-group submission helper for canonical smoke drivers.

POSTs ``/api/__danger__/test-harness/write/experiment-runs`` on the api container; returns the
run_ids in the same order as the slots passed in.

Tests are a pure black-box client of the stack: they do not import any
ergon internals, do not call ``build_experiment`` / ``create_run`` /
``inngest.send`` in-process, and do not register worker / evaluator
slugs in the test process.  All of that lives inside the api container's
local composition target.  Single source of truth for fixtures ⇒ no host /
container staleness risk.

Each slot can use a different ``(worker_slug, criterion_slug)`` pair.
Empty slots list is valid (returns ``[]``) but unlikely in practice.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID

import httpx
import pytest

_DEFAULT_API = "http://127.0.0.1:9000"


def smoke_experiment_key(env: str) -> str:
    """Return a shared QA experiment key when provided, otherwise an env-scoped one."""
    override = os.environ.get("E2E_EXPERIMENT_KEY")
    if override is not None and override:
        return override
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"ci-smoke-{env}-{timestamp}"


def _api_base() -> str:
    return os.environ.get("ERGON_API_BASE_URL", _DEFAULT_API)


def build_experiment_payload(
    *,
    benchmark_slug: str,
    slots: list[tuple[str, str]],
    experiment: str,
    sandbox_slug: str,
    dependency_extras: tuple[str, ...],
    model: str = "openai:gpt-4o",
) -> dict:
    return {
        "benchmark_slug": benchmark_slug,
        "slots": [
            {"worker_slug": worker, "evaluator_slug": criterion} for worker, criterion in slots
        ],
        "experiment": experiment,
        "sandbox_slug": sandbox_slug,
        "dependency_extras": list(dependency_extras),
        "model": model,
    }


async def submit_experiment_runs(
    *,
    benchmark_slug: str,
    slots: list[tuple[str, str]],
    experiment: str,
    sandbox_slug: str,
    dependency_extras: tuple[str, ...],
    model: str = "openai:gpt-4o",
    timeout: int = 300,  # reserved — server-side per-run timeout
) -> list[UUID]:
    """Submit one run per slot under ``experiment``; return run_ids in order.

    Args:
        benchmark_slug:  e.g. ``"researchrubrics"``
        slots:           list of ``(worker_slug, criterion_slug)`` tuples
        experiment:      shared experiment tag (all runs group under this)
        sandbox_slug:    explicit sandbox manager slug for the run
        dependency_extras: explicit dependency intent; smoke uses ``("none",)``
        model:           explicit model target used by the test harness
        timeout:         reserved for future use; the api endpoint does
                         not block on run completion, so there is no
                         client-side timeout to propagate.
    """
    payload = build_experiment_payload(
        benchmark_slug=benchmark_slug,
        slots=slots,
        experiment=experiment,
        sandbox_slug=sandbox_slug,
        dependency_extras=dependency_extras,
        model=model,
    )
    async with httpx.AsyncClient(base_url=_api_base(), timeout=30.0) as client:
        response = await client.post(
            "/api/__danger__/test-harness/write/experiment-runs", json=payload
        )
        if response.status_code >= 400:
            pytest.fail(
                "experiment-run submission failed: "
                f"{response.status_code} {response.reason_phrase} "
                f"for {response.request.url}\n"
                f"response body:\n{response.text[:4000]}",
            )
        body = response.json()
    return [UUID(rid) for rid in body["run_ids"]]


__all__ = ["build_experiment_payload", "smoke_experiment_key", "submit_experiment_runs"]
