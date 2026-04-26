"""ResearchRubrics canonical sad-path smoke against real E2B.

Per-run assertion dispatch on slot ``kind``:

- The single slot routes ``l_2`` to a failing leaf.
- ``l_3`` depends on ``l_2`` and must remain blocked / unstarted.
- Independent branches must still complete.

Cohort-level: ``_assert_cohort_membership`` checks all submitted runs
are visible on ``/cohort/{key}``.  Playwright subprocess runs at the
end with a JSON-encoded cohort array so the shared factory can dispatch
per-kind assertions in the UI.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
from datetime import datetime, timezone

import pytest

from tests.e2e._asserts import (
    _assert_cohort_membership,
    _assert_sadpath_evaluation,
    _assert_sadpath_graph_cascade,
    _assert_sadpath_partial_artifact,
    _assert_sadpath_partial_wal,
    _assert_sadpath_thread_messages,
    _assert_sandbox_command_wal,
    _assert_sandbox_lifecycle_events,
    _assert_temporal_ordering,
    wait_for_terminal_status,
)
from tests.e2e._submit import submit_cohort

ENV = "researchrubrics"
WORKER = f"{ENV}-sadpath-smoke-worker"
CRITERION = f"{ENV}-smoke-criterion"
PER_RUN_TIMEOUT = 270  # seconds; < pytest's 300s --timeout


COHORT_SIZE = int(os.environ.get("SMOKE_COHORT_SIZE", "1"))


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_smoke_cohort(tmp_path: pathlib.Path) -> None:
    cohort_key = f"ci-smoke-{ENV}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    run_ids = await submit_cohort(
        benchmark_slug=ENV,
        slots=[(WORKER, CRITERION)] * COHORT_SIZE,
        cohort_key=cohort_key,
        timeout=PER_RUN_TIMEOUT,
    )
    assert len(run_ids) == COHORT_SIZE

    await asyncio.gather(
        *(
            wait_for_terminal_status(
                rid,
                expected_statuses=frozenset({"failed"}),
                timeout_seconds=PER_RUN_TIMEOUT,
            )
            for rid in run_ids
        ),
    )

    for rid in run_ids:
        _assert_sad_run(rid)

    _assert_cohort_membership(cohort_key, run_ids)

    screenshot_dir_env = os.environ.get("SCREENSHOT_DIR")
    screenshot_dir = (
        pathlib.Path(screenshot_dir_env)
        if screenshot_dir_env is not None
        else tmp_path / "playwright"
    )
    _invoke_playwright(
        cohort_key=cohort_key,
        cohort=[{"run_id": str(rid), "kind": "sad"} for rid in run_ids],
        screenshot_dir=screenshot_dir,
    )


def _assert_sad_run(rid) -> None:
    _assert_sadpath_graph_cascade(rid)
    _assert_sadpath_partial_artifact(rid)
    _assert_sadpath_partial_wal(rid)
    _assert_sadpath_thread_messages(rid)
    _assert_sadpath_evaluation(rid)
    _assert_sandbox_lifecycle_events(rid)
    _assert_sandbox_command_wal(rid)
    _assert_temporal_ordering(rid)


def _invoke_playwright(
    *,
    cohort_key: str,
    cohort: list[dict[str, str]],
    screenshot_dir: pathlib.Path,
) -> None:
    """Launch the researchrubrics smoke Playwright spec as a subprocess.

    Passes cohort state via env vars: JSON-encoded cohort list so the
    shared factory can dispatch per-kind assertions.  Always runs (even
    when phase-3 assertions failed) so the dashboard state at time of
    failure is captured.
    """
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "pnpm",
            "--dir",
            "ergon-dashboard",
            "exec",
            "playwright",
            "test",
            f"tests/e2e/{ENV}.smoke.spec.ts",
            "--project=chromium",
        ],
        env={
            **os.environ,
            "COHORT_KEY": cohort_key,
            "SMOKE_ENV": ENV,
            "SMOKE_COHORT_JSON": json.dumps(cohort),
            "SCREENSHOT_DIR": str(screenshot_dir),
            "PLAYWRIGHT_LIVE": "1",
            "PLAYWRIGHT_BASE_URL": os.environ.get(
                "PLAYWRIGHT_BASE_URL",
                "http://127.0.0.1:3001",
            ),
            "ERGON_API_BASE_URL": os.environ.get(
                "ERGON_API_BASE_URL",
                "http://127.0.0.1:9000",
            ),
            "TEST_HARNESS_SECRET": os.environ["TEST_HARNESS_SECRET"],
        },
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"playwright spec failed (returncode={result.returncode})")
