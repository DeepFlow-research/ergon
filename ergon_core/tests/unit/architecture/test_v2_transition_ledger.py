"""v2 transition ledger — negative inventory of old symbols.

For each symbol that v2 deletes by PR 11, this ledger says either
"still present (allowed for now)" or "regression — it came back". The
ledger gives reviewers a single place to see whether a symbol is still
allowed or has become forbidden.

Companion files (positive ledgers):
- test_v2_final_state_ledger.py — invariants that must hold by PR 11
- test_dead_path_audit.py — symbols that must stay callerless
- test_no_type_circumventors.py — getattr/hasattr ban in prod code
"""

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
        name="InngestCriterionExecutor",
        owner_pr="PR 4",
        deletion_pr="PR 11",
        allowed_reason=(
            "Concrete impl of the Protocol; survives alongside "
            "CriterionExecutor until PR 11 deletes both."
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


EXEMPT_DIR_PARTS: frozenset[str] = frozenset({"tests", "migrations", "__pycache__"})


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
