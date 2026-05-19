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
    """CLAUDE.md guardrail: no *user-defined* `model_post_init` in core
    public API objects.

    Pydantic v2 auto-generates a `model_post_init` on any class that
    declares a `PrivateAttr` (it just initializes the private slots
    from their defaults). The guardrail's intent is to forbid
    user-defined constructors that assemble derived state from public
    fields — those hide invariants. We check the Task source text to
    distinguish auto-generation from a hand-written override.
    """

    import inspect

    from ergon_core.api.benchmark.task import Task

    source = inspect.getsource(Task)
    assert "def model_post_init" not in source, (
        "Task defines a custom model_post_init. CLAUDE.md forbids this: "
        "build derived state explicitly in constructors or factory "
        "classmethods so object construction stays inspectable."
    )


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
    # task_has_no_model_post_init: already holds today (v1 Task has no
    # model_post_init); the assertion ensures PR 5's v2 Task keeps it
    # that way. Tested every run, no xfail needed.
    # materialize_dynamic_subtask_definition_is_gone: the v1 codebase
    # doesn't currently use this symbol name. Asserted every run; PR 9
    # ensures the graph-native path doesn't reintroduce it.
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
            marks.append(pytest.mark.xfail(reason=f"{assertion.landing_pr}: {reason}", strict=True))
        cases.append(pytest.param(assertion, marks=marks, id=assertion.name))
    return cases


@pytest.mark.parametrize("assertion", _cases())
def test_v2_final_state(assertion: FinalStateAssertion) -> None:
    """One check per v2 invariant. Each is xfail(strict=True) until its
    landing PR flips the marker off in `_XFAIL_BY_NAME`."""

    assertion.check()
