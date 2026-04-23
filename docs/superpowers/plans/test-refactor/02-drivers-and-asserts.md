# 02 — Pytest drivers + per-env Postgres assertions

**Status:** draft
**Scope:** three `tests/e2e/test_{env}_smoke.py` files. How they submit, how they wait, exactly what they assert on Postgres, and where Playwright is invoked.

Cross-refs: shared fixtures in [`01-fixtures.md`](01-fixtures.md); Playwright spec shape in [`03-dashboard-and-playwright.md`](03-dashboard-and-playwright.md).

---

## 1. Driver template (shared shape, 3 files)

Every `test_{env}_smoke.py` follows this shape. Each driver defines a **cohort recipe** — a list of `(worker_slug, criterion_slug, kind)` per cohort slot. Minif2f + swebench-verified pass 3 × `"happy"`; researchrubrics passes 2 × `"happy"` + 1 × `"sad"`. The per-run assertion loop dispatches on `kind`.

```python
# tests/e2e/test_researchrubrics_smoke.py
"""Researchrubrics canonical smoke — 3-run cohort (2 happy + 1 sad) against real E2B."""

from __future__ import annotations

import asyncio
import os
import pathlib
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import pytest
from sqlmodel import select

import tests.e2e._fixtures  # noqa: F401  (registration hook)

from ergon_cli.submit import submit_cohort
from ergon_core.core.persistence.graph.models import RunGraphNode, RunGraphMutation
from ergon_core.core.persistence.resources.models import RunResource
from ergon_core.core.persistence.evaluation.models import RunTaskEvaluation
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.graph.status_conventions import COMPLETED

from tests.e2e._fixtures.smoke_base.constants import EXPECTED_SUBTASK_SLUGS

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


# Researchrubrics cohort: 2 happy + 1 sad. MiniF2F and SWE-bench drivers
# pass 3 × CohortSlot(HAPPY_WORKER, CRITERION, "happy").
COHORT: tuple[CohortSlot, ...] = (
    CohortSlot(HAPPY_WORKER, CRITERION, "happy"),
    CohortSlot(HAPPY_WORKER, CRITERION, "happy"),
    CohortSlot(SAD_WORKER,   CRITERION, "sad"),
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_smoke_cohort(tmp_path: pathlib.Path) -> None:
    cohort_key = f"ci-smoke-{ENV}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    # ── Phase 1: submit the cohort (may be mixed worker slugs) ─────────
    run_ids: list[uuid.UUID] = await submit_cohort(
        benchmark_slug=ENV,
        slots=[(s.worker_slug, s.criterion_slug) for s in COHORT],
        cohort_key=cohort_key,
    )
    assert len(run_ids) == len(COHORT)

    # Pair each run_id with the slot that submitted it (preserves order).
    slotted: list[tuple[CohortSlot, uuid.UUID]] = list(zip(COHORT, run_ids))

    # ── Phase 2: wait for terminal state ───────────────────────────────
    await asyncio.gather(*(
        wait_for_terminal(rid, timeout_seconds=PER_RUN_TIMEOUT) for rid in run_ids
    ))

    # ── Phase 3: Postgres assertions (per run, dispatched on kind) ─────
    for slot, rid in slotted:
        if slot.kind == "happy":
            _assert_happy_run(rid)
        else:
            _assert_sad_run(rid)

    # ── Phase 3b: cohort-level invariant (works for any mix) ───────────
    _assert_cohort_membership(cohort_key, run_ids)

    # ── Phase 4: Playwright subprocess (screenshots per run) ───────────
    _invoke_playwright(
        env=ENV,
        cohort_key=cohort_key,
        cohort=[
            {"run_id": str(rid), "kind": slot.kind}
            for slot, rid in slotted
        ],
        screenshot_dir=tmp_path / "playwright",
    )

    # Phase 5 (finalizer) is attached via fixture; see §4.


def _assert_happy_run(rid: uuid.UUID) -> None:
    _assert_run_graph(rid)
    _assert_run_resources(rid)
    _assert_run_turn_counts(rid)                 # incremental turn persistence
    _assert_sandbox_command_wal(rid)             # §2.5a — bash cmds land in WAL
    _assert_sandbox_lifecycle_events(rid)        # §2.5b — created/command/closed
    _assert_thread_messages_ordered(rid)         # §2.5c — 9 per-leaf completion msgs
    _assert_blob_roundtrip(rid)                  # §2.5d — bytes-in == bytes-out
    _assert_temporal_ordering(rid)               # §2.5e — DAG deps honoured in time
    _assert_run_evaluation(rid)
    _assert_env_content(rid)                     # per-env extension; §3


def _assert_sad_run(rid: uuid.UUID) -> None:
    # Sad-path-specific invariants (§10)
    _assert_sadpath_graph_cascade(rid)
    _assert_sadpath_partial_artifact(rid)
    _assert_sadpath_partial_wal(rid)
    _assert_sadpath_thread_messages(rid)         # 8 msgs (l_2 missing)
    _assert_sadpath_evaluation(rid)
    # Shared helpers that still apply on the sad path:
    _assert_sandbox_command_wal(rid)
    _assert_sandbox_lifecycle_events(rid)        # 9 created / 9 closed (l_3 never provisioned)
    _assert_temporal_ordering(rid)               # only edges whose child reached "started" state
```

