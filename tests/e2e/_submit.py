"""Cohort submission helper for canonical smoke drivers.

In-process submission: builds the experiment graph, persists it, creates
a ``RunRecord``, and emits ``WorkflowStartedEvent`` via Inngest — all
without spawning an external ``ergon benchmark run`` subprocess.

Historically this shelled out to the CLI so the test orchestrator could
live on the host and talk to a dockerised backend.  That layout needed
the smoke ``WORKERS`` / ``EVALUATORS`` to be registered in *every*
process that might resolve a worker slug (the CLI's process *and* the
api container's Inngest worker).  Moving pytest into the api container
(see Dockerfile + docker-compose) means both halves run in the same
interpreter, so direct service calls are sufficient and cheaper.

Each slot can use a different ``(worker_slug, criterion_slug)`` pair —
used by the researchrubrics leg which has 2 happy + 1 sad slot.  Empty
slots list is valid (returns ``[]``) but unlikely in practice.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import inngest
from ergon_cli.composition import build_experiment
from ergon_core.core.runtime.events.task_events import WorkflowStartedEvent
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.cohort_service import experiment_cohort_service
from ergon_core.core.runtime.services.run_service import create_run

# Default model passed into ``build_experiment``.  Smoke workers do not
# call an LLM — the field is only there because the production CLI arg
# requires it.  Matches the CLI default (``ergon_cli.main``).
_SMOKE_MODEL = "openai:gpt-4o"


async def _submit_one(
    *,
    benchmark_slug: str,
    worker_slug: str,
    criterion_slug: str,
    cohort_key: str,
    timeout: int = 300,  # noqa: ARG001  # kept for backward-compat signature
) -> UUID:
    """Build + persist + dispatch one smoke run; return its run_id."""
    experiment = build_experiment(
        benchmark_slug=benchmark_slug,
        model=_SMOKE_MODEL,
        worker_slug=worker_slug,
        evaluator_slug=criterion_slug,
        limit=1,
    )
    experiment.validate()
    persisted = experiment.persist()

    cohort = experiment_cohort_service.resolve_or_create(
        name=cohort_key,
        description=f"smoke cohort: {benchmark_slug} / {worker_slug} / {criterion_slug}",
        created_by="smoke-test",
    )
    run = create_run(persisted, cohort_id=cohort.id)

    event = WorkflowStartedEvent(
        run_id=run.id,
        definition_id=persisted.definition_id,
    )
    await inngest_client.send(
        inngest.Event(
            name=WorkflowStartedEvent.name,
            data=event.model_dump(mode="json"),
        )
    )
    return run.id


async def submit_cohort(
    *,
    benchmark_slug: str,
    slots: list[tuple[str, str]],
    cohort_key: str,
    timeout: int = 300,
) -> list[UUID]:
    """Submit one run per slot, all sharing ``cohort_key``.

    Returns run_ids in the same order as ``slots``.  Dispatch happens in
    parallel via ``asyncio.gather``.

    Args:
        benchmark_slug:  e.g. ``"researchrubrics"``
        slots:           list of ``(worker_slug, criterion_slug)`` tuples
                         — one entry per cohort member
        cohort_key:      shared cohort string (all runs group under this)
        timeout:         per-run timeout seconds (reserved for future use)
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
