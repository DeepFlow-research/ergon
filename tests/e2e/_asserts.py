"""Shared assertion helpers for canonical smoke drivers.

Per-run helpers take a single ``sample_id`` and are called in a loop for
each experiment-group member.  No "at-least-one-passed" fallbacks; each
run must pass every check independently.  Experiment-group helpers take
the experiment key + sample_id list.

See docs/superpowers/plans/test-refactor/02-drivers-and-asserts.md §2
and §10 for the full catalogue.

Persistence-specific reads live behind ``ergon_core.test_support`` so
these e2e assertions stay stable while private core modules move.
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import time
from typing import Literal
from uuid import UUID

import httpx
from ergon_core.core.views.rl.episode import RlEpisodeReadService
from ergon_core.core.views.rl.projections import RlProjectionService
from ergon_core.core.views.samples.models import SampleTaskDto
from ergon_core.test_support.e2e_read_helpers import (
    ObservedSampleRuntimeEvent,
    ObservedSampleRuntimeEventStream,
    ResourceSnapshot,
    first_probe_resource,
    leaf_execution_timings_by_slug,
    list_named_resources,
    list_root_execution_and_evaluations,
    list_sandbox_command_wal,
    list_sandbox_events,
    read_sample_runtime_event_stream,
    read_resource_bytes,
)
from tests.fixtures.smoke_components.smoke_base.constants import (
    ARTIFACT_SUMMARY_SLUG,
    ENV_PROBE_SLUG,
    EXPECTED_RESOURCE_HANDOFF,
    EXPECTED_SMOKE_LOGPROBS,
    EXPECTED_SMOKE_TOKEN_IDS,
    EXPECTED_SUBTASK_SLUGS,
    EXPECTED_SUBAGENT_INTERNAL_MARKER,
    EXPECTED_PARENT_VISIBLE_CHILD_RESULT,
    HANDOFF_RESOURCE_NAME,
    HANDOFF_VERIFY_SLUG,
    METADATA_REVIEW_SLUG,
    METADATA_VALIDATE_SLUG,
    NESTED_INSPECT_SLUG,
    NESTED_LINE_SLUGS,
    NESTED_VERIFY_SLUG,
    PRIMARY_ARTIFACT_SLUG,
    SEEDED_SOURCE_DOC_NAME,
    SOURCE_REVIEW_SLUG,
)

from tests.e2e._read_contracts import require_run_snapshot

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
BLOCKED = "blocked"
COMPLETED = "completed"
FAILED = "failed"
SMOKE_PARENT_TURN_COUNT = 3
SMOKE_RECURSIVE_TURN_COUNT = 3
SMOKE_LEAF_TURN_COUNT = 2


# =============================================================================
# Run-level helpers (happy path)
# =============================================================================


def _assert_sample_graph(sample_id: UUID) -> None:
    """Happy path: root + 9 direct children + 2 nested children; all COMPLETED."""
    snapshot = require_run_snapshot(sample_id)
    tasks = list(snapshot.tasks.values())
    by_slug = {task.name: task for task in tasks}
    root_tasks = [task for task in tasks if task.level == 0]

    assert snapshot.total_tasks == 12, f"expected 12 tasks, got {snapshot.total_tasks}"
    assert snapshot.total_leaf_tasks == 10, (
        f"expected 10 leaf tasks, got {snapshot.total_leaf_tasks}"
    )
    assert len(root_tasks) == 1, f"expected 1 root task, got {len(root_tasks)}"
    assert snapshot.root_task_id == root_tasks[0].id
    assert sorted(task.name for task in tasks if task.level == 1) == sorted(
        EXPECTED_SUBTASK_SLUGS,
    )
    assert sorted(task.name for task in tasks if task.level == 2) == sorted(NESTED_LINE_SLUGS)
    assert by_slug[ENV_PROBE_SLUG].is_leaf is False
    assert by_slug[NESTED_INSPECT_SLUG].parent_id == by_slug[ENV_PROBE_SLUG].id
    assert by_slug[NESTED_VERIFY_SLUG].parent_id == by_slug[ENV_PROBE_SLUG].id
    non_completed = [(task.name, task.status) for task in tasks if task.status != COMPLETED]
    assert not non_completed, f"non-completed nodes: {non_completed}"

    _assert_dag_edges(tasks)


def _assert_dag_edges(leaves: list[SampleTaskDto]) -> None:
    """Verify each dependency edge is exposed by the read-service task DTO."""
    by_id = {task.id: task for task in leaves}
    actual_pairs = {
        (by_id[parent_id].name, task.name)
        for task in leaves
        for parent_id in task.depends_on_ids
        if parent_id in by_id
    }
    expected_pairs = {
        (SOURCE_REVIEW_SLUG, HANDOFF_VERIFY_SLUG),
        (SOURCE_REVIEW_SLUG, PRIMARY_ARTIFACT_SLUG),
        (HANDOFF_VERIFY_SLUG, ARTIFACT_SUMMARY_SLUG),
        (PRIMARY_ARTIFACT_SLUG, ARTIFACT_SUMMARY_SLUG),
        (METADATA_REVIEW_SLUG, ENV_PROBE_SLUG),
        (ENV_PROBE_SLUG, METADATA_VALIDATE_SLUG),
        (NESTED_INSPECT_SLUG, NESTED_VERIFY_SLUG),
    }
    missing = expected_pairs - actual_pairs
    assert not missing, f"missing DAG edges: {missing}"


def _assert_sample_resources(sample_id: UUID) -> None:
    """Expected task resources include artifacts, probes, toolkit probes, and handoff files."""
    snapshot = require_run_snapshot(sample_id)
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
    assert len(probes) == 10, f"expected 10 probe_*.json (kind=report) resources, got {len(probes)}"
    worker_outputs = [resource for resource in resources if resource.name == "worker_output"]
    assert not worker_outputs, (
        "worker final assistant messages must stay on executions, not resources"
    )
    toolkit_probes = [
        resource
        for resource in resources
        if resource.name.startswith("toolkit_probe_") and resource.name.endswith(".json")
    ]
    assert len(toolkit_probes) == 10, (
        f"expected 10 toolkit_probe_*.json resources, got {len(toolkit_probes)}"
    )
    names = {resource.name for resource in resources}
    assert SEEDED_SOURCE_DOC_NAME in names
    assert HANDOFF_RESOURCE_NAME in names
    assert len(resources) == 32, (
        f"expected 32 task artifact resources "
        f"(10 outputs + 10 probes + 10 toolkit probes + source/handoff), got {len(resources)}"
    )


def _assert_run_turn_counts(sample_id: UUID) -> None:
    """Parent + recursive ``environment-probe`` + artifact leaves emit fixed chunk counts.

    Each smoke context chunk contains one assistant text part, so persistence
    emits exactly one ``SampleContextEvent`` per chunk.
    """
    leaf_count = len(EXPECTED_SUBTASK_SLUGS) - 1 + len(NESTED_LINE_SLUGS)
    expected = (
        SMOKE_PARENT_TURN_COUNT + SMOKE_RECURSIVE_TURN_COUNT + leaf_count * SMOKE_LEAF_TURN_COUNT
    )  # currently 3 + 3 + 10×2 = 26

    snapshot = require_run_snapshot(sample_id)
    event_count = sum(len(events) for events in snapshot.context_events_by_task.values())

    assert event_count == expected, (
        f"turn count mismatch: expected {expected} "
        f"(parent={SMOKE_PARENT_TURN_COUNT}, "
        f"recursive={SMOKE_RECURSIVE_TURN_COUNT}, "
        f"leaves={leaf_count}×{SMOKE_LEAF_TURN_COUNT}), got {event_count}"
    )


def _assert_run_evaluation(sample_id: UUID) -> None:
    """Exactly 2 root SampleTaskEvaluation rows with score 1.0.

    Retries for up to 30 s because the evaluator invocations land
    asynchronously even though PR 4's ``execute_task`` fanout is
    synchronous within the orchestrator. The second evaluator is the
    root timing marker.

    Note on ordering: pre-PR-4 the evaluator was a sibling Inngest
    function triggered by ``task/completed``, so evaluations were
    written strictly after ``SampleTaskAttempt.completed_at``. PR 4
    moved fanout inside ``execute_task`` via ``ctx.group.parallel``
    after ``persist_outputs`` returns, so evaluation rows are written
    *before* ``finalize_success`` stamps ``completed_at``. The
    ordering invariant the assertion enforces is now structural — the
    orchestrator only fans out after worker output has been persisted
    — and the temporal check against ``completed_at`` no longer
    captures that. The retained checks (count, scores, snapshot DTOs)
    cover the observable contract.
    """
    deadline = time.monotonic() + 30
    evaluations = []
    root_execution = None
    while time.monotonic() < deadline:
        root_execution, evaluations = list_root_execution_and_evaluations(sample_id)
        if len(evaluations) == 2:
            break
        time.sleep(2)
    assert root_execution is not None, "expected root task execution"
    assert root_execution.completed_at is not None, "expected root execution completed_at"
    assert len(evaluations) == 2, f"expected 2 root task evaluations, got {len(evaluations)}"
    scores = [evaluation.score for evaluation in evaluations]
    assert scores == [1.0, 1.0], f"expected two score 1.0 evaluations, got {scores}"
    snapshot = require_run_snapshot(sample_id)
    assert snapshot.final_score == 1.0
    snapshot_evaluations = list(snapshot.evaluations_by_task.values())
    assert snapshot_evaluations, "expected run snapshot evaluation DTOs"
    for dto in snapshot_evaluations:
        assert dto.evaluator_name, "evaluation DTO must expose evaluator_name"
        assert dto.aggregation_rule, "evaluation DTO must expose aggregation_rule"
        for criterion in dto.criterion_results:
            assert criterion.criterion_name, "criterion must expose criterion_name"
            assert criterion.status in {"passed", "failed", "errored", "skipped"}
            assert criterion.weight >= 0
            assert criterion.contribution >= 0


def _assert_handoff_task_evaluation(sample_id: UUID) -> None:
    deadline = time.monotonic() + 30
    evaluation = None
    consumer = None
    while time.monotonic() < deadline:
        snapshot = require_run_snapshot(sample_id)
        consumer = next(
            (task for task in snapshot.tasks.values() if task.name == HANDOFF_VERIFY_SLUG),
            None,
        )
        if consumer is not None:
            evaluation = snapshot.evaluations_by_task.get(consumer.id)
            if evaluation is not None:
                break
        time.sleep(2)

    assert consumer is not None, f"expected {HANDOFF_VERIFY_SLUG} task in snapshot"
    assert evaluation is not None, f"expected evaluation for {HANDOFF_VERIFY_SLUG}"
    assert evaluation.normalized_score == 1.0
    criterion_slugs = {criterion.criterion_slug for criterion in evaluation.criterion_results}
    assert criterion_slugs == {"smoke-resource-handoff"}


def _assert_rl_episode_view(sample_id: UUID) -> None:
    episode = RlEpisodeReadService().get_episode(sample_id)
    assert episode.sample_id == sample_id
    assert episode.normalized_reward == 1.0
    assert len(episode.root_tasks) == 1

    tasks = _walk_rl_tasks(episode.root_tasks)
    by_slug = {task.task_slug: task for task in tasks}
    assert set(EXPECTED_SUBTASK_SLUGS) <= set(by_slug)
    assert by_slug[ENV_PROBE_SLUG].children
    assert {child.task_slug for child in by_slug[ENV_PROBE_SLUG].children} == set(NESTED_LINE_SLUGS)
    assert by_slug[HANDOFF_VERIFY_SLUG].actor is not None
    assert (
        by_slug[HANDOFF_VERIFY_SLUG].actor.parent_task_id
        == by_slug[SOURCE_REVIEW_SLUG].parent_task_id
    )

    projection = RlProjectionService()
    trajectories = list(projection.iter_task_attempt_trajectories(episode))
    assert {trajectory.task_slug for trajectory in trajectories} >= set(EXPECTED_SUBTASK_SLUGS)
    joint_timeline = projection.get_joint_timeline(episode)
    token_steps = [step for step in joint_timeline.records if step.token_metadata is not None]
    assert token_steps, "expected RL joint timeline to expose synthetic logprobs"
    first = token_steps[0].token_metadata
    assert first is not None
    assert first.token_ids == EXPECTED_SMOKE_TOKEN_IDS
    assert [item.logprob for item in first.logprobs or []] == EXPECTED_SMOKE_LOGPROBS


def _walk_rl_tasks(tasks) -> list:
    result = []
    for task in tasks:
        result.append(task)
        result.extend(_walk_rl_tasks(task.children))
    return result


# =============================================================================
# Observability helpers (run-level)
# =============================================================================


def _assert_sandbox_command_wal(sample_id: UUID) -> None:
    """Bash commands land as WAL rows via ``PostgresSandboxEventSink``."""
    entries = list_sandbox_command_wal(sample_id)
    probes = [e for e in entries if "wc" in e.command or "probe" in e.command]
    # Canonical sad-path smokes block metadata-validate before it starts, so
    # executed leaves should emit probe commands while the blocked node emits none.
    assert len(probes) >= 8, f"expected ≥8 probe WAL entries, got {len(probes)}"


def _assert_sandbox_lifecycle_events(sample_id: UUID) -> None:
    """``sandbox_created`` + ``sandbox_closed`` symmetric per sandbox."""
    deadline = time.monotonic() + 30
    events = []
    while time.monotonic() < deadline:
        events = list_sandbox_events(sample_id)
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


def _assert_thread_messages_ordered(sample_id: UUID) -> None:
    """11 completion messages on the ``smoke-completion`` thread."""
    snapshot = require_run_snapshot(sample_id)
    threads = [thread for thread in snapshot.threads if thread.topic == "smoke-completion"]
    assert len(threads) == 1, f"expected 1 smoke-completion thread, got {len(threads)}"
    msgs = sorted(threads[0].messages, key=lambda msg: msg.sequence_num)
    assert len(msgs) == 11, f"expected 11 completion messages, got {len(msgs)}"
    assert [m.sequence_num for m in msgs] == list(range(1, 12))
    from_slugs = {m.from_agent_id.removeprefix("leaf-") for m in msgs}
    assert from_slugs == set(EXPECTED_SUBTASK_SLUGS) | set(NESTED_LINE_SLUGS), (
        f"from_agent_id slug set mismatch: {sorted(from_slugs)}"
    )
    assert all(m.to_agent_id == "parent" for m in msgs)
    assert all(m.task_attempt_id is not None for m in msgs)


def _assert_blob_roundtrip(sample_id: UUID) -> None:
    """Read one probe JSON artifact from disk; confirm it parses and
    is byte-stable across two reads.

    Uses ``kind='report'`` resources because those are written to the
    content-addressed blob store (``ERGON_BLOB_ROOT``) which is bind-mounted
    at the same path on both the host and inside the API container.  The
    direct ``kind='output'`` rows store container-internal download paths
    that are not directly accessible from the host-side test process.
    """
    row = first_probe_resource(sample_id)
    assert row is not None, "no probe_*.json (kind=report) to round-trip"
    assert row.content_hash
    bytes_a = read_resource_bytes(row)
    bytes_b = read_resource_bytes(row)
    assert bytes_a == bytes_b, "blob read non-deterministic"
    parsed = json.loads(bytes_a)
    assert "exit_code" in parsed, f"probe JSON missing exit_code: {parsed!r}"


def _assert_toolkit_probe_resources(
    sample_id: UUID,
    *,
    expected_toolkit_suffix: str,
) -> None:
    resources = _require_named_resources(
        sample_id,
        prefix="toolkit_probe_",
        suffix=".json",
        expected_count=10,
    )
    for resource in resources:
        payload = json.loads(read_resource_bytes(resource))
        assert payload["ok"] is True, f"{resource.name} toolkit probe failed: {payload!r}"
        assert payload["toolkit"].endswith(expected_toolkit_suffix)
        assert payload["synthetic_token_ids"] == EXPECTED_SMOKE_TOKEN_IDS
        assert payload["synthetic_logprobs"] == EXPECTED_SMOKE_LOGPROBS
        assert payload["internal_marker"] == EXPECTED_SUBAGENT_INTERNAL_MARKER
        assert payload["parent_visible_marker"] == EXPECTED_PARENT_VISIBLE_CHILD_RESULT


def _assert_source_handoff_resource(sample_id: UUID) -> None:
    resources = _require_named_resources(
        sample_id,
        prefix=HANDOFF_RESOURCE_NAME,
        suffix="",
        expected_count=1,
    )
    payload = json.loads(read_resource_bytes(resources[0]))
    assert payload["producer_slug"] == EXPECTED_RESOURCE_HANDOFF.producer_slug
    assert payload["consumer_slug"] == EXPECTED_RESOURCE_HANDOFF.consumer_slug
    assert payload["source_doc"] == SEEDED_SOURCE_DOC_NAME


def _assert_minif2f_artifacts(sample_id: UUID) -> None:
    """Every MiniF2F leaf persists a Lean proof artifact with the smoke theorem."""
    resources = _require_named_resources(
        sample_id, prefix="proof_", suffix=".lean", expected_count=10
    )
    for resource in resources:
        text = read_resource_bytes(resource).decode("utf-8")
        assert "theorem smoke_trivial" in text, f"{resource.name} missing theorem marker"
        assert ":=" in text, f"{resource.name} missing Lean proof term"


def _assert_swebench_artifacts(sample_id: UUID) -> None:
    """Every SWE-Bench leaf persists a parseable Python patch with add()."""
    resources = _require_named_resources(
        sample_id, prefix="patch_", suffix=".py", expected_count=10
    )
    for resource in resources:
        source = read_resource_bytes(resource).decode("utf-8")
        module = ast.parse(source, filename=resource.name)
        function_names = {
            node.name for node in ast.walk(module) if isinstance(node, ast.FunctionDef)
        }
        assert "add" in function_names, f"{resource.name} missing add() function"


def _require_named_resources(
    sample_id: UUID,
    *,
    prefix: str,
    suffix: str,
    expected_count: int,
) -> list[ResourceSnapshot]:
    resources = list_named_resources(sample_id, prefix=prefix, suffix=suffix)
    assert len(resources) == expected_count, (
        f"expected {expected_count} {prefix}*{suffix} resources, got {len(resources)}"
    )
    missing_hash = [resource.name for resource in resources if not resource.content_hash]
    assert not missing_hash, f"resources missing content_hash: {missing_hash}"
    return resources


def _assert_temporal_ordering(sample_id: UUID) -> None:
    """Schedule honours DAG deps: children start no earlier than parents finish.

    Uses ``SampleTaskAttempt.started_at`` / ``completed_at`` via
    ``task_id`` join.  Only checks edges whose both endpoints reached
    at least ``started`` state. Blocked descendants are skipped because
    they should never have execution timestamps.
    """
    slug_exec = leaf_execution_timings_by_slug(sample_id)

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

    _after(ARTIFACT_SUMMARY_SLUG, [HANDOFF_VERIFY_SLUG, PRIMARY_ARTIFACT_SLUG])
    _after(HANDOFF_VERIFY_SLUG, [SOURCE_REVIEW_SLUG])
    _after(PRIMARY_ARTIFACT_SLUG, [SOURCE_REVIEW_SLUG])
    _after(ENV_PROBE_SLUG, [METADATA_REVIEW_SLUG])
    _after(METADATA_VALIDATE_SLUG, [ENV_PROBE_SLUG])


SMOKE_DIRECT_EDGES = (
    (SOURCE_REVIEW_SLUG, HANDOFF_VERIFY_SLUG),
    (SOURCE_REVIEW_SLUG, PRIMARY_ARTIFACT_SLUG),
    (HANDOFF_VERIFY_SLUG, ARTIFACT_SUMMARY_SLUG),
    (PRIMARY_ARTIFACT_SLUG, ARTIFACT_SUMMARY_SLUG),
    (METADATA_REVIEW_SLUG, ENV_PROBE_SLUG),
    (ENV_PROBE_SLUG, METADATA_VALIDATE_SLUG),
)
SMOKE_NESTED_EDGES = ((NESTED_INSPECT_SLUG, NESTED_VERIFY_SLUG),)


def _assert_sample_runtime_event_stream(
    sample_id: UUID,
    *,
    profile: Literal["happy", "sad"],
    worker_prefix: str,
    root_worker_slug: str,
) -> None:
    snapshot = read_sample_runtime_event_stream(sample_id)
    sample_snapshot = require_run_snapshot(sample_id)
    root_slug = sample_snapshot.tasks[sample_snapshot.root_task_id].name

    expected_task_slugs = (
        (root_slug, *EXPECTED_SUBTASK_SLUGS, *NESTED_LINE_SLUGS)
        if profile == "happy"
        else (root_slug, *EXPECTED_SUBTASK_SLUGS)
    )
    expected_edge_pairs = (
        (*SMOKE_DIRECT_EDGES, *SMOKE_NESTED_EDGES) if profile == "happy" else SMOKE_DIRECT_EDGES
    )
    expected_status_sequence = (
        ("pending", "executing", "completed")
        if profile == "happy"
        else ("pending", "executing", "failed")
    )
    expected_terminal_status_by_slug = {slug: "completed" for slug in expected_task_slugs}
    if profile == "sad":
        expected_terminal_status_by_slug[ENV_PROBE_SLUG] = "failed"
        expected_terminal_status_by_slug[METADATA_VALIDATE_SLUG] = "blocked"

    expected_workers = {slug: f"{worker_prefix}-smoke-leaf" for slug in expected_task_slugs}
    expected_workers[root_slug] = root_worker_slug
    if profile == "happy":
        expected_workers[ENV_PROBE_SLUG] = f"{worker_prefix}-smoke-recursive-worker"
        expected_workers[NESTED_INSPECT_SLUG] = f"{worker_prefix}-smoke-leaf"
        expected_workers[NESTED_VERIFY_SLUG] = f"{worker_prefix}-smoke-leaf"
    else:
        expected_workers[ENV_PROBE_SLUG] = f"{worker_prefix}-smoke-leaf-failing"

    assert snapshot.status_sequence == expected_status_sequence
    assert snapshot.task_added_slugs == expected_task_slugs
    assert snapshot.edge_added_pairs == expected_edge_pairs
    assert snapshot.worker_added_by_task_slug == expected_workers
    assert set(snapshot.sandbox_added_by_task_slug) == set(expected_task_slugs)
    assert set(snapshot.evaluator_added_by_task_slug) == {root_slug, HANDOFF_VERIFY_SLUG}
    assert set(snapshot.evaluator_added_by_task_slug[root_slug]) == {"default", "post-root"}
    assert set(snapshot.evaluator_added_by_task_slug[HANDOFF_VERIFY_SLUG]) == {
        "smoke-resource-handoff"
    }
    assert snapshot.task_terminal_status_by_slug == expected_terminal_status_by_slug
    if profile == "happy":
        assert NESTED_INSPECT_SLUG in snapshot.task_added_slugs
        assert NESTED_VERIFY_SLUG in snapshot.task_added_slugs
    else:
        assert NESTED_INSPECT_SLUG not in snapshot.task_added_slugs
        assert NESTED_VERIFY_SLUG not in snapshot.task_added_slugs

    _assert_sample_runtime_event_order(snapshot, root_slug=root_slug)


def _assert_sample_runtime_event_order(
    snapshot: ObservedSampleRuntimeEventStream,
    *,
    root_slug: str,
) -> None:
    ordered = snapshot.ordered_events
    assert ordered, "expected typed sample runtime WAL events"
    assert ordered == tuple(sorted(ordered, key=lambda event: (event.event_timestamp, event.id)))
    pending_sample_status = _event_index(
        ordered,
        event_table="sample_status_events",
        event_type="sample.status_changed",
        status="pending",
    )

    first_executing = _event_index(
        ordered,
        event_table="sample_status_events",
        event_type="sample.status_changed",
        status="executing",
    )
    assert pending_sample_status < first_executing
    final_sample_status = max(
        i for i, event in enumerate(ordered) if event.event_table == "sample_status_events"
    )

    task_add_index = {
        event.task_slug: i for i, event in enumerate(ordered) if event.event_type == "task.added"
    }

    assert task_add_index[root_slug] < first_executing
    for slug in EXPECTED_SUBTASK_SLUGS:
        assert task_add_index[slug] > first_executing

    for i, event in enumerate(ordered):
        if event.event_type in {"worker.added", "sandbox.added", "evaluator.added"}:
            assert event.task_slug is not None
            assert event.task_slug in task_add_index
        if event.event_type == "edge.added":
            assert event.source_task_slug is not None
            assert event.target_task_slug is not None
            assert event.source_task_slug in task_add_index
            assert event.target_task_slug in task_add_index
        if event.event_type == "task.status_changed" and event.status in {
            "completed",
            "failed",
            "blocked",
            "cancelled",
        }:
            assert event.task_slug is not None
            assert task_add_index[event.task_slug] < i
            assert i < final_sample_status


def _event_index(
    ordered: tuple[ObservedSampleRuntimeEvent, ...],
    *,
    event_table: str,
    event_type: str,
    status: str | None = None,
) -> int:
    for i, event in enumerate(ordered):
        if (
            event.event_table == event_table
            and event.event_type == event_type
            and (status is None or event.status == status)
        ):
            return i
    raise AssertionError(
        f"missing event table={event_table!r} type={event_type!r} status={status!r}"
    )


# =============================================================================
# Experiment-group helpers
# =============================================================================


def _assert_experiment_membership(experiment: str, sample_ids: list[UUID]) -> None:
    """Runs are visible via the experiment-group test-harness endpoint."""
    api_base = os.environ["ERGON_API_BASE_URL"]
    r = httpx.get(
        f"{api_base}/api/__danger__/test-harness/read/experiment/{experiment}/samples",
        timeout=10.0,
    )
    r.raise_for_status()
    rows = r.json()
    returned = {UUID(row["sample_id"]) for row in rows}
    expected = set(sample_ids)
    assert expected <= returned, f"experiment group missing expected run ids: {expected - returned}"


# =============================================================================
# Sad-path helpers
# =============================================================================


def _assert_sadpath_graph_cascade(sample_id: UUID) -> None:
    """Canonical sad path: parent plans, environment-probe fails, metadata-validate blocks."""
    snapshot = require_run_snapshot(sample_id)
    tasks = list(snapshot.tasks.values())
    leaves = [task for task in tasks if task.level > 0]
    root_tasks = [task for task in tasks if task.level == 0]
    by_slug = {task.name: task for task in leaves}
    assert len(root_tasks) == 1, f"expected 1 root task, got {len(root_tasks)}"
    assert root_tasks[0].status == COMPLETED, (
        "parent task should complete after planning; child failure is represented "
        f"on the failing child and run terminal status, got {root_tasks[0].status}"
    )
    failed = by_slug[ENV_PROBE_SLUG]
    blocked = by_slug[METADATA_VALIDATE_SLUG]
    assert failed.status == FAILED, f"{ENV_PROBE_SLUG} expected FAILED, got {failed.status}"
    assert blocked.status == BLOCKED, (
        f"{METADATA_VALIDATE_SLUG} expected BLOCKED, got {blocked.status}"
    )
    assert blocked.started_at is None, f"blocked {METADATA_VALIDATE_SLUG} should never start"
    assert not snapshot.executions_by_task.get(blocked.id), (
        f"blocked {METADATA_VALIDATE_SLUG} should not have execution attempts"
    )
    for slug in set(EXPECTED_SUBTASK_SLUGS) - {ENV_PROBE_SLUG, METADATA_VALIDATE_SLUG}:
        assert by_slug[slug].status == COMPLETED, (
            f"{slug} expected COMPLETED, got {by_slug[slug].status}"
        )


def _assert_sadpath_partial_artifact(sample_id: UUID) -> None:
    """``AlwaysFailSubworker`` writes ``partial_<node>.md`` before raising.
    The runtime's persist step must still serialize it as a SampleResource."""
    deadline = time.monotonic() + 30
    partials: list[ResourceSnapshot] = []
    while time.monotonic() < deadline:
        partials = list_named_resources(sample_id, prefix="partial_", suffix=".md")
        if partials:
            break
        time.sleep(2)
    assert len(partials) == 1, (
        f"expected 1 partial artifact from {ENV_PROBE_SLUG} (partial work must persist on "
        f"FAILED leaf), got {len(partials)}"
    )
    r = partials[0]
    assert r.content_hash, "partial resource missing content_hash"
    body = read_resource_bytes(r).decode("utf-8")
    assert body.startswith("# Partial work"), f"partial artifact body unexpected: {body[:80]!r}"