The driver is intentionally boring. All structural assertions live in the named helpers below; `kind`-dispatch keeps happy and sad run invariants cleanly separated. **MiniF2F + SWE-bench drivers are the same file with `COHORT = (CohortSlot(HAPPY_WORKER, CRITERION, "happy"),) * 3`** — no sad slot.

---

## 2. Shared assertion helpers (used by all 3 envs)

Live in `tests/e2e/_asserts.py` (not under `_fixtures/`; these helpers are test-side, not registry-side).

### 2.1 `_assert_run_graph(run_id)` — graph shape + completion

```python
def _assert_run_graph(run_id: UUID) -> None:
    with get_session() as s:
        nodes = s.exec(
            select(RunGraphNode)
            .where(RunGraphNode.run_id == run_id)
            .order_by(RunGraphNode.depth, RunGraphNode.task_slug),
        ).all()

    # 1 root + 9 subtasks = 10 total nodes
    assert len(nodes) == 10, f"expected 10 nodes, got {len(nodes)}"
    root = next(n for n in nodes if n.depth == 0)
    leaves = [n for n in nodes if n.depth > 0]
    assert len(leaves) == 9
    assert sorted(n.task_slug for n in leaves) == sorted(EXPECTED_SUBTASK_SLUGS)
    assert all(n.status == COMPLETED for n in nodes), \
        f"non-completed nodes: {[(n.task_slug, n.status) for n in nodes if n.status != COMPLETED]}"
    assert root.status == COMPLETED

    # Structural dep check: d_join depends on d_left + d_right; l_3 depends on l_2.
    by_slug = {n.task_slug: n for n in leaves}
    _assert_deps(by_slug, "d_join",  {"d_left", "d_right"})
    _assert_deps(by_slug, "d_left",  {"d_root"})
    _assert_deps(by_slug, "d_right", {"d_root"})
    _assert_deps(by_slug, "l_2",     {"l_1"})
    _assert_deps(by_slug, "l_3",     {"l_2"})
    for roots in ("d_root", "l_1", "s_a", "s_b"):
        _assert_deps(by_slug, roots, set())
```

`_assert_deps` reads `RunGraphEdge` (or whatever the edge table is called today) and compares parent-sets. Sketch only; must match the current schema.

### 2.2 `_assert_run_resources(run_id)` — 9 `RunResource` rows + optional artifact probes

```python
def _assert_run_resources(run_id: UUID) -> None:
    with get_session() as s:
        resources = s.exec(
            select(RunResource).where(RunResource.run_id == run_id),
        ).all()

    # Each leaf writes at minimum: 1 output file + 1 probe.json = 18 resources
    # (9 outputs + 9 probes). The parent does not publish resources.
    assert len(resources) >= 18, \
        f"expected >= 18 resources (9 outputs + 9 probes), got {len(resources)}"
    probes = [r for r in resources if r.name.startswith("probe_") and r.name.endswith(".json")]
    assert len(probes) == 9
    assert all(r.content_hash for r in resources), \
        "some resources missing content_hash"
```

### 2.3 `_assert_run_turn_counts(run_id)` — multi-turn persistence invariant

Protects the multi-turn fidelity choice documented in [`01-fixtures.md §2.6`](01-fixtures.md). Imports the `ClassVar`s off the base classes so the numbers can change in lock-step without editing this driver.

```python
from tests.e2e._fixtures.smoke_base.worker_base import SmokeWorkerBase
from tests.e2e._fixtures.smoke_base.leaf_base import BaseSmokeLeafWorker


def _assert_run_turn_counts(run_id: UUID) -> None:
    """1 parent × PARENT_TURN_COUNT + 9 leaves × LEAF_TURN_COUNT GenerationTurn rows."""
    expected = (
        SmokeWorkerBase.PARENT_TURN_COUNT
        + 9 * BaseSmokeLeafWorker.LEAF_TURN_COUNT
    )  # currently 3 + 18 = 21

    with get_session() as s:
        turns = s.exec(
            select(GenerationTurn)
            .where(GenerationTurn.run_id == run_id)
            .order_by(GenerationTurn.sequence),
        ).all()

    assert len(turns) == expected, (
        f"turn count mismatch: expected {expected} "
        f"(parent={SmokeWorkerBase.PARENT_TURN_COUNT}, "
        f"leaves=9×{BaseSmokeLeafWorker.LEAF_TURN_COUNT}), got {len(turns)}"
    )

    # Sequence must be strictly monotonic and dense (no gaps).
    seqs = [t.sequence for t in turns]
    assert seqs == sorted(seqs), f"turn sequences not monotonic: {seqs}"
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs))), \
        f"turn sequences not dense: {seqs}"
```

