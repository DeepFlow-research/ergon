"""Shared assertion helpers for canonical smoke drivers.

Per-run helpers take a single ``run_id`` and are called in a loop for
each cohort member.  No "at-least-one-passed" fallbacks; each run must
pass every check independently.  Cohort-level helpers (e.g.
``_assert_cohort_membership``) take the cohort key + run_id list.

See docs/superpowers/plans/test-refactor/02-drivers-and-asserts.md §2
and §10 for the full catalogue.

Schema paths are best-effort sketches against the current
``ergon_core.core.persistence.*`` models; if a table name moves, fix
the import + query inline rather than pushing complexity into this
module.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from uuid import UUID

import httpx
from sqlmodel import select

from ergon_core.core.persistence.graph.models import RunGraphEdge, RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import COMPLETED
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.persistence.telemetry.models import (
    RunResource,
    RunTaskEvaluation,
    RunTaskExecution,
    SandboxCommandWalEntry,
    SandboxEvent,
    Thread,
    ThreadMessage,
)

from tests.e2e._fixtures.smoke_base.constants import EXPECTED_SUBTASK_SLUGS
from tests.e2e._fixtures.smoke_base.leaf_base import BaseSmokeLeafWorker
from tests.e2e._fixtures.smoke_base.worker_base import SmokeWorkerBase

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


# =============================================================================
# Run-level helpers (happy path)
# =============================================================================


def _assert_run_graph(run_id: UUID) -> None:
    """1 root + 9 leaves = 10 nodes; all COMPLETED; deps honoured."""
    with get_session() as s:
        nodes = list(
            s.exec(
                select(RunGraphNode)
                .where(RunGraphNode.run_id == run_id)
                .order_by(RunGraphNode.level, RunGraphNode.task_slug),  # ty: ignore[unresolved-attribute]
            ).all(),
        )

    assert len(nodes) == 10, f"expected 10 nodes, got {len(nodes)}"
    leaves = [n for n in nodes if n.level > 0]
    root_nodes = [n for n in nodes if n.level == 0]
    assert len(root_nodes) == 1, f"expected 1 root node, got {len(root_nodes)}"
    assert len(leaves) == 9, f"expected 9 leaves, got {len(leaves)}"
    assert sorted(n.task_slug for n in leaves) == sorted(EXPECTED_SUBTASK_SLUGS)
    non_completed = [(n.task_slug, n.status) for n in nodes if n.status != COMPLETED]
    assert not non_completed, f"non-completed nodes: {non_completed}"

    _assert_dag_edges(run_id, leaves)


def _assert_dag_edges(run_id: UUID, leaves: list[RunGraphNode]) -> None:
    """Verify each dep edge exists in ``run_graph_edges``."""
    with get_session() as s:
        edges = list(s.exec(select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)).all())
    by_slug = {n.task_slug: n.id for n in leaves}
    actual_pairs: set[tuple[str, str]] = set()
    id_to_slug = {nid: slug for slug, nid in by_slug.items()}
    for e in edges:
        src = id_to_slug.get(e.source_node_id)
        tgt = id_to_slug.get(e.target_node_id)
        if src is not None and tgt is not None:
            actual_pairs.add((src, tgt))

    expected_pairs = {
        ("d_root", "d_left"),
        ("d_root", "d_right"),
        ("d_left", "d_join"),
        ("d_right", "d_join"),
        ("l_1", "l_2"),
        ("l_2", "l_3"),
    }
    missing = expected_pairs - actual_pairs
    assert not missing, f"missing DAG edges: {missing}"


def _assert_run_resources(run_id: UUID) -> None:
    """Exactly 18 kind='report' resources: 9 report_*.md + 9 probe_*.json.

    All resources from ``SandboxResourcePublisher.sync()`` land as
    ``kind='report'``.  The legacy ``kind='output'`` download path has been
    removed from ``persist_outputs.py``.
    """
    with get_session() as s:
        resources = list(s.exec(select(RunResource).where(RunResource.run_id == run_id)).all())

    report_resources = [r for r in resources if r.kind == "report"]
    probes = [
        r for r in report_resources if r.name.startswith("probe_") and r.name.endswith(".json")
    ]
    assert len(probes) == 9, f"expected 9 probe_*.json (kind=report) resources, got {len(probes)}"
    assert len(report_resources) == 18, (
        f"expected 18 kind=report resources (9 reports + 9 probes), got {len(report_resources)}"
    )
    missing_hash = [r.name for r in resources if not r.content_hash]
    assert not missing_hash, f"resources missing content_hash: {missing_hash}"


def _assert_run_turn_counts(run_id: UUID) -> None:
    """1 parent × PARENT_TURN_COUNT + N leaves × LEAF_TURN_COUNT context events.

    Each smoke ``GenerationTurn`` has ``messages_in=[]`` and one ``TextPart``
    in ``response_parts``, so ``persist_turn`` emits exactly 1 ``RunContextEvent``
    per turn.  Total = PARENT_TURN_COUNT + len(EXPECTED_SUBTASK_SLUGS) × LEAF_TURN_COUNT.
    """
    expected = (
        SmokeWorkerBase.PARENT_TURN_COUNT
        + len(EXPECTED_SUBTASK_SLUGS) * BaseSmokeLeafWorker.LEAF_TURN_COUNT
    )  # currently 3 + 9×2 = 21

    with get_session() as s:
        events = list(
            s.exec(select(RunContextEvent).where(RunContextEvent.run_id == run_id)).all(),
        )

    assert len(events) == expected, (
        f"turn count mismatch: expected {expected} "
        f"(parent={SmokeWorkerBase.PARENT_TURN_COUNT}, "
        f"leaves={len(EXPECTED_SUBTASK_SLUGS)}×{BaseSmokeLeafWorker.LEAF_TURN_COUNT}), got {len(events)}"
    )


def _assert_run_evaluation(run_id: UUID) -> None:
    """Exactly 1 RunTaskEvaluation row with score 1.0.

    Retries for up to 30 s because the evaluator Inngest function fires
    asynchronously after the run reaches terminal state.
    """
    deadline = time.monotonic() + 30
    evals: list[RunTaskEvaluation] = []
    while time.monotonic() < deadline:
        with get_session() as s:
            evals = list(
                s.exec(select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)).all(),
            )
        if evals:
            break
        time.sleep(2)
    assert len(evals) == 1, f"expected 1 evaluation, got {len(evals)}"
    assert evals[0].score == 1.0, (
        f"expected score 1.0, got {evals[0].score} ({evals[0].feedback!r})"
    )
    assert evals[0].passed is True


# =============================================================================
# Observability helpers (run-level)
# =============================================================================


def _assert_sandbox_command_wal(run_id: UUID) -> None:
    """Bash commands land as WAL rows via ``PostgresSandboxEventSink``."""
    with get_session() as s:
        entries = list(
            s.exec(
                select(SandboxCommandWalEntry).where(SandboxCommandWalEntry.run_id == run_id),
            ).all(),
        )
    probes = [e for e in entries if "wc" in e.command or "probe" in e.command]
    assert len(probes) >= 9, f"expected ≥9 probe WAL entries, got {len(probes)}"


def _assert_sandbox_lifecycle_events(run_id: UUID) -> None:
    """``sandbox_created`` + ``sandbox_closed`` symmetric per sandbox."""
    deadline = time.monotonic() + 30
    events: list[SandboxEvent] = []
    while time.monotonic() < deadline:
        with get_session() as s:
            events = list(s.exec(select(SandboxEvent).where(SandboxEvent.run_id == run_id)).all())
        created = {e.sandbox_id for e in events if e.kind == "sandbox_created"}
        closed = {e.sandbox_id for e in events if e.kind == "sandbox_closed"}
        if created == closed:
            return
        time.sleep(2)

    created = {e.sandbox_id for e in events if e.kind == "sandbox_created"}
    closed = {e.sandbox_id for e in events if e.kind == "sandbox_closed"}
    assert created == closed, (
        f"created/closed sandbox_id mismatch: "
        f"only created={created - closed}, only closed={closed - created}"
    )


def _assert_thread_messages_ordered(run_id: UUID) -> None:
    """9 completion messages on the ``smoke-completion`` thread."""
    with get_session() as s:
        threads = list(
            s.exec(
                select(Thread)
                .where(Thread.run_id == run_id)
                .where(Thread.topic == "smoke-completion"),
            ).all(),
        )
        assert len(threads) == 1, f"expected 1 smoke-completion thread, got {len(threads)}"
        thread = threads[0]
        msgs = list(
            s.exec(
                select(ThreadMessage)
                .where(ThreadMessage.thread_id == thread.id)
                .order_by(ThreadMessage.sequence_num),  # ty: ignore[unresolved-attribute]
            ).all(),
        )
    assert len(msgs) == 9, f"expected 9 completion messages, got {len(msgs)}"
    assert [m.sequence_num for m in msgs] == list(range(1, 10))
    from_slugs = {m.from_agent_id.removeprefix("leaf-") for m in msgs}
    assert from_slugs == set(EXPECTED_SUBTASK_SLUGS), (
        f"from_agent_id slug set mismatch: {sorted(from_slugs)}"
    )
    assert all(m.to_agent_id == "parent" for m in msgs)
    assert all(m.task_execution_id is not None for m in msgs)


def _assert_blob_roundtrip(run_id: UUID) -> None:
    """Read one probe JSON artifact from disk; confirm it parses and
    is byte-stable across two reads.

    Uses ``kind='report'`` resources because those are written to the
    content-addressed blob store (``ERGON_BLOB_ROOT``) which is bind-mounted
    at the same path on both the host and inside the API container.  The
    legacy ``kind='output'`` rows store container-internal download paths
    that are not directly accessible from the host-side test process.
    """
    with get_session() as s:
        row = s.exec(
            select(RunResource)
            .where(RunResource.run_id == run_id)
            .where(
                RunResource.name.like("probe_%.json"),  # ty: ignore[unresolved-attribute]
            )
            .where(RunResource.kind == "report")
            .order_by(
                RunResource.created_at,  # ty: ignore[unresolved-attribute]
            )
            .limit(1),
        ).first()
    assert row is not None, "no probe_*.json (kind=report) to round-trip"
    assert row.content_hash
    bytes_a = Path(row.file_path).read_bytes()
    bytes_b = Path(row.file_path).read_bytes()
    assert bytes_a == bytes_b, "blob read non-deterministic"
    parsed = json.loads(bytes_a)
    assert "exit_code" in parsed, f"probe JSON missing exit_code: {parsed!r}"


def _assert_temporal_ordering(run_id: UUID) -> None:
    """Schedule honours DAG deps: children start no earlier than parents finish.

    Uses ``RunTaskExecution.started_at`` / ``completed_at`` via
    ``node_id`` join.  Only checks edges whose both endpoints reached
    at least ``started`` state; skips silently otherwise (sad-path
    ``l_3`` never starts, so its edge is skipped).
    """
    with get_session() as s:
        leaves = list(
            s.exec(
                select(RunGraphNode)
                .where(RunGraphNode.run_id == run_id)
                .where(RunGraphNode.level > 0),
            ).all(),
        )
        executions = list(
            s.exec(
                select(RunTaskExecution)
                .where(RunTaskExecution.run_id == run_id)
                .where(
                    RunTaskExecution.node_id.in_([leaf.id for leaf in leaves]),  # ty: ignore[unresolved-attribute]
                ),
            ).all(),
        )
    by_node = {e.node_id: e for e in executions if e.node_id is not None}
    slug_exec = {leaf.task_slug: by_node.get(leaf.id) for leaf in leaves}

    def _after(child: str, parents: list[str]) -> None:
        c_exec = slug_exec.get(child)
        if c_exec is None or c_exec.started_at is None:
            return  # child never started (valid on sad path)
        for p in parents:
            p_exec = slug_exec.get(p)
            if p_exec is None or p_exec.completed_at is None:
                continue
            assert c_exec.started_at >= p_exec.completed_at, (
                f"{child}.started_at ({c_exec.started_at}) < "
                f"{p}.completed_at ({p_exec.completed_at})"
            )

    _after("d_join", ["d_left", "d_right"])
    _after("d_left", ["d_root"])
    _after("d_right", ["d_root"])
    _after("l_2", ["l_1"])
    _after("l_3", ["l_2"])


# =============================================================================
# Cohort-level helpers
# =============================================================================


def _assert_cohort_membership(cohort_key: str, run_ids: list[UUID]) -> None:
    """3 runs visible via ``/api/test/read/cohort/{key}/runs`` harness endpoint."""
    api_base = os.environ["ERGON_API_BASE_URL"]
    secret = os.environ["TEST_HARNESS_SECRET"]
    r = httpx.get(
        f"{api_base}/api/test/read/cohort/{cohort_key}/runs",
        headers={"X-Test-Secret": secret},
        timeout=10.0,
    )
    r.raise_for_status()
    rows = r.json()
    returned = {UUID(row["run_id"]) for row in rows}
    expected = set(run_ids)
    assert returned == expected, (
        f"cohort membership mismatch: only returned={returned - expected}, "
        f"only expected={expected - returned}"
    )


# =============================================================================
# Sad-path helpers
# =============================================================================


def _assert_sadpath_graph_cascade(run_id: UUID) -> None:
    """Score-zero sad path: all graph nodes complete, l_2 produces failed output."""
    with get_session() as s:
        leaves = list(
            s.exec(
                select(RunGraphNode)
                .where(RunGraphNode.run_id == run_id)
                .where(RunGraphNode.level > 0),
            ).all(),
        )
    by_slug = {n.task_slug: n for n in leaves}
    for slug in EXPECTED_SUBTASK_SLUGS:
        assert by_slug[slug].status == COMPLETED, (
            f"{slug} expected COMPLETED, got {by_slug[slug].status}"
        )


def _assert_sadpath_partial_artifact(run_id: UUID) -> None:
    """``AlwaysFailSubworker`` writes ``partial_<node>.md`` before raising.
    The runtime's persist step must still serialize it as a RunResource."""
    deadline = time.monotonic() + 30
    partials: list[RunResource] = []
    while time.monotonic() < deadline:
        with get_session() as s:
            partials = list(
                s.exec(
                    select(RunResource)
                    .where(RunResource.run_id == run_id)
                    .where(
                        RunResource.name.like("partial_%.md"),  # ty: ignore[unresolved-attribute]
                    ),
                ).all(),
            )
        if partials:
            break
        time.sleep(2)
    assert len(partials) == 1, (
        f"expected 1 partial artifact from l_2 (partial work must persist on "
        f"FAILED leaf), got {len(partials)}"
    )
    r = partials[0]
    assert r.content_hash, "partial resource missing content_hash"
    body = Path(r.file_path).read_bytes().decode("utf-8")
    assert body.startswith("# Partial work"), f"partial artifact body unexpected: {body[:80]!r}"


