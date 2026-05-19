"""Dead-path audit: v1 helpers that were wired up to nothing must stay
callerless until their deletion PR.

The v1 audit found multiple helpers (saved_specs, Worker.from_buffer,
CriterionExecutor, etc.) that production code never invoked. This file
asserts they stay callerless. Each case is xfail(strict=True) until the
listed landing PR deletes the last production reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOTS = (
    ROOT / "ergon_core" / "ergon_core",
    ROOT / "ergon_builtins" / "ergon_builtins",
    ROOT / "ergon_cli" / "ergon_cli",
)
EXEMPT_PARTS: frozenset[str] = frozenset({"tests", "migrations", "__pycache__"})


def _grep_production_callers(symbol: str) -> list[str]:
    hits: list[str] = []
    for root in PRODUCTION_ROOTS:
        for path in root.rglob("*.py"):
            if EXEMPT_PARTS.intersection(path.parts):
                continue
            if symbol in path.read_text():
                hits.append(str(path.relative_to(ROOT)))
    return sorted(hits)


@dataclass(frozen=True)
class DeadPath:
    symbol: str
    landing_pr: str
    audit_note: str


DEAD_PATHS: tuple[DeadPath, ...] = (
    DeadPath(
        symbol="saved_specs",
        landing_pr="PR 11",
        audit_note="v1 wrote, nothing read",
    ),
    DeadPath(
        symbol="Worker.from_buffer",
        landing_pr="PR 11",
        audit_note="constructor with zero callers",
    ),
    DeadPath(
        symbol="CriterionExecutor",
        landing_pr="PR 11",
        audit_note=(
            "Protocol with one trivial impl; reshaped eval calls evaluator.evaluate directly"
        ),
    ),
    DeadPath(
        symbol="InngestCriterionExecutor",
        landing_pr="PR 11",
        audit_note="trivial impl removed with the Protocol",
    ),
    DeadPath(
        symbol="_prepare_definition",
        landing_pr="PR 3",
        audit_note="renamed to _prepare_legacy_definition in PR 3",
    ),
    DeadPath(
        symbol="_prepare_legacy_definition",
        landing_pr="PR 11",
        audit_note="transitional name; deleted by PR 11",
    ),
    DeadPath(
        symbol="_prepare_legacy_graph_native",
        landing_pr="PR 11",
        audit_note=(
            "PR 3 renamed _prepare_graph_native; the legacy method is "
            "kept callerless for rollback and deleted by PR 11"
        ),
    ),
    DeadPath(
        symbol="materialize_dynamic_subtask_definition",
        landing_pr="PR 9",
        audit_note=("synthesized definition row for dynamic spawn; graph-native replaces it"),
    ),
    DeadPath(
        symbol="terminate_sandbox_by_id",
        landing_pr="PR 11",
        audit_note="legacy cleanup helper; sandbox_cleanup is the only production owner",
    ),
    DeadPath(
        symbol="_persist_single_sample_workflow_definition",
        landing_pr="PR 8",
        audit_note=("v1 CLI write to saved_specs; replaced by canonical persist_benchmark"),
    ),
    DeadPath(
        symbol="legacy_worker_from_payload",
        landing_pr="PR 11",
        audit_note=(
            "PR 3 in-body bridge (`_worker_from_payload_bridge`); PR 5 "
            "moved the legacy fallback to `_legacy_worker_bridge.py` "
            "(sibling module) and renamed the function to "
            "`legacy_worker_from_payload` while benchmarks migrate. "
            "PR 11 deletes both the sibling and the if-worker-is-None "
            "branch in worker_execute."
        ),
    ),
    DeadPath(
        symbol="_DetachableSandboxBridge",
        landing_pr="PR 5",
        audit_note="PR 4 bridge; lifted into Sandbox.detach() base method",
    ),
    # --- Components/registry layer that v2 retires ---
    DeadPath(
        symbol="ComponentCatalogService",
        landing_pr="PR 11",
        audit_note=(
            "Registry-driven runtime resolution; replaced by object-bound "
            "task.worker / task.sandbox / task.evaluators"
        ),
    ),
    DeadPath(
        symbol="DefinitionRepository",
        landing_pr="PR 11",
        audit_note=(
            "Runtime read path into definition tables; replaced by "
            "graph_repo.node reading run-tier task_json"
        ),
    ),
    # --- Renamed symbols whose old name must disappear ---
    DeadPath(
        symbol="Worker.validate",
        landing_pr="PR 11",
        audit_note="Renamed to validate_runtime_deps in PR 5",
    ),
    # --- Domain Experiment retired in favor of public Experiment ---
    DeadPath(
        symbol="ergon_core.core.domain.experiments.Experiment",
        landing_pr="PR 11",
        audit_note="Replaced by ergon_core.api.experiment.Experiment in PR 5",
    ),
    # --- DTO fields that PR 11 drops from PreparedTaskExecution ---
    DeadPath(
        symbol="PreparedTaskExecution.node_id",
        landing_pr="PR 11",
        audit_note="Identity collapses to task_id only",
    ),
    DeadPath(
        symbol="PreparedTaskExecution.task_id",
        landing_pr="PR 11",
        audit_note="Identity collapses to task_id only",
    ),
    DeadPath(
        symbol="PreparedTaskExecution.worker_type",
        landing_pr="PR 11",
        audit_note="Worker resolved from task.worker after PR 5",
    ),
    DeadPath(
        symbol="PreparedTaskExecution.assigned_worker_slug",
        landing_pr="PR 11",
        audit_note="Worker resolved from task.worker after PR 5",
    ),
    # --- Run-graph column collapses ---
    DeadPath(
        symbol="parent_node_id",
        landing_pr="PR 11",
        audit_note="Renamed to parent_task_id in PR 11 schema reset",
    ),
    DeadPath(
        symbol="source_node_id",
        landing_pr="PR 11",
        audit_note="Renamed to source_task_id in PR 11 schema reset",
    ),
    DeadPath(
        symbol="target_node_id",
        landing_pr="PR 11",
        audit_note="Renamed to target_task_id in PR 11 schema reset",
    ),
)


# Only symbols that have at least one production caller TODAY appear here.
# When a transitional symbol is *introduced* by a later PR (e.g.
# `_DetachableSandboxBridge` in PR 4), that PR's flip step adds the
# corresponding entry; the deletion PR removes it. Currently-callerless
# symbols listed in `DEAD_PATHS` (e.g. names not yet present in v1, or
# names already cleaned up) are still asserted every run — they just
# pass without xfail because they're already in the desired state.
_XFAIL_BY_SYMBOL: dict[str, str] = {}


def _cases() -> list:
    cases = []
    for dp in DEAD_PATHS:
        marks = []
        reason = _XFAIL_BY_SYMBOL.get(dp.symbol)
        if reason is not None:
            marks.append(pytest.mark.xfail(reason=reason, strict=True))
        cases.append(pytest.param(dp, marks=marks, id=dp.symbol))
    return cases


@pytest.mark.parametrize("dead_path", _cases())
def test_dead_path_has_no_production_callers(dead_path: DeadPath) -> None:
    callers = _grep_production_callers(dead_path.symbol)
    assert callers == [], (
        f"{dead_path.symbol!r} is on the deletion list "
        f"(lands {dead_path.landing_pr}; audit note: {dead_path.audit_note}) "
        f"but still has production callers: {callers}"
    )
