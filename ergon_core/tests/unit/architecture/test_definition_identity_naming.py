"""Guard that definition identity is not exposed with pre-v2 naming.

The heterogeneous-experiment RFC reintroduces ``experiment_id`` as the identity
of the new experiment object. This guard is scoped to definition-owned code so
it does not reject legitimate experiment provenance fields.
"""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[4]
DEFINITION_ROOTS = (
    ROOT / "ergon_core" / "ergon_core" / "core" / "persistence" / "definitions",
    ROOT / "ergon_core" / "ergon_core" / "core" / "application" / "definitions",
    ROOT / "ergon_core" / "ergon_core" / "core" / "application" / "experiments",
    ROOT / "ergon_core" / "tests" / "unit" / "runtime",
    ROOT / "ergon_core" / "tests" / "unit" / "core" / "application" / "experiments",
)
EXCLUDED_FILES = {Path(__file__).resolve()}
EXPERIMENT_ID_PATTERN = re.compile(r"\b(?:experiment" r"_id|experiment" r"Id)\b")


def test_definition_identity_uses_definition_name() -> None:
    hits: list[str] = []
    for root in DEFINITION_ROOTS:
        if not root.exists():
            continue
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
                if EXPERIMENT_ID_PATTERN.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    assert hits == []
