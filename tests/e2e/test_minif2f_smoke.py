"""MiniF2F canonical smoke — cohort of 3 happy runs against real E2B.

No sad-path slot (researchrubrics leg carries that for the whole
matrix).  Structure identical to ``test_researchrubrics_smoke.py``.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import uuid
from datetime import datetime, timezone

import pytest

import tests.e2e._fixtures  # noqa: F401  (registration side-effect)
from tests.e2e._asserts import (
    _assert_blob_roundtrip,
    _assert_cohort_membership,
    _assert_run_evaluation,
    _assert_run_graph,
    _assert_run_resources,
    _assert_run_turn_counts,
    _assert_sandbox_command_wal,
    _assert_sandbox_lifecycle_events,
    _assert_temporal_ordering,
    _assert_thread_messages_ordered,
    wait_for_terminal,
)
from tests.e2e._submit import submit_cohort

ENV = "minif2f"
WORKER = f"{ENV}-smoke-worker"
CRITERION = f"{ENV}-smoke-criterion"
COHORT_SIZE = 3
PER_RUN_TIMEOUT = 270


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
        *(wait_for_terminal(rid, timeout_seconds=PER_RUN_TIMEOUT) for rid in run_ids),
    )

    for rid in run_ids:
        _assert_run_graph(rid)
        _assert_run_resources(rid)
        _assert_run_turn_counts(rid)
        _assert_sandbox_command_wal(rid)
        _assert_sandbox_lifecycle_events(rid)
        _assert_thread_messages_ordered(rid)
        _assert_blob_roundtrip(rid)
        _assert_temporal_ordering(rid)
        _assert_run_evaluation(rid)

    _assert_cohort_membership(cohort_key, run_ids)

    _invoke_playwright(
        cohort_key=cohort_key,
        cohort=[{"run_id": str(rid), "kind": "happy"} for rid in run_ids],
        screenshot_dir=tmp_path / "playwright",
    )


def _invoke_playwright(
    *,
    cohort_key: str,
    cohort: list[dict[str, str]],
    screenshot_dir: pathlib.Path,
) -> None:
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
                "http://127.0.0.1:3000",
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
