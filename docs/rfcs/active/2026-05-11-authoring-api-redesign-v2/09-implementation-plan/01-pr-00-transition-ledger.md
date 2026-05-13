# PR 0 — Transition Ledger And Guard Scaffolding

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add guardrails that make temporary old paths explicit during the
v2 transition, and land the executable spec of the v2 final state as a set
of `xfail(strict=True)` invariants whose markers each subsequent PR removes.

**Architecture:** Three static, source-text architecture guards land
together:

1. **Transition ledger** (`test_v2_transition_ledger.py`) — *negative*
   ledger: "these old symbols still exist and that's intentional".
2. **Final-state ledger** (`test_v2_final_state_ledger.py`) — *positive*
   ledger: "these v2 invariants must hold at the end; each is
   `xfail(strict=True)` with its landing-PR reason until that PR flips
   the marker off". `strict=True` so an unexpected pass also fails CI —
   if a later PR lands an invariant early, we want to know.
3. **Dead-path audit** (`test_dead_path_audit.py`) — every symbol/package
   the v1 audit flagged as "wired up to nothing" has a `grep_callers`
   test asserting it stays callerless until its deletion PR.

Together, the three files act as a single-glance progress meter for the
whole program: the count of `xfail` markers shrinks monotonically as PRs
land. The PR ledger and bridge ledger in `00-program.md` stay as the
human-readable narrative; the test files are the machine-readable twin.

**Tech Stack:** pytest, pathlib, source-text architecture checks, pytest
`xfail(strict=True)`.

---

## Files

**Create:**

```text
ergon_core/tests/unit/architecture/test_v2_transition_ledger.py
ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py
ergon_core/tests/unit/architecture/test_dead_path_audit.py
```

**Modify:**

```text
docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/00-program.md
```

## Current State

These old symbols are present and intentionally transitional:

```text
TaskSpec
WorkerSpec
ComponentRegistry
BaseSandboxManager
ExperimentRecord
EvaluateTaskRunRequest
evaluate_task_run
CriterionExecutor
InngestCriterionExecutor
saved_specs
definition_task_id
Worker.from_buffer
terminate_sandbox_by_id
```

## Target State For This PR

The symbols remain in production code, but they are recorded in a test-owned
ledger. The ledger gives reviewers a single place to see whether a symbol is
still allowed or has become forbidden.

## Task 1: Add Transition Ledger Test

**Files:**

- Create: `ergon_core/tests/unit/architecture/test_v2_transition_ledger.py`

- [ ] **Step 1: Write the guard file**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SEARCH_ROOTS = (
    ROOT / "ergon_core",
    ROOT / "ergon_builtins",
    ROOT / "ergon_cli",
)


@dataclass(frozen=True)
class TransitionalSymbol:
    name: str
    owner_pr: str
    deletion_pr: str
    allowed_reason: str


