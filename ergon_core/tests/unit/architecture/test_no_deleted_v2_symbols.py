"""PR 11 guard for symbols removed from the v2 stack."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOTS = (
    ROOT / "ergon_core" / "ergon_core",
    ROOT / "ergon_builtins" / "ergon_builtins",
    ROOT / "ergon_cli" / "ergon_cli",
)
DELETED_SYMBOLS = (
    "TaskSpec",
    "ComponentRegistry",
    "ComponentCatalog",
    "ComponentCatalogService",
    "EvaluateTaskRunRequest",
    "ExperimentRecord",
    "CriterionExecutor",
    "InngestCriterionExecutor",
    "definition_task_id",
    "parent_node_id",
    "source_node_id",
    "target_node_id",
    "terminate_sandbox_by_id",
)


def test_deleted_v2_symbols_do_not_reappear() -> None:
    hits: list[str] = []
    for root in PRODUCTION_ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text()
            for symbol in DELETED_SYMBOLS:
                if symbol in text:
                    hits.append(f"{path.relative_to(ROOT)}: {symbol}")
    assert hits == []
