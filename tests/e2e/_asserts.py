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

import ast
import asyncio
import json
import os
import time
from pathlib import Path
from uuid import UUID

import httpx
from sqlmodel import select

from ergon_core.core.api.schemas import RunTaskDto
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import BLOCKED, COMPLETED, FAILED
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import (
    RunResource,
    RunTaskExecution,
    SandboxCommandWalEntry,
    SandboxEvent,
)

from ergon_core.test_support.smoke_fixtures.smoke_base.constants import EXPECTED_SUBTASK_SLUGS
from ergon_core.test_support.smoke_fixtures.smoke_base.leaf_base import BaseSmokeLeafWorker
from ergon_core.test_support.smoke_fixtures.smoke_base.worker_base import SmokeWorkerBase
from tests.e2e._read_contracts import require_run_snapshot

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


# =============================================================================
# Run-level helpers (happy path)
# =============================================================================


def _assert_run_graph(run_id: UUID) -> None:
    """1 root + 9 leaves = 10 tasks; all COMPLETED; deps honoured."""
    snapshot = require_run_snapshot(run_id)
    tasks = list(snapshot.tasks.values())
    leaves = [task for task in tasks if task.level > 0]
    root_tasks = [task for task in tasks if task.level == 0]

    assert snapshot.total_tasks == 10, f"expected 10 tasks, got {snapshot.total_tasks}"
    assert snapshot.total_leaf_tasks == 9, f"expected 9 leaf tasks, got {snapshot.total_leaf_tasks}"
    assert len(root_tasks) == 1, f"expected 1 root task, got {len(root_tasks)}"
    assert snapshot.root_task_id == root_tasks[0].id
    assert sorted(task.name for task in leaves) == sorted(EXPECTED_SUBTASK_SLUGS)
    non_completed = [(task.name, task.status) for task in tasks if task.status != COMPLETED]
    assert not non_completed, f"non-completed nodes: {non_completed}"

    _assert_dag_edges(leaves)


def _assert_dag_edges(leaves: list[RunTaskDto]) -> None:
    """Verify each dependency edge is exposed by the read-service task DTO."""
    by_id = {task.id: task for task in leaves}
    actual_pairs = {
        (by_id[parent_id].name, task.name)
        for task in leaves
        for parent_id in task.depends_on_ids
        if parent_id in by_id
    }
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
    """Exactly 18 task resources: 9 benchmark artifacts + 9 probe_*.json."""
    snapshot = require_run_snapshot(run_id)
    resources = [
        resource
        for task_resources in snapshot.resources_by_task.values()
        for resource in task_resources
    ]
    probes = [
        resource
        for resource in resources
        if resource.name.startswith("probe_") and resource.name.endswith(".json")
    ]
    assert len(probes) == 9, f"expected 9 probe_*.json (kind=report) resources, got {len(probes)}"
    worker_outputs = [resource for resource in resources if resource.name == "worker_output"]
    assert not worker_outputs, (
        "worker final assistant messages must stay on executions, not resources"
    )
    assert len(resources) == 18, (
        f"expected 18 task artifact resources (9 outputs + 9 probes), got {len(resources)}"
    )


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

    snapshot = require_run_snapshot(run_id)
    event_count = sum(len(events) for events in snapshot.context_events_by_task.values())

    assert event_count == expected, (
        f"turn count mismatch: expected {expected} "
        f"(parent={SmokeWorkerBase.PARENT_TURN_COUNT}, "
        f"leaves={len(EXPECTED_SUBTASK_SLUGS)}×{BaseSmokeLeafWorker.LEAF_TURN_COUNT}), got {event_count}"
    )


def _assert_run_evaluation(run_id: UUID) -> None:
    """Exactly 1 RunTaskEvaluation row with score 1.0.

    Retries for up to 30 s because the evaluator Inngest function fires
    asynchronously after the run reaches terminal state.
    """
    deadline = time.monotonic() + 30
    evaluations = []
    while time.monotonic() < deadline:
        snapshot = require_run_snapshot(run_id)
        evaluations = list(snapshot.evaluations_by_task.values())
        if evaluations:
            break
        time.sleep(2)
    assert len(evaluations) == 1, f"expected 1 task evaluation, got {len(evaluations)}"
    assert evaluations[0].total_score == 1.0, (
        f"expected score 1.0, got {evaluations[0].total_score}"
    )
    assert snapshot.final_score == 1.0


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
    # Canonical sad-path smokes block l_3 before it starts, so the eight
    # executed leaves should emit probe commands while l_3 emits none.
    assert len(probes) >= 8, f"expected ≥8 probe WAL entries, got {len(probes)}"


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
    snapshot = require_run_snapshot(run_id)
    threads = [thread for thread in snapshot.threads if thread.topic == "smoke-completion"]
    assert len(threads) == 1, f"expected 1 smoke-completion thread, got {len(threads)}"
    msgs = sorted(threads[0].messages, key=lambda msg: msg.sequence_num)
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


