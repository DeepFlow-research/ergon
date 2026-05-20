"""Job-local Inngest event sending helpers.

These helpers keep concrete Inngest client construction out of ``job.py``
modules while PR11 continues consolidating runtime persistence ownership.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ergon_core.core.infrastructure.inngest.client import InngestEvent, inngest_client

JobEvent = tuple[str, dict[str, Any]]


async def send_job_event(name: str, data: dict[str, Any]) -> None:
    await inngest_client.send(InngestEvent(name=name, data=data))


async def send_job_events(events: Iterable[JobEvent]) -> None:
    payload = [InngestEvent(name=name, data=data) for name, data in events]
    if payload:
        await inngest_client.send(payload)


async def send_job_step_event(ctx: Any, step_id: str, name: str, data: dict[str, Any]) -> None:
    """Send one durable step event without exposing Inngest event construction to jobs."""
    await ctx.step.send_event(step_id, InngestEvent(name=name, data=data))