Sequence-density check catches regressions where `GenerationTurnRepository` silently drops a turn mid-stream.

### 2.4 `_assert_run_evaluation(run_id)` — exactly 1 evaluation, score 1.0

```python
def _assert_run_evaluation(run_id: UUID) -> None:
    with get_session() as s:
        evals = s.exec(
            select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id),
        ).all()
    assert len(evals) == 1, f"expected 1 evaluation, got {len(evals)}"
    assert evals[0].score == 1.0, \
        f"expected score 1.0, got {evals[0].score} ({evals[0].feedback!r})"
    assert evals[0].passed is True
```

### 2.5a `_assert_sandbox_command_wal(run_id)` — bash commands recorded

Each leaf runs at least one `sandbox.commands.run(...)` (its probe); the `BaseSandboxManager._emit_wal_entry` path writes one WAL row per command. Happy-path assertion: **at least 9 probe commands in the WAL for the run** (one per leaf), all with `exit_code == 0`.

```python
from ergon_core.core.persistence.sandbox.models import SandboxCommandWalEntry  # or current path

def _assert_sandbox_command_wal(run_id: UUID) -> None:
    with get_session() as s:
        entries = s.exec(
            select(SandboxCommandWalEntry)
            .where(SandboxCommandWalEntry.run_id == run_id)
            .order_by(SandboxCommandWalEntry.created_at),
        ).all()

    # Each leaf runs at least 1 probe command. Env-specific health check in
    # the criterion adds 1 more on the parent. Minimum = 9 (leaves) + 1 (criterion).
    probes = [e for e in entries if "probe" in e.command or "wc" in e.command
              or "lean --check" in e.command or "py_compile" in e.command]
    assert len(probes) >= 9, f"expected ≥9 probe commands in WAL, got {len(probes)}"

    # Happy path: every recorded exit_code is 0 (or None for commands we didn't
    # instrument). Any non-zero is a real probe failure, not a silent pass.
    non_zero = [(e.command, e.exit_code) for e in entries if e.exit_code not in (0, None)]
    assert not non_zero, f"non-zero exit_codes in WAL (happy path): {non_zero}"
```

Schema path is a sketch — replace with the current WAL table name. If WAL entries are stored alongside sandbox events rather than in a dedicated table, read from wherever `_emit_wal_entry` actually persists.

### 2.5b `_assert_sandbox_lifecycle_events(run_id)` — created/command/closed trio

The `SandboxEventSink` Protocol has three methods: `sandbox_created`, `sandbox_command`, `sandbox_closed`. `BaseSandboxManager.close()` fires `sandbox_closed` in a `finally` block, so the happy path must produce one `created` + one `closed` per sandbox, with `sandbox_command`s interleaved.

```python
from ergon_core.core.persistence.sandbox.models import SandboxEvent  # or current path

def _assert_sandbox_lifecycle_events(run_id: UUID) -> None:
    with get_session() as s:
        events = s.exec(
            select(SandboxEvent)
            .where(SandboxEvent.run_id == run_id)
            .order_by(SandboxEvent.created_at),
        ).all()

    # Sandboxes this run: 1 parent + 9 leaves = 10
    created = [e for e in events if e.kind == "sandbox_created"]
    closed  = [e for e in events if e.kind == "sandbox_closed"]
    assert len(created) == 10, f"expected 10 sandbox_created events, got {len(created)}"
    assert len(closed)  == 10, f"expected 10 sandbox_closed events, got {len(closed)}"

    # Each (sandbox_id, created) must have a matching (sandbox_id, closed)
    created_ids = {e.sandbox_id for e in created}
    closed_ids  = {e.sandbox_id for e in closed}
    assert created_ids == closed_ids, (
        f"created/closed sandbox_id mismatch: "
        f"only created = {created_ids - closed_ids}, only closed = {closed_ids - created_ids}"
    )

    # Ordering: for each sandbox_id, created.created_at < all its commands < closed.created_at.
    by_id: dict[str, list[SandboxEvent]] = {}
    for e in events:
        by_id.setdefault(e.sandbox_id, []).append(e)
    for sid, group in by_id.items():
        first, *_, last = sorted(group, key=lambda e: e.created_at)
        assert first.kind == "sandbox_created", f"{sid}: first event is {first.kind}"
        assert last.kind  == "sandbox_closed",  f"{sid}: last event is {last.kind}"
```

