"""PR 11 migration reset guard."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
VERSIONS = ROOT / "ergon_core" / "migrations" / "versions"


def test_v2_migration_stack_is_explicit() -> None:
    migrations = sorted(path.name for path in VERSIONS.glob("*.py"))
    assert migrations == [
        "00000000_initial_v2.py",
        "00000001_add_experiment_persistence.py",
        "00000002_add_sample_experiment_provenance.py",
        "00000003_delete_definition_runtime_columns.py",
    ]


def test_initial_migration_has_no_parent() -> None:
    text = (VERSIONS / "00000000_initial_v2.py").read_text()
    assert 'revision = "00000000"' in text
    assert "down_revision = None" in text


def test_initial_migration_orders_fk_targets_before_dependents() -> None:
    text = (VERSIONS / "00000000_initial_v2.py").read_text()

    assert text.index('"sample_task_attempts"') < text.index('"sample_context_events"')
