"""ResearchRubrics canonical smoke — cohort of 3 (2 happy + 1 sad) against real E2B.

Per-run assertion dispatch on slot ``kind``:

- ``happy`` slots run the full happy-path assertion block (§2.5 of
  ``docs/superpowers/plans/test-refactor/02-drivers-and-asserts.md``).
- ``sad`` slot (slot 3) runs the sad-path block (§10) — line-cascade
  failure invariants.

Cohort-level: ``_assert_cohort_membership`` checks all 3 runs are
visible on ``/cohort/{key}``.  Playwright subprocess runs at the end
with a JSON-encoded cohort array so the shared factory can dispatch
per-kind assertions in the UI.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

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
    _assert_temporal_ordering,
    _assert_thread_messages_ordered,
    wait_for_terminal,
    wait_for_terminal_status,
)
from tests.e2e._submit import submit_cohort

ENV = "researchrubrics"
HAPPY_WORKER = f"{ENV}-smoke-worker"
SAD_WORKER = f"{ENV}-sadpath-smoke-worker"
CRITERION = f"{ENV}-smoke-criterion"
PER_RUN_TIMEOUT = 270  # seconds; < pytest's 300s --timeout


@dataclass(frozen=True)
class CohortSlot:
    worker_slug: str
    criterion_slug: str
    kind: Literal["happy", "sad"]


def _build_cohort() -> tuple[CohortSlot, ...]:
    """Build the cohort using the ``SMOKE_COHORT_SIZE`` env-var override.

    ``SMOKE_COHORT_SIZE`` controls the number of *happy* slots (default 2).
    One sad-path slot is always appended — every cohort must exercise the
    line-cascade failure path regardless of size.

    Size=1 → 1 happy + 1 sad.  Size=2 (default) → 2 happy + 1 sad.
    """
    size = int(os.environ.get("SMOKE_COHORT_SIZE", "2"))
    if size <= 0:
        raise ValueError(f"SMOKE_COHORT_SIZE must be >= 1, got {size}")

    slots: list[CohortSlot] = [CohortSlot(HAPPY_WORKER, CRITERION, "happy") for _ in range(size)]
    slots.append(CohortSlot(SAD_WORKER, CRITERION, "sad"))
    return tuple(slots)


COHORT: tuple[CohortSlot, ...] = _build_cohort()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_smoke_cohort(tmp_path: pathlib.Path) -> None:
    cohort_key = f"ci-smoke-{ENV}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    # ── Phase 1: submit the cohort (mixed worker slugs) ───────────────
    run_ids = await submit_cohort(
        benchmark_slug=ENV,
        slots=[(s.worker_slug, s.criterion_slug) for s in COHORT],
        cohort_key=cohort_key,
        timeout=PER_RUN_TIMEOUT,
    )
    assert len(run_ids) == len(COHORT)
    slotted: list[tuple[CohortSlot, uuid.UUID]] = list(zip(COHORT, run_ids))

    # ── Phase 2: wait for terminal state ──────────────────────────────
    await asyncio.gather(
        *(
            wait_for_terminal(rid, timeout_seconds=PER_RUN_TIMEOUT)
            if slot.kind == "happy"
            else wait_for_terminal_status(
                rid,
                expected_statuses=frozenset({"failed"}),
                timeout_seconds=PER_RUN_TIMEOUT,
            )
            for slot, rid in slotted
        ),
    )

    # ── Phase 3: per-run assertions (dispatched on kind) ──────────────
    for slot, rid in slotted:
        if slot.kind == "happy":
            _assert_happy_run(rid)
        else:
            _assert_sad_run(rid)

    # ── Phase 3b: cohort-level invariant ──────────────────────────────
    _assert_cohort_membership(cohort_key, run_ids)

    # ── Phase 4: Playwright subprocess (screenshots per run) ──────────
    _invoke_playwright(
        cohort_key=cohort_key,
        cohort=[{"run_id": str(rid), "kind": s.kind} for s, rid in slotted],
        screenshot_dir=tmp_path / "playwright",
    )

    # Phase 5 (finalizer) — see tests/e2e/conftest.py ``_screenshot_uploader``.


def _assert_happy_run(rid: uuid.UUID) -> None:
    _assert_run_graph(rid)
    _assert_run_resources(rid)
    _assert_run_turn_counts(rid)
    _assert_sandbox_command_wal(rid)
    _assert_sandbox_lifecycle_events(rid)
    _assert_thread_messages_ordered(rid)
    _assert_blob_roundtrip(rid)
    _assert_temporal_ordering(rid)
    _assert_run_evaluation(rid)
    # Env-specific content check is inside the criterion + also rerun here
    # via _assert_env_content_happy below.
    _assert_env_content_happy(rid)


def _assert_sad_run(rid: uuid.UUID) -> None:
    _assert_sadpath_graph_cascade(rid)
    _assert_sadpath_partial_artifact(rid)
    _assert_sadpath_partial_wal(rid)
    _assert_sadpath_thread_messages(rid)
    _assert_sadpath_evaluation(rid)
    _assert_sandbox_command_wal(rid)
    _assert_sandbox_lifecycle_events(rid)
    _assert_temporal_ordering(rid)


def _assert_env_content_happy(rid: uuid.UUID) -> None:
    """Out-of-band re-verification that each happy leaf produced a
    well-formed ``report_*.md``.  Duplicates what
    ``ResearchRubricsSmokeCriterion._verify_env_content`` does inside
    the workflow — if the criterion regresses silently, this catches it."""
    from pathlib import Path

    from sqlmodel import select

    from ergon_core.core.persistence.shared.db import get_session
    from ergon_core.core.persistence.telemetry.models import RunResource

    with get_session() as s:
        reports = list(
            s.exec(
                select(RunResource)
                .where(RunResource.run_id == rid)
                .where(
                    RunResource.name.like("report_%.md"),  # ty: ignore[unresolved-attribute]
                )
                .where(RunResource.kind == "report"),  # blob-store only (host-accessible)
            ).all(),
        )
    assert len(reports) == 9, f"expected 9 reports, got {len(reports)}"
    for r in reports:
        body = Path(r.file_path).read_bytes()
        assert body.startswith(b"# Research report"), (
            f"{r.name}: missing `# Research report` header"
        )
        assert len(body.strip()) >= 20, f"{r.name}: body < 20 bytes"


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