def _assert_sadpath_partial_wal(sample_id: UUID) -> None:
    """Pre-failure ``wc -l partial_*`` command persists as WAL row."""
    deadline = time.monotonic() + 30
    wc = []
    while time.monotonic() < deadline:
        entries = list_sandbox_command_wal(sample_id)
        wc = [e for e in entries if "wc -l" in e.command and "partial_" in e.command]
        if wc:
            break
        time.sleep(2)
    assert len(wc) >= 1, (
        "expected ≥1 'wc -l partial_*' WAL entry from the pre-failure probe; "
        "sandbox_command path did not persist the command before the raise"
    )


def _assert_sadpath_thread_messages(sample_id: UUID) -> None:
    """Sad path sends messages for the 7 completed leaves only."""
    snapshot = require_run_snapshot(sample_id)
    thread = next(
        (thread for thread in snapshot.threads if thread.topic == "smoke-completion"), None
    )
    assert thread is not None, "no smoke-completion thread created"
    msgs = sorted(thread.messages, key=lambda msg: msg.sequence_num)
    assert len(msgs) == 7, (
        f"expected 7 completion messages ({ENV_PROBE_SLUG} failed, "
        f"{METADATA_VALIDATE_SLUG} blocked), got {len(msgs)}"
    )
    from_slugs = {m.from_agent_id.removeprefix("leaf-") for m in msgs}
    assert ENV_PROBE_SLUG not in from_slugs, (
        f"{ENV_PROBE_SLUG} sent a completion message despite suppression: {from_slugs}"
    )
    assert METADATA_VALIDATE_SLUG not in from_slugs, (
        f"{METADATA_VALIDATE_SLUG} sent a completion message despite being blocked: {from_slugs}"
    )
    assert from_slugs == set(EXPECTED_SUBTASK_SLUGS) - {
        ENV_PROBE_SLUG,
        METADATA_VALIDATE_SLUG,
    }


