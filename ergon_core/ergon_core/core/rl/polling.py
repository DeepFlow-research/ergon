"""DB polling utilities for waiting on episode completion.

Used by the TRL ``rollout_func`` adapter to wait for Inngest-orchestrated
episodes to finish before reading their results.
"""

import logging
import time
from typing import Callable
from uuid import UUID

from sqlmodel import Session, select

from ergon_core.core.persistence.shared.enums import TERMINAL_RUN_STATUSES
from ergon_core.core.persistence.telemetry.models import RunRecord

logger = logging.getLogger(__name__)


class PollTimeoutError(Exception):
    """Raised when polling exceeds the configured timeout."""

    def __init__(self, run_ids: list[UUID], elapsed_s: float):
        self.run_ids = run_ids
        self.elapsed_s = elapsed_s
        super().__init__(f"Timed out waiting for {len(run_ids)} run(s) after {elapsed_s:.1f}s")


def poll_until_all_complete(
    session_factory: Callable[[], Session],
    run_ids: list[UUID],
    *,
    timeout_s: float = 300.0,
    poll_interval_s: float = 1.0,
) -> dict[UUID, str]:
    """Block until all runs reach a terminal status.

    Args:
        session_factory: callable returning a new ``Session`` (e.g. ``get_session``).
        run_ids: list of ``RunRecord.id`` values to wait for.
        timeout_s: maximum wall-clock time to wait.
        poll_interval_s: sleep between polls.

    Returns:
        Mapping of ``run_id -> terminal status`` for every run.

    Raises:
        PollTimeoutError: if any run is still non-terminal after *timeout_s*.
    """
    terminal = set(TERMINAL_RUN_STATUSES)
    remaining = set(run_ids)
    results: dict[UUID, str] = {}
    start = time.monotonic()

    while remaining:
        elapsed = time.monotonic() - start
        if elapsed > timeout_s:
            raise PollTimeoutError(list(remaining), elapsed)

        with session_factory() as session:
            rows = list(
                session.exec(
                    select(RunRecord).where(RunRecord.id.in_(list(remaining)))  # type: ignore[union-attr]
                ).all()
            )
            for run in rows:
                if run.status in terminal:
                    results[run.id] = run.status
                    remaining.discard(run.id)

        if remaining:
            logger.debug(
                "Polling: %d/%d complete (%.0fs elapsed)",
                len(results),
                len(run_ids),
                elapsed,
            )
            time.sleep(poll_interval_s)

    return results