Kind-name strings (`"sandbox_created"`, `"sandbox_command"`, `"sandbox_closed"`) must match the SandboxEventSink persistence layer's current convention.

### 2.5c `_assert_thread_messages_ordered(run_id)` — inter-agent messaging

Each happy-path leaf calls `BaseSmokeLeafWorker._send_completion_message` exactly once. Expect 9 `ThreadMessage` rows on topic `"smoke-completion"` for this run.

```python
from ergon_core.core.persistence.telemetry.models import Thread, ThreadMessage

def _assert_thread_messages_ordered(run_id: UUID) -> None:
    with get_session() as s:
        threads = s.exec(
            select(Thread)
            .where(Thread.run_id == run_id)
            .where(Thread.topic == "smoke-completion"),
        ).all()
        assert len(threads) == 1, (
            f"expected 1 smoke-completion thread for run, got {len(threads)}"
        )
        thread = threads[0]
        assert thread.agent_a_id in ("parent",), f"unexpected agent_a_id: {thread.agent_a_id}"

        msgs = s.exec(
            select(ThreadMessage)
            .where(ThreadMessage.thread_id == thread.id)
            .order_by(ThreadMessage.sequence_num),
        ).all()

    # 9 messages, one per leaf.
    assert len(msgs) == 9, f"expected 9 completion messages, got {len(msgs)}"

    # sequence_num is per-thread monotonic starting at 1.
    seqs = [m.sequence_num for m in msgs]
    assert seqs == list(range(1, 10)), f"sequence_num not 1..9: {seqs}"

    # Each message is from a distinct leaf, targeting the parent.
    from_ids = [m.from_agent_id for m in msgs]
    assert set(from_ids) == {f"leaf-{slug}" for slug in EXPECTED_SUBTASK_SLUGS}, (
        f"from_agent_id set mismatch: {sorted(from_ids)}"
    )
    assert all(m.to_agent_id == "parent" for m in msgs), (
        f"non-parent to_agent_id: {[m.to_agent_id for m in msgs if m.to_agent_id != 'parent']}"
    )

    # Creation timestamps must not go backwards (sequence_num already enforces
    # thread-local order; this pins wall-clock order too).
    ts = [m.created_at for m in msgs]
    assert ts == sorted(ts), f"message timestamps not monotonic: {ts}"

    # task_execution_id FK present on every message.
    assert all(m.task_execution_id is not None for m in msgs), (
        "some messages missing task_execution_id FK"
    )
```

Sad-path counterpart asserts **8** messages with `l_2` missing from `from_ids`. See §10.

### 2.5d `_assert_blob_roundtrip(run_id)` — bytes-in == bytes-out

Picks one leaf's output artifact, re-reads it from blob storage, and confirms the bytes match what the leaf wrote. Cheap catch for blob-store truncation or content-hash drift.

```python
def _assert_blob_roundtrip(run_id: UUID) -> None:
    with get_session() as s:
        r = s.exec(
            select(RunResource)
            .where(RunResource.run_id == run_id)
            .where(RunResource.name.like("probe_%.json"))
            .order_by(RunResource.created_at)
            .limit(1),
        ).first()
    assert r is not None, "no probe_*.json to round-trip"
    assert r.content_hash, "resource missing content_hash"

    bytes_from_blob = BlobClient.default().get_sync(r.content_hash)
    # Minimal content-shape check: parses as JSON and has an exit_code key.
    parsed = json.loads(bytes_from_blob)
    assert "exit_code" in parsed, f"probe JSON missing exit_code: {parsed!r}"

    # Bytes should be identical on two fetches (idempotent read).
    bytes_again = BlobClient.default().get_sync(r.content_hash)
    assert bytes_from_blob == bytes_again, "blob read non-deterministic"
```

### 2.5e `_assert_temporal_ordering(run_id)` — DAG deps honoured in time

Graph dep check (§2.1) is structural. This one asserts **schedule**: `d_join.started_at >= max(d_left.completed_at, d_right.completed_at)`, etc.

```python
def _assert_temporal_ordering(run_id: UUID) -> None:
    with get_session() as s:
        leaves = s.exec(
            select(RunGraphNode)
            .where(RunGraphNode.run_id == run_id)
            .where(RunGraphNode.depth > 0),
        ).all()
    by_slug = {n.task_slug: n for n in leaves}

    def _after(child: str, parents: list[str]) -> None:
        child_started = by_slug[child].started_at
        latest_parent_done = max(by_slug[p].completed_at for p in parents)
        assert child_started >= latest_parent_done, (
            f"{child}.started_at ({child_started}) < "
            f"max({parents}).completed_at ({latest_parent_done})"
        )

    _after("d_join", ["d_left", "d_right"])
    _after("d_left", ["d_root"])
    _after("d_right", ["d_root"])
    _after("l_2", ["l_1"])
    _after("l_3", ["l_2"])
```