def _assert_minif2f_artifacts(run_id: UUID) -> None:
    """Every MiniF2F leaf persists a Lean proof artifact with the smoke theorem."""
    resources = _require_named_resources(run_id, prefix="proof_", suffix=".lean", expected_count=9)
    for resource in resources:
        text = Path(resource.file_path).read_bytes().decode("utf-8")
        assert "theorem smoke_trivial" in text, f"{resource.name} missing theorem marker"
        assert ":=" in text, f"{resource.name} missing Lean proof term"


def _assert_swebench_artifacts(run_id: UUID) -> None:
    """Every SWE-Bench leaf persists a parseable Python patch with add()."""
    resources = _require_named_resources(run_id, prefix="patch_", suffix=".py", expected_count=9)
    for resource in resources:
        source = Path(resource.file_path).read_bytes().decode("utf-8")
        module = ast.parse(source, filename=resource.name)
        function_names = {
            node.name for node in ast.walk(module) if isinstance(node, ast.FunctionDef)
        }
        assert "add" in function_names, f"{resource.name} missing add() function"


def _require_named_resources(
    run_id: UUID,
    *,
    prefix: str,
    suffix: str,
    expected_count: int,
) -> list[RunResource]:
    with get_session() as s:
        resources = list(
            s.exec(
                select(RunResource)
                .where(RunResource.run_id == run_id)
                .where(
                    RunResource.name.like(f"{prefix}%{suffix}"),  # ty: ignore[unresolved-attribute]
                ),
            ).all(),
        )
    assert len(resources) == expected_count, (
        f"expected {expected_count} {prefix}*{suffix} resources, got {len(resources)}"
    )
    missing_hash = [resource.name for resource in resources if not resource.content_hash]
    assert not missing_hash, f"resources missing content_hash: {missing_hash}"
    return resources


def _assert_temporal_ordering(run_id: UUID) -> None:
    """Schedule honours DAG deps: children start no earlier than parents finish.

    Uses ``RunTaskExecution.started_at`` / ``completed_at`` via
    ``node_id`` join.  Only checks edges whose both endpoints reached
    at least ``started`` state. Blocked descendants are skipped because
    they should never have execution timestamps.
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
    """Canonical sad path: l_2 fails, l_3 blocks, independent leaves complete."""
    snapshot = require_run_snapshot(run_id)
    tasks = list(snapshot.tasks.values())
    leaves = [task for task in tasks if task.level > 0]
    root_tasks = [task for task in tasks if task.level == 0]
    by_slug = {task.name: task for task in leaves}
    assert len(root_tasks) == 1, f"expected 1 root task, got {len(root_tasks)}"
    assert root_tasks[0].status != COMPLETED, (
        f"parent task should not complete when a child fails, got {root_tasks[0].status}"
    )
    assert by_slug["l_2"].status == FAILED, f"l_2 expected FAILED, got {by_slug['l_2'].status}"
    assert by_slug["l_3"].status == BLOCKED, f"l_3 expected BLOCKED, got {by_slug['l_3'].status}"
    assert by_slug["l_3"].started_at is None, "blocked l_3 should never start"
    assert not snapshot.executions_by_task.get(by_slug["l_3"].id), (
        "blocked l_3 should not have execution attempts"
    )
    for slug in set(EXPECTED_SUBTASK_SLUGS) - {"l_2", "l_3"}:
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
    """Sad path sends messages for the 7 completed leaves only."""
    snapshot = require_run_snapshot(run_id)
    thread = next(
        (thread for thread in snapshot.threads if thread.topic == "smoke-completion"), None
    )
    assert thread is not None, "no smoke-completion thread created"
    msgs = sorted(thread.messages, key=lambda msg: msg.sequence_num)
    assert len(msgs) == 7, f"expected 7 completion messages (l_2 failed, l_3 blocked), got {len(msgs)}"
    from_slugs = {m.from_agent_id.removeprefix("leaf-") for m in msgs}
    assert "l_2" not in from_slugs, (
        f"l_2 sent a completion message despite suppression: {from_slugs}"
    )
    assert "l_3" not in from_slugs, (
        f"l_3 sent a completion message despite being blocked: {from_slugs}"
    )
    assert from_slugs == set(EXPECTED_SUBTASK_SLUGS) - {"l_2", "l_3"}


def _assert_sadpath_evaluation(run_id: UUID) -> None:
    """Sad-path run should not produce a successful final score."""
    snapshot = require_run_snapshot(run_id)
    assert snapshot.final_score in (None, 0.0)


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
