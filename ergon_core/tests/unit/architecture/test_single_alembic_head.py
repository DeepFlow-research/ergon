"""PR 11 migration reset guard."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
VERSIONS = ROOT / "ergon_core" / "migrations" / "versions"


def test_v2_has_one_initial_migration() -> None:
    migrations = sorted(path.name for path in VERSIONS.glob("*.py"))
    assert migrations == ["00000000_initial_v2.py"]


def test_initial_migration_has_no_parent() -> None:
    text = (VERSIONS / "00000000_initial_v2.py").read_text()
    assert 'revision = "00000000"' in text
    assert "down_revision = None" in text