Only asserts ordering across dependency edges; zero-dep slugs (`d_root`, `l_1`, `s_a`, `s_b`) are free to run in any order.

### 2.5f `_assert_cohort_membership(cohort_key, run_ids)` — cohort view on BE side

Playwright checks the UI; this pins the same invariant in Python against the harness read DTO.

```python
def _assert_cohort_membership(cohort_key: str, run_ids: list[UUID]) -> None:
    import requests
    r = requests.get(
        f"{os.environ['ERGON_API_BASE_URL']}/api/test/read/cohort/{cohort_key}/runs",
        headers={"X-Test-Secret": os.environ["TEST_HARNESS_SECRET"]},
        timeout=10,
    )
    r.raise_for_status()
    cohort_runs = r.json()
    returned_ids = {row["run_id"] for row in cohort_runs}
    expected_ids = {str(rid) for rid in run_ids}
    assert returned_ids == expected_ids, (
        f"cohort membership mismatch: "
        f"only returned = {returned_ids - expected_ids}, "
        f"only expected = {expected_ids - returned_ids}"
    )
```

### 2.5 `_assert_mutations_ordered(run_id)` — optional extra

Not every assertion helper needs to run for every PR. `_assert_mutations_ordered` reads `RunGraphMutation` and asserts that:

- First mutation is `add_subtask` for either a diamond root, line root, or singleton (any of the four zero-dep slugs).
- `d_join` add precedes `d_join` start.
- All 9 `add_subtask` mutations exist with `parent_id == root.id`.

Include this in the driver only once the cheaper asserts are green in CI — it's a deeper probe of the mutation log that catches sequence regressions, not completion regressions.

---

## 3. Per-env `_assert_env_content`

### 3.1 ResearchRubrics

```python
def _assert_env_content(run_id: UUID) -> None:
    """One markdown report per leaf, non-empty, correct header."""
    outputs = _pull_artifacts(run_id, name_like="report_%.md")
    assert len(outputs) == 9
    for r in outputs:
        body = BlobClient.default().get_sync(r.content_hash).decode("utf-8")
        assert body.startswith("# Research report"), \
            f"{r.node_id}: missing `# Research report` header"
        assert len(body.strip()) >= 20, \
            f"{r.node_id}: body shorter than 20 bytes"
```

### 3.2 MiniF2F

```python
def _assert_env_content(run_id: UUID) -> None:
    """One .lean file per leaf, parses, contains `theorem smoke_trivial`."""
    outputs = _pull_artifacts(run_id, name_like="proof_%.lean")
    assert len(outputs) == 9
    for r in outputs:
        src = BlobClient.default().get_sync(r.content_hash).decode("utf-8")
        assert "theorem smoke_trivial" in src
        assert ":=" in src
```

### 3.3 SWE-Bench Verified

```python
import ast

def _assert_env_content(run_id: UUID) -> None:
    """One .py file per leaf, valid AST, contains function `add`."""
    outputs = _pull_artifacts(run_id, name_like="patch_%.py")
    assert len(outputs) == 9
    for r in outputs:
        src = BlobClient.default().get_sync(r.content_hash).decode("utf-8")
        tree = ast.parse(src)
        funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert "add" in funcs, f"{r.node_id}: expected `add`, got {sorted(funcs)}"
```

These assertions duplicate what `SmokeCriterionBase._verify_env_content` does on the criterion side — that is intentional. The **criterion runs inside the workflow and writes an evaluation row**; the **driver reruns the check out-of-band against the same artifacts**. If the criterion regresses silently, the driver catches it (and vice versa).

---

## 4. Phase 4: Playwright subprocess

```python
def _invoke_playwright(
    env: str, cohort_key: str, run_ids: list[UUID], screenshot_dir: pathlib.Path,
) -> None:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "pnpm", "--dir", "ergon-dashboard", "exec", "playwright",
            "test", f"tests/e2e/{env}.smoke.spec.ts",
            "--project=chromium",
        ],
        env={
            **os.environ,
            "COHORT_KEY": cohort_key,
            "RUN_IDS": ",".join(str(r) for r in run_ids),
            "SMOKE_ENV": env,
            "SCREENSHOT_DIR": str(screenshot_dir),
            "PLAYWRIGHT_LIVE": "1",
            "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:3000",
            "ERGON_API_BASE_URL": "http://127.0.0.1:9000",
            "TEST_HARNESS_SECRET": os.environ["TEST_HARNESS_SECRET"],
        },
        check=False,   # do not raise — screenshots still need uploading on fail
    )
    if result.returncode != 0:
        pytest.fail(f"playwright spec failed (returncode={result.returncode})")
