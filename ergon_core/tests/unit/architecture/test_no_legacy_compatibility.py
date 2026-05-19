"""Guard against reintroducing old compatibility paths in active code/tests."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[4]
ACTIVE_ROOTS = (
    ROOT / "ergon_core" / "ergon_core",
    ROOT / "ergon_core" / "tests",
    ROOT / "ergon_builtins" / "ergon_builtins",
    ROOT / "ergon_cli" / "ergon_cli",
    ROOT / "tests",
    ROOT / "ergon_cli" / "tests",
    ROOT / "ergon-dashboard" / "src",
    ROOT / "ergon-dashboard" / "tests",
)
EXCLUDED_FILES = {Path(__file__).resolve()}
LEGACY_PATTERN = re.compile(r"\blegacy\b", re.IGNORECASE)


def test_active_code_has_no_legacy_compatibility_references() -> None:
    hits: list[str] = []
    for root in ACTIVE_ROOTS:
        for path in root.rglob("*"):
            if (
                path.is_dir()
                or path.resolve() in EXCLUDED_FILES
                or "node_modules" in path.parts
                or "__pycache__" in path.parts
            ):
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if LEGACY_PATTERN.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    assert hits == []