def _assert_sadpath_partial_wal(run_id: UUID) -> None:
    """Pre-failure ``wc -l partial_*`` command persists as WAL row."""
    deadline = time.monotonic() + 30
    wc: list[SandboxCommandWalEntry] = []
    while time.monotonic() < deadline:
        with get_session() as s:
            entries = list(
                s.exec(
                    select(SandboxCommandWalEntry).where(SandboxCommandWalEntry.run_id == run_id),
                ).all(),
            )
        wc = [e for e in entries if "wc -l" in e.command and "partial_" in e.command]
        if wc:
            break
        time.sleep(2)
    assert len(wc) >= 1, (
        "expected ≥1 'wc -l partial_*' WAL entry from the pre-failure probe; "
        "sandbox_command path did not persist the command before the raise"
    )


def _assert_sadpath_thread_messages(run_id: UUID) -> None:
    """Happy path sends 9 messages; sad l_2 suppresses completion reporting."""
    with get_session() as s:
        thread = s.exec(
            select(Thread).where(Thread.run_id == run_id).where(Thread.topic == "smoke-completion"),
        ).first()
        assert thread is not None, "no smoke-completion thread created"
        msgs = list(
            s.exec(
                select(ThreadMessage)
                .where(ThreadMessage.thread_id == thread.id)
                .order_by(ThreadMessage.sequence_num),  # ty: ignore[unresolved-attribute]
            ).all(),
        )
    assert len(msgs) == 8, f"expected 8 completion messages (l_2 suppressed), got {len(msgs)}"
    from_slugs = {m.from_agent_id.removeprefix("leaf-") for m in msgs}
    assert "l_2" not in from_slugs, (
        f"l_2 sent a completion message despite suppression: {from_slugs}"
    )
    assert from_slugs == set(EXPECTED_SUBTASK_SLUGS) - {"l_2"}