```

Always runs, even if phase-3 assertions failed (so the dashboard state at time of failure is captured). Pytest own CI pass/fail — Playwright failure fails the test via `pytest.fail`.

---

## 5. Phase 5: screenshot finalizer

Implemented as a session-scoped pytest finalizer fixture (autouse in `tests/e2e/conftest.py`).

```python
# tests/e2e/conftest.py (excerpt)

@pytest.fixture(autouse=True, scope="session")
def _screenshot_uploader():
    yield
    pr_number = os.environ.get("GITHUB_PR_NUMBER")
    screenshot_dir = os.environ.get("SCREENSHOT_DIR", "/tmp/playwright")
    env = os.environ.get("SMOKE_ENV", "unknown")
    if not pr_number:
        return  # local run — skip
    subprocess.run(
        ["bash", "ci/push_screenshots.sh", pr_number, env, screenshot_dir],
        check=False,
    )
```

`ci/push_screenshots.sh` is specified in [`04-ci-and-workflows.md §4`](04-ci-and-workflows.md).

---

## 6. `submit_cohort` helper

Not yet a CLI surface. Minimal implementation — accepts a list of `(worker_slug, criterion_slug)` tuples so cohorts can be heterogeneous (e.g. 2 happy + 1 sad):

```python
# ergon_cli/submit.py  (or wherever current CLI submit lives)

async def submit_cohort(
    *, benchmark_slug: str,
    slots: list[tuple[str, str]],   # [(worker_slug, criterion_slug), …]
    cohort_key: str,
) -> list[UUID]:
    """Submit one run per slot, all with the same cohort_key.

    Returns run_ids in the same order as `slots`. Parallel submission is via
    asyncio.gather. Under the hood this calls whatever today does `ergon run`;
    the cross-cutting additions are (a) heterogeneous worker slugs per slot
    and (b) stable cohort_key.
    """
    ...
```

If the CLI already supports cohort submission, extend it for heterogeneous slots. Otherwise a 20-line wrapper over the existing single-run submit path is fine — it is test-only.

---

## 7. `wait_for_terminal`

Polls `/runs/{run_id}` (or the equivalent service call) every 2 seconds until status ∈ {completed, failed, cancelled}. Returns the terminal status. Raises `TimeoutError` on timeout.

```python
TERMINAL = {"completed", "failed", "cancelled"}

async def wait_for_terminal(run_id: UUID, timeout_seconds: int) -> str:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = await _get_run_status(run_id)
        if status in TERMINAL:
            return status
        await asyncio.sleep(2)
    raise TimeoutError(f"run {run_id} did not reach terminal status within {timeout_seconds}s")