def _assert_sadpath_evaluation(sample_id: UUID) -> None:
    """Sad-path run should not be mistaken for a successful run."""
    snapshot = require_run_snapshot(sample_id)
    assert snapshot.status == "failed"


# =============================================================================
# Polling helpers
# =============================================================================


async def wait_for_terminal(sample_id: UUID, timeout_seconds: int = 270) -> str:
    """Poll the harness read endpoint until the run reaches a terminal state."""
    return await wait_for_terminal_status(
        sample_id,
        expected_statuses=frozenset({"completed"}),
        timeout_seconds=timeout_seconds,
    )


async def wait_for_terminal_status(
    sample_id: UUID,
    *,
    expected_statuses: frozenset[str],
    timeout_seconds: int = 270,
) -> str:
    """Poll until the run reaches one of the expected terminal statuses."""
    api_base = os.environ["ERGON_API_BASE_URL"]
    deadline = time.monotonic() + timeout_seconds
    last_state: dict[str, object] | None = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        while time.monotonic() < deadline:
            r = await client.get(
                f"{api_base}/api/__danger__/test-harness/read/samples/{sample_id}/state"
            )
            if r.status_code == 200:
                state = r.json()
                last_state = state
                status = state["status"]
                if status in expected_statuses:
                    return status
                if status in TERMINAL_STATUSES:
                    raise AssertionError(
                        f"run {sample_id} reached terminal failure status {status!r}:\n"
                        f"{json.dumps(state, indent=2, sort_keys=True)}"
                    )
            await asyncio.sleep(2)
    raise TimeoutError(
        f"run {sample_id} did not reach terminal status within {timeout_seconds}s:\n"
        f"{json.dumps(last_state, indent=2, sort_keys=True)}",
    )