def _assert_sadpath_evaluation(run_id: UUID) -> None:
    """Reusing happy-path criterion on sad-path run must return score 0."""
    with get_session() as s:
        evals = list(
            s.exec(select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)).all(),
        )
    assert len(evals) == 1
    assert evals[0].score == 0.0
    assert evals[0].passed is False


# =============================================================================
# Polling helpers
# =============================================================================


async def wait_for_terminal(run_id: UUID, timeout_seconds: int = 270) -> str:
    """Poll the harness read endpoint until the run reaches a terminal state."""
    return await wait_for_terminal_status(
        run_id,
        expected_statuses=frozenset({"completed"}),
        timeout_seconds=timeout_seconds,
    )


async def wait_for_terminal_status(
    run_id: UUID,
    *,
    expected_statuses: frozenset[str],
    timeout_seconds: int = 270,
) -> str:
    """Poll until the run reaches one of the expected terminal statuses."""
    api_base = os.environ["ERGON_API_BASE_URL"]
    secret = os.environ["TEST_HARNESS_SECRET"]
    deadline = time.monotonic() + timeout_seconds
    last_state: dict[str, object] | None = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        while time.monotonic() < deadline:
            r = await client.get(
                f"{api_base}/api/test/read/run/{run_id}/state",
                headers={"X-Test-Secret": secret},
            )
            if r.status_code == 200:
                state = r.json()
                last_state = state
                status = state["status"]
                if status in expected_statuses:
                    return status
                if status in TERMINAL_STATUSES:
                    raise AssertionError(
                        f"run {run_id} reached terminal failure status {status!r}:\n"
                        f"{json.dumps(state, indent=2, sort_keys=True)}"
                    )
            await asyncio.sleep(2)
    raise TimeoutError(
        f"run {run_id} did not reach terminal status within {timeout_seconds}s:\n"
        f"{json.dumps(last_state, indent=2, sort_keys=True)}",
    )