```

The driver does **not** assert on the terminal status value here — it asserts after via `_assert_run_evaluation` (score == 1.0 implies completed-clean). This keeps "did we finish?" and "did we finish correctly?" separate.

---

## 8. Failure modes worth naming

| Failure | Which assertion catches it |
|---|---|
| Inngest function crashes mid-run | `wait_for_terminal` times out |
| Graph edge table wrong | `_assert_deps` in `_assert_run_graph` |
| A leaf subtask stuck in `IN_PROGRESS` | `_assert_run_graph` node status check |
| Sandbox provision fails partway | `wait_for_terminal` returns `failed`; `_assert_run_evaluation` fails (score != 1.0) |
| Leaf writes file but probe JSON missing | `_assert_run_resources` probe-count check |
| `GenerationTurn` rows dropped / sequence gap | `_assert_run_turn_counts` |
| Parent yields wrong number of turns | `_assert_run_turn_counts` (catches silent divergence from `PARENT_TURN_COUNT`) |
| Sandbox `commands.run` doesn't emit WAL row | `_assert_sandbox_command_wal` |
| `sandbox_closed` not fired on teardown | `_assert_sandbox_lifecycle_events` (mismatched created/closed counts) |
| `CommunicationService.save_message` regression | `_assert_thread_messages_ordered` (message count / ordering / FK) |
| Blob-store returns wrong bytes for a hash | `_assert_blob_roundtrip` |
| DAG dep violated at scheduling time (child runs before parent done) | `_assert_temporal_ordering` |
| Cohort view misses a run | `_assert_cohort_membership` |
| Criterion writes evaluation with score 0 | `_assert_run_evaluation` |
| Partial artifacts lost when leaf fails | `_assert_sadpath_partial_artifact` (sad-path driver) |
| Sandbox command WAL not written for pre-failure commands | `_assert_sadpath_partial_wal` |
| Failed leaf still marked COMPLETED | `_assert_sadpath_graph_cascade` |
| Static-sibling failure cascade missing on l_3 | `_assert_sadpath_graph_cascade` |
| Failed leaf sends completion message anyway | `_assert_sadpath_thread_messages` |
| Dashboard missing graph UI | Playwright spec |
| Dashboard rerender broken on cohort index | Playwright spec ([`03-dashboard-and-playwright.md §5`](03-dashboard-and-playwright.md)) |

The driver's assertion order is chosen so the first failure points squarely at a layer (runtime, graph, resource, eval, UI) instead of at a cascade.

---

## 9. Migration note — 3-run cohort asserts

Every helper above takes a **single `run_id`** and is called in a loop for all 3 cohort runs. This is intentional: each run must independently pass every check. No "at least one passed" fallback; no cohort-level aggregation that could hide a per-run regression.

If a cohort-level invariant becomes useful later (e.g. "all 3 runs produced identical resource counts"), add it as a separate helper after the per-run loop — do not merge into the per-run check.

---

## 10. Sad-run assertion helpers (researchrubrics cohort slot 3)

The researchrubrics cohort's third slot uses `ResearchRubricsSadPathSmokeWorker`. It is submitted through the same `submit_cohort` call as the 2 happy slots (§1) and runs in parallel with them under the same `cohort_key`. Only the per-run **assertion dispatch** differs: `_assert_sad_run` below replaces the happy-path block.

There is **no separate driver file** and **no fourth matrix leg**. The sad run lives inside `tests/e2e/test_researchrubrics_smoke.py`. MiniF2F + SWE-bench drivers have no sad slot.

### 10.1 Sad-path specific helpers

```python
def _assert_sadpath_graph_cascade(run_id: UUID) -> None:
    """Line cascade failure: l_1 done, l_2 failed, l_3 blocked/cancelled.
    Diamond + singletons unaffected."""
    with get_session() as s:
        leaves = s.exec(
            select(RunGraphNode)
            .where(RunGraphNode.run_id == run_id)
            .where(RunGraphNode.depth > 0),
        ).all()
    by_slug = {n.task_slug: n for n in leaves}

    # Line: cascade of deterministic failure
    assert by_slug["l_1"].status == COMPLETED, by_slug["l_1"].status
    assert by_slug["l_2"].status == FAILED,    by_slug["l_2"].status
    assert by_slug["l_3"].status in {BLOCKED, CANCELLED}, (
        f"l_3 expected BLOCKED or CANCELLED per static-sibling-failure-semantics RFC, "
        f"got {by_slug['l_3'].status}"
    )

    # Diamond + singletons: independent branches, must still all COMPLETED.
    for slug in ("d_root", "d_left", "d_right", "d_join", "s_a", "s_b"):
        assert by_slug[slug].status == COMPLETED, (
            f"{slug} expected COMPLETED (independent branch), got {by_slug[slug].status}"
        )


def _assert_sadpath_partial_artifact(run_id: UUID) -> None:
    """AlwaysFailSubworker writes `partial_<node>.md` BEFORE raising.
    The runtime's persist step must still serialize it as a RunResource."""
    with get_session() as s:
        partials = s.exec(
            select(RunResource)
            .where(RunResource.run_id == run_id)
            .where(RunResource.name.like("partial_%.md")),
        ).all()
    # Only l_2 fails, so exactly 1 partial artifact.
    assert len(partials) == 1, (
        f"expected 1 partial artifact from l_2 (partial work must persist on "
        f"FAILED leaf), got {len(partials)}"
    )
    r = partials[0]
    assert r.content_hash, f"partial resource missing content_hash"
    body = BlobClient.default().get_sync(r.content_hash).decode("utf-8")
    assert body.startswith("# Partial work"), (
        f"partial artifact body unexpected: {body[:80]!r}"
    )


def _assert_sadpath_partial_wal(run_id: UUID) -> None:
    """The pre-failure `wc -l` command must land as a sandbox_command WAL row
    even though the leaf ultimately failed."""
    with get_session() as s:
        entries = s.exec(
            select(SandboxCommandWalEntry)
            .where(SandboxCommandWalEntry.run_id == run_id),
        ).all()
    wc_entries = [e for e in entries if "wc -l" in e.command and "partial_" in e.command]
    assert len(wc_entries) >= 1, (
        f"expected ≥1 'wc -l partial_*' WAL entry from pre-failure probe; "
        f"sandbox_command path did not persist the command before the raise"
    )
    # That command should have succeeded (exit 0) — the failure is the raise
    # AFTER the command, not the command itself.
    assert all(e.exit_code == 0 for e in wc_entries), (
        f"pre-failure wc probe non-zero exit: {[(e.command, e.exit_code) for e in wc_entries]}"
    )