TRANSITIONAL_SYMBOLS = (
    TransitionalSymbol(
        name="TaskSpec",
        owner_pr="PR 5",
        deletion_pr="PR 11",
        allowed_reason="old benchmark definitions still return TaskSpec",
    ),
    TransitionalSymbol(
        name="WorkerSpec",
        owner_pr="PR 5",
        deletion_pr="PR 11",
        allowed_reason="old Experiment composition still binds worker specs",
    ),
    TransitionalSymbol(
        name="ComponentRegistry",
        owner_pr="PR 5",
        deletion_pr="PR 11",
        allowed_reason="registry remains while old builtins are unmigrated",
    ),
    TransitionalSymbol(
        name="BaseSandboxManager",
        owner_pr="PR 6",
        deletion_pr="PR 11",
        allowed_reason="sandbox subclass migration is incremental",
    ),
    TransitionalSymbol(
        name="ExperimentRecord",
        owner_pr="PR 7",
        deletion_pr="PR 11",
        allowed_reason="read models are migrated after collapsed definitions land",
    ),
    TransitionalSymbol(
        name="EvaluateTaskRunRequest",
        owner_pr="PR 4",
        deletion_pr="PR 11",
        allowed_reason=(
            "v1 multi-field payload replaced by TaskEvaluateRequest "
            "(id-only) when PR 4 reshapes evaluate_task_run; the import "
            "shim survives until cleanup."
        ),
    ),
    TransitionalSymbol(
        name="CriterionExecutor",
        owner_pr="PR 4",
        deletion_pr="PR 11",
        allowed_reason=(
            "Protocol kept compiling during PR 4 reshape; the reshaped "
            "evaluate_task_run calls criterion.evaluate(...) directly so "
            "no executor indirection remains in production code paths."
        ),
    ),
    TransitionalSymbol(
        name="saved_specs",
        owner_pr="PR 8",
        deletion_pr="PR 11",
        allowed_reason="CLI define moves before persistence package deletion",
    ),
    TransitionalSymbol(
        name="definition_task_id",
        owner_pr="PR 1",
        deletion_pr="PR 11",
        allowed_reason="old runtime identity survives until task_id becomes canonical",
    ),
    TransitionalSymbol(
        name="from_buffer",
        owner_pr="PR 11",
        deletion_pr="PR 11",
        allowed_reason="dead Worker constructor is deleted in the cleanup PR",
    ),
    TransitionalSymbol(
        name="terminate_sandbox_by_id",
        owner_pr="PR 4",
        deletion_pr="PR 11",
        allowed_reason="old cleanup path remains until worker_execute owns release",
    ),
)


def _hits(symbol: str) -> list[str]:
    hits: list[str] = []
    for root in SEARCH_ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text()
            if symbol in text:
                hits.append(str(path.relative_to(ROOT)))
    return sorted(hits)


EXEMPT_DIR_PARTS: frozenset[str] = frozenset(
    {"tests", "migrations", "__pycache__"}
)


def _production_hits(symbol: str) -> list[str]:
    """Return production-code hits for a symbol, excluding tests and migrations."""

    hits: list[str] = []
    for root in SEARCH_ROOTS:
        for path in root.rglob("*.py"):
            if EXEMPT_DIR_PARTS.intersection(path.parts):
                continue
            text = path.read_text()
            if symbol in text:
                hits.append(str(path.relative_to(ROOT)))
    return sorted(hits)


def test_transitional_symbols_are_explicitly_ledgered() -> None:
    missing: list[str] = []
    for symbol in TRANSITIONAL_SYMBOLS:
        if not _hits(symbol.name):
            missing.append(
                f"{symbol.name} disappeared; update this ledger and the deletion docs "
                f"for {symbol.deletion_pr}"
            )
    assert missing == []


# Symbols that PR 11 expects to delete. If production code starts using any
# legacy term that is NOT in TRANSITIONAL_SYMBOLS, the v2 program has
# regressed — every transitional path must be named in the ledger.
LEGACY_PRODUCTION_TERMS: frozenset[str] = frozenset(
    {
        "TaskSpec",
        "WorkerSpec",
        "ComponentRegistry",
        "BaseSandboxManager",
        "ExperimentRecord",
        "EvaluateTaskRunRequest",
        "CriterionExecutor",
        "InngestCriterionExecutor",
        "saved_specs",
        "definition_task_id",
        "from_buffer",
        "terminate_sandbox_by_id",
        # evaluate_task_run is intentionally NOT here — it survives reshaped per Δ.4.
    }
)


def test_no_unledgered_legacy_term_appears_in_production_code() -> None:
    """Real check: a legacy term may live in production code only if ledgered."""

    ledgered = {symbol.name for symbol in TRANSITIONAL_SYMBOLS}
    offenders: list[str] = []
    for term in LEGACY_PRODUCTION_TERMS:
        if term in ledgered:
            continue
        hits = _production_hits(term)
        if hits:
            offenders.append(
                f"{term} appears in production code at {hits} but is not in "
                f"TRANSITIONAL_SYMBOLS. Either add it to the ledger with a "
                f"deletion_pr, or remove the production references."
            )
    assert offenders == [], "\n".join(offenders)
