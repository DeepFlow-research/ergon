"""PR 3 textual guards: the worker_execute job body must read only
from the run tier, never from definition tables.

After PR 3, `worker_execute.py` goes through `graph_repo.node(...)` to
get a typed Task; the legacy DefinitionRepository / ExperimentDefinitionTask
imports are gone. PR 11 deletes the legacy prep methods entirely.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_worker_execute_does_not_read_definition_repository() -> None:
    """`worker_execute.py` body must not import definition-tier
    symbols. PR 11's textual guard for the broader runtime is the
    final-state ledger's `worker_execute_imports_only_run_tier` check;
    this guard is the per-PR version that PR 3 flips green."""

    text = (ROOT / "ergon_core/ergon_core/core/application/jobs/worker_execute.py").read_text()
    assert "DefinitionRepository" not in text, (
        "worker_execute imports DefinitionRepository; the run-tier read "
        "boundary (Δ.2) forbids this."
    )
    assert "task_with_instance" not in text, (
        "worker_execute calls task_with_instance; the run-tier read "
        "boundary forbids definition-tier reads."
    )
    assert "ExperimentDefinitionTask" not in text, (
        "worker_execute imports ExperimentDefinitionTask; the run-tier "
        "read boundary forbids definition-tier reads."
    )