def _assert_sadpath_thread_messages(run_id: UUID) -> None:
    """Happy path sends 9 completion messages; l_2 raises before sending.
    Expect 8 on the smoke-completion thread, l_2 missing."""
    with get_session() as s:
        thread = s.exec(
            select(Thread)
            .where(Thread.run_id == run_id)
            .where(Thread.topic == "smoke-completion"),
        ).first()
        assert thread is not None, "no smoke-completion thread created"
        msgs = s.exec(
            select(ThreadMessage)
            .where(ThreadMessage.thread_id == thread.id)
            .order_by(ThreadMessage.sequence_num),
        ).all()
    assert len(msgs) == 8, (
        f"expected 8 completion messages (l_2 raises before sending), got {len(msgs)}"
    )
    from_slugs = {m.from_agent_id.removeprefix("leaf-") for m in msgs}
    assert "l_2" not in from_slugs, (
        f"l_2 sent a completion message despite raising: {from_slugs}"
    )
    assert from_slugs == set(EXPECTED_SUBTASK_SLUGS) - {"l_2"}


def _assert_sadpath_evaluation(run_id: UUID) -> None:
    """Reusing happy-path criterion on sad-path run MUST return score 0.
    feedback should name the failing slug so operators see it quickly."""
    with get_session() as s:
        evals = s.exec(
            select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id),
        ).all()
    assert len(evals) == 1
    assert evals[0].score == 0.0
    assert evals[0].passed is False
    # Criterion's `_check_children_completed` raises with "l_2 not completed"
    # or similar — just assert the slug appears for operator-visibility.
    assert "l_2" in (evals[0].feedback or ""), (
        f"sad-path evaluation feedback should mention l_2; got: {evals[0].feedback!r}"
    )
```

### 10.2 Playwright delta for the sad run

The driver passes a `cohort: [{ run_id, kind }, …]` array to Playwright (see `_invoke_playwright` in §1). The existing `researchrubrics.smoke.spec.ts` — built from the shared factory in `_shared/smoke.ts` — iterates that list and branches on `kind`:

```typescript
// ergon-dashboard/tests/e2e/_shared/smoke.ts (excerpt, added inside defineSmokeSpec)

for (const { run_id, kind } of cohort) {
  test(`run ${run_id} (${kind})`, async ({ page }) => {
    if (kind === "happy") {
      // existing happy-path assertions (§5 of 03-dashboard-and-playwright.md)
    } else {
      // sad: l_2 FAILED, l_3 BLOCKED/CANCELLED, everything else COMPLETED
      await page.goto(`/run/${run_id}`);
      await expect(page.getByTestId("run-status")).toHaveText(/failed/i);
      await expect(page.getByTestId("task-node-l_2"))
        .toHaveAttribute("data-status", "failed");
      await expect(page.getByTestId("task-node-l_3"))
        .toHaveAttribute("data-status", /blocked|cancelled/);
      for (const slug of ["d_root", "d_left", "d_right", "d_join", "s_a", "s_b", "l_1"]) {
        await expect(page.getByTestId(`task-node-${slug}`))
          .toHaveAttribute("data-status", "completed");
      }
      await page.screenshot({
        path: `${screenshotDir}/${run_id}-sad-failed.png`, fullPage: true,
      });
    }
  });
}
```

No separate spec file. No separate Playwright project. The sad run is visible in the cohort index alongside the 2 happy runs — and the Playwright spec's cohort assertion (3 runs listed) still passes.

### 10.3 CI sequencing

No fourth matrix leg. The researchrubrics leg's cohort-of-3 naturally contains the sad run in slot 3; `e2e-benchmarks.yml` matrix stays at `[researchrubrics, minif2f, swebench-verified]`. The sad run adds zero top-level runs and replaces one happy leaf-count-9 with a leaf-count-8 (l_3 not provisioned), for a net **-1** sandbox vs an all-happy matrix.

### 10.4 What the sad run specifically catches

| Regression | Caught by |
|---|---|
| Partial artifacts dropped when a leaf fails | `_assert_sadpath_partial_artifact` |
| Sandbox command WAL not written until success | `_assert_sadpath_partial_wal` |
| Leaf exception silently converted to COMPLETED | `_assert_sadpath_graph_cascade` (l_2 must be FAILED) |
| Static-sibling failure cascade not implemented | `_assert_sadpath_graph_cascade` (l_3 check) |
| Dynamic/static subtask semantics conflated (l_3 COMPLETED anyway) | same |
| Independent branches accidentally cancelled when a sibling fails | `_assert_sadpath_graph_cascade` (diamond + singletons) |
| Completion message sent from a failed leaf | `_assert_sadpath_thread_messages` (l_2 must NOT appear) |
| Evaluation silently returns score=1.0 on a half-failed run | `_assert_sadpath_evaluation` |