```

- [ ] **Step 2: Run the guard**

Run:

```bash
uv run pytest ergon_core/tests/unit/architecture/test_v2_transition_ledger.py -q
```

Expected: pass while old symbols are still present.

- [ ] **Step 3: Commit**

```bash
git add ergon_core/tests/unit/architecture/test_v2_transition_ledger.py \
  docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan
git commit -m "test: add v2 transition ledger guard"
```

## Task 2: Add Final-State Ledger (xfail invariants)

**Files:**

- Create: `ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py`

The final-state ledger is the executable form of the v2 deletion list and
the run-tier read boundary. One parametrized test, one case per invariant.
Each case starts `xfail(reason="<landing PR>: ...", strict=True)`; the PR
that lands the invariant removes the marker entry from `_XFAIL_BY_NAME`.

`strict=True` causes a case to fail CI if it passes without an xfail
marker (an invariant landed early without the ledger update) AND if it
fails without an xfail marker (an invariant regressed after landing). The
ledger entries below are the load-bearing v2 invariants from
[`02-persistence-layer.md`](../02-persistence-layer.md) §4 and
[`00-readme.md`](../00-readme.md) Δ.4 / Δ.7.

- [ ] **Step 1: Write the guard file**

```python
"""Executable spec of the v2 final state.

Each FinalStateAssertion is one architecture invariant that must hold once
the v2 program is complete. Invariants that have not landed yet are marked
xfail(strict=True) with their landing PR. Removing a marker is the
landing-PR signal — CI will flag any case that passes without a marker
(invariant landed early) or fails without a marker (invariant regressed).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOTS = (
    ROOT / "ergon_core" / "ergon_core",
    ROOT / "ergon_builtins" / "ergon_builtins",
    ROOT / "ergon_cli" / "ergon_cli",
)
EXEMPT_PARTS: frozenset[str] = frozenset({"tests", "migrations", "__pycache__"})


def _read(relpath: str) -> str:
    return (ROOT / relpath).read_text()


def _grep_production(symbol: str) -> list[str]:
    hits: list[str] = []
    for root in PRODUCTION_ROOTS:
        for path in root.rglob("*.py"):
            if EXEMPT_PARTS.intersection(path.parts):
                continue
            if symbol in path.read_text():
                hits.append(str(path.relative_to(ROOT)))
    return sorted(hits)


@dataclass(frozen=True)
class FinalStateAssertion:
    name: str
    landing_pr: str
    check: Callable[[], None]
    reason: str


def _assert_no_definition_repository_in_worker_execute() -> None:
    text = _read("ergon_core/ergon_core/core/application/jobs/worker_execute.py")
    assert "DefinitionRepository" not in text
    assert "task_with_instance" not in text
    assert "ExperimentDefinitionTask" not in text


def _assert_no_prepare_definition_method() -> None:
    text = _read("ergon_core/ergon_core/core/application/tasks/execution.py")
    assert "_prepare_definition" not in text
    assert "_prepare_legacy_definition" not in text


def _assert_no_materialize_dynamic_subtask_definition() -> None:
    assert _grep_production("materialize_dynamic_subtask_definition") == []


def _assert_no_criterion_executor() -> None:
    assert _grep_production("CriterionExecutor") == []
    assert _grep_production("InngestCriterionExecutor") == []


def _assert_no_saved_specs_package() -> None:
    assert not (ROOT / "ergon_core/ergon_core/core/persistence/saved_specs").exists()


def _assert_evaluate_task_run_takes_thin_payload() -> None:
    """Δ.4: evaluate_task_run survives reshaped with TaskEvaluateRequest."""

    import inspect

    from ergon_core.core.application.jobs.evaluate_task_run import evaluate_task_run

    sig = inspect.signature(evaluate_task_run)
    assert "TaskEvaluateRequest" in repr(sig), (
        "evaluate_task_run must take TaskEvaluateRequest after PR 4's reshape"
    )


def _assert_run_graph_node_has_no_definition_task_id_column() -> None:
    from ergon_core.core.persistence.graph.models import RunGraphNode

    assert "definition_task_id" not in RunGraphNode.model_fields


def _assert_task_has_no_model_post_init() -> None:
    """CLAUDE.md guardrail: no model_post_init in core public API objects."""

    from ergon_core.api.benchmark.task import Task

    assert "model_post_init" not in Task.__dict__


def _assert_worker_from_buffer_is_gone() -> None:
    from ergon_core.api.worker.worker import Worker

    assert not hasattr(Worker, "from_buffer")


def _assert_terminate_sandbox_by_id_is_gone() -> None:
    assert _grep_production("terminate_sandbox_by_id") == []


def _assert_no_check_evaluators_registration() -> None:
    text = _read("ergon_core/ergon_core/core/infrastructure/inngest/registry.py")
    assert "check_evaluators" not in text


FINAL_STATE_ASSERTIONS: tuple[FinalStateAssertion, ...] = (
    FinalStateAssertion(
        name="worker_execute_imports_only_run_tier",
        landing_pr="PR 3",
        check=_assert_no_definition_repository_in_worker_execute,
        reason="Δ.2: runtime reads only run-tier tables",
    ),
    FinalStateAssertion(
        name="evaluate_task_run_uses_thin_payload",
        landing_pr="PR 4",
        check=_assert_evaluate_task_run_takes_thin_payload,
        reason="Δ.4: per-evaluator fanout takes TaskEvaluateRequest",
    ),
    FinalStateAssertion(
        name="check_evaluators_is_unregistered",
        landing_pr="PR 4",
        check=_assert_no_check_evaluators_registration,
        reason="Δ.4: synchronous fanout replaces check_evaluators dispatch",
    ),
    FinalStateAssertion(
        name="task_has_no_model_post_init",
        landing_pr="PR 5",
        check=_assert_task_has_no_model_post_init,
        reason="CLAUDE.md: no model_post_init in public API objects",
    ),
    FinalStateAssertion(
        name="materialize_dynamic_subtask_definition_is_gone",
        landing_pr="PR 9",
        check=_assert_no_materialize_dynamic_subtask_definition,
        reason="Δ.3: dynamic subtasks are graph-native",
    ),
    FinalStateAssertion(
        name="prepare_definition_helper_is_removed",
        landing_pr="PR 11",
        check=_assert_no_prepare_definition_method,
        reason="Δ.2: no fallback to definition-tier reads",
    ),
    FinalStateAssertion(
        name="criterion_executor_is_removed",
        landing_pr="PR 11",
        check=_assert_no_criterion_executor,
        reason="Δ.7: deletion list",
    ),
    FinalStateAssertion(
        name="saved_specs_package_is_removed",
        landing_pr="PR 11",
        check=_assert_no_saved_specs_package,
        reason="Δ.7: write-only package, no readers",
    ),
    FinalStateAssertion(
        name="run_graph_node_has_no_definition_task_id_column",
        landing_pr="PR 11",
        check=_assert_run_graph_node_has_no_definition_task_id_column,
        reason="Δ.7 + identity model: task_id is the single canonical id",
    ),
    FinalStateAssertion(
        name="worker_from_buffer_is_removed",
        landing_pr="PR 11",
        check=_assert_worker_from_buffer_is_gone,
        reason="Δ.7: dead constructor with no callers",
    ),
    FinalStateAssertion(
        name="terminate_sandbox_by_id_is_removed",
        landing_pr="PR 11",
        check=_assert_terminate_sandbox_by_id_is_gone,
        reason="Δ.7: cleanup path subsumed by worker_execute.finally",
    ),
)


# When an assertion's landing PR merges, delete its entry from this dict.
# strict=True surfaces unexpected passes — if a later refactor flips an
# invariant green ahead of its landing PR, CI fails and the ledger gets
# the update at the same time.
_XFAIL_BY_NAME: dict[str, str] = {
    "worker_execute_imports_only_run_tier": "PR 3 flips worker_execute to run-tier",
    "evaluate_task_run_uses_thin_payload": "PR 4 reshapes evaluate_task_run",
    "check_evaluators_is_unregistered": "PR 4 removes check_evaluators dispatch",
    "task_has_no_model_post_init": "PR 5 introduces object-bound Task",
    "materialize_dynamic_subtask_definition_is_gone": "PR 9 makes dynamic subtasks graph-native",
    "prepare_definition_helper_is_removed": "PR 11 deletes legacy prepare path",
    "criterion_executor_is_removed": "PR 11 deletes Protocol pair",
    "saved_specs_package_is_removed": "PR 11 deletes write-only package",
    "run_graph_node_has_no_definition_task_id_column": "PR 11 drops the column",
    "worker_from_buffer_is_removed": "PR 11 deletes dead constructor",
    "terminate_sandbox_by_id_is_removed": "PR 11 deletes legacy cleanup path",
}


def _cases() -> list:
    cases = []
    for assertion in FINAL_STATE_ASSERTIONS:
        marks = []
        reason = _XFAIL_BY_NAME.get(assertion.name)
        if reason is not None:
            marks.append(
                pytest.mark.xfail(
                    reason=f"{assertion.landing_pr}: {reason}", strict=True
                )
            )
        cases.append(pytest.param(assertion, marks=marks, id=assertion.name))
    return cases


@pytest.mark.parametrize("assertion", _cases())
def test_v2_final_state(assertion: FinalStateAssertion) -> None:
    """One check per v2 invariant. Each is xfail(strict=True) until its
    landing PR flips the marker off in `_XFAIL_BY_NAME`."""

    assertion.check()
```

- [ ] **Step 2: Run the guard**

```bash
uv run pytest ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py -q
```

Expected: every case is XFAIL on PR 0 (none of the v2 cutovers have
landed yet). No XPASS, no FAIL.

## Task 3: Add Dead-Path Audit

**Files:**

- Create: `ergon_core/tests/unit/architecture/test_dead_path_audit.py`

This file is the executable form of "v1 helpers that were wired up to
nothing must stay callerless until their deletion PR removes them." It
is the textual grep counterpart to the deletion list in
[`00-program.md`](00-program.md) "Final Deleted Symbols". Each case is
xfail until the symbol's last production caller is gone.

- [ ] **Step 1: Write the guard file**

```python
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
            "Protocol with one trivial impl; reshaped eval calls "
            "evaluator.evaluate directly"
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
        symbol="materialize_dynamic_subtask_definition",
        landing_pr="PR 9",
        audit_note="synthesized definition row for dynamic spawn; graph-native replaces it",
    ),
    DeadPath(
        symbol="terminate_sandbox_by_id",
        landing_pr="PR 11",
        audit_note="legacy cleanup path; orchestrator try/finally owns release",
    ),
    DeadPath(
        symbol="_persist_single_sample_workflow_definition",
        landing_pr="PR 8",
        audit_note="v1 CLI write to saved_specs; replaced by canonical persist_definition",
    ),
    DeadPath(
        symbol="_worker_from_payload_bridge",
        landing_pr="PR 5",
        audit_note="PR 3 bridge; replaced by task.worker when object-bound API lands",
    ),
    DeadPath(
        symbol="_DetachableSandboxBridge",
        landing_pr="PR 5",
        audit_note="PR 4 bridge; lifted into Sandbox.detach() base method",
    ),
    # --- Inngest jobs that PR 4 absorbs into worker_execute ---
    DeadPath(
        symbol="execute_task",
        landing_pr="PR 11",
        audit_note=(
            "v1 orchestrator that fanned out to sandbox_setup → worker_execute → "
            "persist_outputs → check_evaluators; v2 collapses into worker_execute"
        ),
    ),
    DeadPath(
        symbol="sandbox_setup",
        landing_pr="PR 11",
        audit_note="PR 4 acquires inline in worker_execute",
    ),
    DeadPath(
        symbol="persist_outputs",
        landing_pr="PR 11",
        audit_note="PR 4 persists WorkerOutput inline before fanout",
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
        symbol="PreparedTaskExecution.definition_task_id",
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


_XFAIL_BY_SYMBOL: dict[str, str] = {
    "saved_specs": "PR 11: package deleted",
    "Worker.from_buffer": "PR 11: dead constructor deleted",
    "CriterionExecutor": "PR 11: Protocol pair deleted",
    "InngestCriterionExecutor": "PR 11: Protocol pair deleted",
    "_prepare_definition": "PR 3: renamed to _prepare_legacy_definition",
    "_prepare_legacy_definition": "PR 11: legacy prep deleted",
    "materialize_dynamic_subtask_definition": "PR 9: graph-native dynamic spawn",
    "terminate_sandbox_by_id": "PR 11: orchestrator owns release",
    "_persist_single_sample_workflow_definition": "PR 8: CLI uses persist_definition",
    "_worker_from_payload_bridge": "PR 5: task.worker replaces the bridge",
    "_DetachableSandboxBridge": "PR 5: lifted into Sandbox.detach()",
    # Inngest jobs absorbed into worker_execute by PR 4; deleted by PR 11
    "execute_task": "PR 11: worker_execute is the orchestrator",
    "sandbox_setup": "PR 11: worker_execute acquires inline",
    "persist_outputs": "PR 11: worker_execute persists inline",
    # Registry/definition layer retired by PR 11
    "ComponentCatalogService": "PR 11: object-bound task replaces registry resolution",
    "DefinitionRepository": "PR 11: runtime reads run-tier only",
    "Worker.validate": "PR 11: renamed to validate_runtime_deps in PR 5",
    "ergon_core.core.domain.experiments.Experiment": "PR 11: public Experiment replaces it",
    # PreparedTaskExecution transitional fields
    "PreparedTaskExecution.node_id": "PR 11: identity collapses to task_id",
    "PreparedTaskExecution.definition_task_id": "PR 11: identity collapses to task_id",
    "PreparedTaskExecution.worker_type": "PR 11: worker comes from task.worker",
    "PreparedTaskExecution.assigned_worker_slug": "PR 11: worker comes from task.worker",
    # Schema column renames
    "parent_node_id": "PR 11: renamed to parent_task_id",
    "source_node_id": "PR 11: renamed to source_task_id",
    "target_node_id": "PR 11: renamed to target_task_id",
}


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
```

- [ ] **Step 2: Run the guard**

```bash
uv run pytest ergon_core/tests/unit/architecture/test_dead_path_audit.py -q
```

Expected: every case is XFAIL on PR 0. As later PRs delete the last
caller of each symbol, they remove that symbol's entry from
`_XFAIL_BY_SYMBOL` in the same commit.

## Task 4: Add No-Type-Circumventors Guard

**Files:**

- Create: `ergon_core/tests/unit/architecture/test_no_type_circumventors.py`

`getattr(obj, "x", default)` and `hasattr(obj, "x")` are banned in
production code per [`07-test-strategy.md` § 0.6](../07-test-strategy.md).
The guard greps production trees and allows hits only when accompanied
by a `# typing: ...` exemption comment on the same or previous line, or
listed in `_KNOWN_EXEMPTIONS` with a landing PR.

- [ ] **Step 1: Write the guard**

```python
"""Ban getattr/hasattr in production code.

