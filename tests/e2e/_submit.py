"""Cohort submission helper for canonical smoke drivers.

Submits N runs of a benchmark via the existing ``ergon benchmark run``
CLI, in parallel, all sharing one ``cohort_key``.  Returns the run_ids
in the same order as the slots passed in.

Each slot can use a different ``(worker_slug, criterion_slug)`` pair —
used by the researchrubrics leg which has 2 happy + 1 sad slot.  Empty
slots list is valid (returns ``[]``) but unlikely in practice.

Parses the run_id from the CLI's ``Run ID:   <uuid>`` line.  If the CLI
output format changes, grep for ``Run ID`` in
``ergon_cli/commands/benchmark.py`` and update the regex.
"""

from __future__ import annotations

import asyncio
import os
import re
from uuid import UUID

RUN_ID_RE = re.compile(r"Run ID:\s+([0-9a-f-]{36})")


async def _submit_one(
    *,
    benchmark_slug: str,
    worker_slug: str,
    criterion_slug: str,
    cohort_key: str,
    timeout: int = 300,
) -> UUID:
    """Launch one ``ergon benchmark run`` subprocess; return its run_id."""
    proc = await asyncio.create_subprocess_exec(
        "ergon",
        "benchmark",
        "run",
        benchmark_slug,
        "--worker",
        worker_slug,
        "--evaluator",
        criterion_slug,
        "--cohort",
        cohort_key,
        "--timeout",
        str(timeout),
        "--limit",
        "1",
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    match = RUN_ID_RE.search(stdout)
    if match is None:
        raise RuntimeError(
            "Could not parse run_id from CLI output. "
            f"exit={proc.returncode}\n"
            f"STDOUT:\n{stdout[-2000:]}\n"
            f"STDERR:\n{stderr[-2000:]}",
        )
    return UUID(match.group(1))


async def submit_cohort(
    *,
    benchmark_slug: str,
    slots: list[tuple[str, str]],
    cohort_key: str,
    timeout: int = 300,
) -> list[UUID]:
    """Submit one run per slot, all with the same ``cohort_key``.

    Returns run_ids in the same order as ``slots``.  Submissions happen
    in parallel via ``asyncio.gather``.

    Args:
        benchmark_slug:  e.g. ``"researchrubrics"``
        slots:           list of ``(worker_slug, criterion_slug)`` tuples
                         — one entry per cohort member
        cohort_key:      shared cohort string (all runs group under this)
        timeout:         per-run timeout seconds passed to the CLI
    """
    tasks = [
        _submit_one(
            benchmark_slug=benchmark_slug,
            worker_slug=worker_slug,
            criterion_slug=criterion_slug,
            cohort_key=cohort_key,
            timeout=timeout,
        )
        for worker_slug, criterion_slug in slots
    ]
    return list(await asyncio.gather(*tasks))


__all__ = ["submit_cohort"]
