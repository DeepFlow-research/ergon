"""SWE-Bench Verified canonical happy/sad smoke cohort against real E2B."""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
from datetime import datetime, timezone

import pytest

from tests.e2e._asserts import (
    _assert_blob_roundtrip,
    _assert_cohort_membership,
    _assert_run_evaluation,
    _assert_run_graph,
    _assert_run_resources,
    _assert_run_turn_counts,
    _assert_sadpath_evaluation,
    _assert_sadpath_graph_cascade,
    _assert_sadpath_partial_artifact,
    _assert_sadpath_partial_wal,
    _assert_sadpath_thread_messages,
    _assert_sandbox_command_wal,
    _assert_sandbox_lifecycle_events,
    _assert_swebench_artifacts,
    _assert_thread_messages_ordered,
    _assert_temporal_ordering,
    wait_for_terminal_status,
)
from tests.e2e._submit import submit_cohort

# Benchmark slug is 'swebench-verified' (matches BENCHMARKS registry);
# worker + criterion slugs use 'swebench' (shorter).  The per-env
# Playwright spec file uses the benchmark slug so the CI matrix env id
# maps 1:1 to the spec filename.
ENV = "swebench-verified"
WORKER_PREFIX = "swebench"
HAPPY_WORKER = f"{WORKER_PREFIX}-smoke-worker"
SAD_WORKER = f"{WORKER_PREFIX}-sadpath-smoke-worker"
CRITERION = f"{WORKER_PREFIX}-smoke-criterion"
# ``SMOKE_COHORT_SIZE`` override for local/dev deep checks; CI uses default 1.
COHORT_SIZE = int(os.environ.get("SMOKE_COHORT_SIZE", "1"))
PER_RUN_TIMEOUT = 270
SmokeSlot = tuple[str, str, str]


def _smoke_slots(cohort_size: int) -> list[SmokeSlot]:
    return [
        slot
        for _ in range(cohort_size)
        for slot in (
            ("happy", HAPPY_WORKER, CRITERION),
            ("sad", SAD_WORKER, CRITERION),
        )
    ]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_smoke_cohort(tmp_path: pathlib.Path) -> None:
    cohort_key = f"ci-smoke-{ENV}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    smoke_slots = _smoke_slots(COHORT_SIZE)

    run_ids = await submit_cohort(
        benchmark_slug=ENV,
        slots=[(worker, criterion) for _, worker, criterion in smoke_slots],
        cohort_key=cohort_key,
        timeout=PER_RUN_TIMEOUT,
    )
    assert len(run_ids) == len(smoke_slots)

    await asyncio.gather(
        *(
            wait_for_terminal_status(
                rid,
                expected_statuses=frozenset({"completed"} if kind == "happy" else {"failed"}),
                timeout_seconds=PER_RUN_TIMEOUT,
            )
            for (kind, _, _), rid in zip(smoke_slots, run_ids, strict=True)
        ),
    )

    for (kind, _, _), rid in zip(smoke_slots, run_ids, strict=True):
        if kind == "happy":
            _assert_happy_run(rid)
        else:
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
        cohort=[
            {"run_id": str(rid), "kind": kind}
            for (kind, _, _), rid in zip(smoke_slots, run_ids, strict=True)
        ],
        screenshot_dir=screenshot_dir,
    )


def _assert_happy_run(rid) -> None:
    _assert_run_graph(rid)
    _assert_run_resources(rid)
    _assert_run_turn_counts(rid)
    _assert_thread_messages_ordered(rid)
    _assert_blob_roundtrip(rid)
    _assert_swebench_artifacts(rid)
    _assert_run_evaluation(rid)
    _assert_sandbox_lifecycle_events(rid)
    _assert_sandbox_command_wal(rid)
    _assert_temporal_ordering(rid)


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