See 07-test-strategy.md § 0.6 for the policy. Exemptions live in
`_KNOWN_EXEMPTIONS`; lines with a `# typing: ...` comment immediately
above or on the same line are allowlisted (the comment names the
exemption category — see the policy doc for the allowed categories).
"""

from __future__ import annotations

import re
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

_GETATTR_RE = re.compile(r"\bgetattr\s*\(")
_HASATTR_RE = re.compile(r"\bhasattr\s*\(")
_TYPING_EXEMPTION_RE = re.compile(r"#\s*typing:")


@dataclass(frozen=True)
class Violation:
    path: str
    lineno: int
    line: str
    pattern: str


def _scan_file(path: Path) -> list[Violation]:
    violations: list[Violation] = []
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        for pat_name, pat in (("getattr", _GETATTR_RE), ("hasattr", _HASATTR_RE)):
            if not pat.search(line):
                continue
            # Same-line typing: comment exempts it.
            if _TYPING_EXEMPTION_RE.search(line):
                continue
            # Previous-line typing: comment exempts it too.
            if i > 0 and _TYPING_EXEMPTION_RE.search(lines[i - 1]):
                continue
            violations.append(
                Violation(
                    path=str(path.relative_to(ROOT)),
                    lineno=i + 1,
                    line=line.strip(),
                    pattern=pat_name,
                )
            )
    return violations


def _all_violations() -> list[Violation]:
    out: list[Violation] = []
    for root in PRODUCTION_ROOTS:
        for path in root.rglob("*.py"):
            if EXEMPT_PARTS.intersection(path.parts):
                continue
            out.extend(_scan_file(path))
    return out


# Lines that are known violators today and have a landing PR for the
# fix. Mirrors PR 0's _XFAIL_BY_NAME shape — each entry is "(relpath,
# lineno_marker_substring)": "PR N: <reason>". PR 11 asserts the dict
# is empty.
_KNOWN_EXEMPTIONS: dict[tuple[str, str], str] = {
    # Populate from the first run; one row per current violator with
    # the PR that fixes it.
}


def test_no_unexpected_type_circumventors() -> None:
    violations = _all_violations()
    unexpected: list[Violation] = []
    for v in violations:
        key = (v.path, v.line)
        # Allow if explicitly listed.
        if any(
            v.path == k_path and k_marker in v.line
            for (k_path, k_marker) in _KNOWN_EXEMPTIONS
        ):
            continue
        unexpected.append(v)
    assert unexpected == [], "\n".join(
        f"{v.path}:{v.lineno}  {v.pattern}  {v.line}" for v in unexpected
    )
```

- [ ] **Step 2: Run the guard and populate `_KNOWN_EXEMPTIONS`**

```bash
uv run pytest ergon_core/tests/unit/architecture/test_no_type_circumventors.py -q
```

The first run lists every current violator. For each, either:

- Add a `# typing: <category>` comment to the source line (legitimate
  exemption — only `dynamic qualname walk`, `<library> SDK boundary`,
  or another approved category from § 0.6).
- Add an entry to `_KNOWN_EXEMPTIONS` with the landing PR (every
  v2 fix is scheduled in this commit's sibling PRs).

After this PR lands, the guard passes; later PRs remove entries as
they land their fixes; PR 11 asserts `_KNOWN_EXEMPTIONS == {}` (only
the legitimate `# typing:`-annotated exemptions remain).

## Task 5: Commit

- [ ] **Step 1: Stage and commit all four ledgers**

```bash
git add ergon_core/tests/unit/architecture/test_v2_transition_ledger.py \
        ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py \
        ergon_core/tests/unit/architecture/test_dead_path_audit.py \
        ergon_core/tests/unit/architecture/test_no_type_circumventors.py \
        docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan
git commit -m "test: add v2 architecture ledgers (transition, final-state, dead-path, no-type-circumventors)"
```

## PR Ledger

Invariant landed: old paths are tracked; v2 final-state invariants are
executable; v1 dead paths have callerless guards.

Bridge code introduced: none.

Old path still intentionally alive: all old paths listed in
`test_v2_transition_ledger.py`.

Deletion gate: PR 11 replaces this ledger with deleted-symbol guards. The
final-state ledger and dead-path audit reach zero xfails at PR 11 — PR 11
verifies this explicitly (see PR 11 § "Verify No XFails Remain").

Tests added or updated: `test_v2_transition_ledger.py`,
`test_v2_final_state_ledger.py`, `test_dead_path_audit.py`.

Modules owned by this PR: architecture tests and docs only.
