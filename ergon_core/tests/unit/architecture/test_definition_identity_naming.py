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
ALLOWED_EXPERIMENT_ID_PATTERNS_BY_FILE = {
    ROOT / "ergon_core" / "ergon_core" / "api" / "experiment" / "experiment.py": (
        re.compile(r"experiment_id: UUID"),
    ),
    ROOT / "ergon_core" / "ergon_core" / "api" / "experiment" / "sampling.py": (
        re.compile(r"experiment_id: UUID"),
    ),
    ROOT
    / "ergon_core"
    / "ergon_core"
    / "core"
    / "application"
    / "experiments"
    / "candidate_pool.py": (
        re.compile(r"handle\.experiment_id"),
        re.compile(r"experiment_id: UUID"),
        re.compile(r"experiment_id == experiment_id"),
    ),
    ROOT / "ergon_core" / "ergon_core" / "core" / "application" / "experiments" / "repository.py": (
        re.compile(r"experiment_id=row\.id"),
        re.compile(r"experiment_id == row\.id"),
        re.compile(r"experiment_id=handle\.id"),
        re.compile(r"experiment_ref\.experiment_id"),
        re.compile(r"experiment_id: UUID"),
        re.compile(r"experiment_id == experiment_id"),
    ),
    ROOT / "ergon_core" / "ergon_core" / "core" / "persistence" / "experiments" / "models.py": (
        re.compile(r"experiment_id"),
    ),
    ROOT
    / "ergon_core"
    / "tests"
    / "integration"
    / "experiments"
<<<<<<< HEAD
    / "test_experiment_persistence_roundtrip.py": (
        re.compile(r"experiment_id == handle\.experiment_id"),
    ),
    ROOT
    / "ergon_core"
    / "tests"
    / "unit"
    / "core"
    / "application"
    / "experiments"
    / "test_experiment_persistence.py": (
        re.compile(r"experiment_id == handle\.experiment_id"),
        re.compile(r"handle\.experiment_id"),
    ),
    ROOT / "ergon_core" / "tests" / "unit" / "api" / "test_sampler_contract.py": (
        re.compile(r"experiment_ref_id=uuid4"),
        re.compile(r"result\.experiment_ref_id"),
    ),
    ROOT / "ergon_core" / "ergon_core" / "core" / "application" / "experiments" / "submission.py": (
        re.compile(r"experiment_id=entry\.experiment_id"),
        re.compile(r"experiment=str\(entry\.experiment_id\)"),
    ),
    ROOT / "ergon_core" / "ergon_core" / "core" / "persistence" / "telemetry" / "models.py": (
        re.compile(r"experiment_id"),
    ),
    ROOT
    / "ergon_core"
    / "tests"
    / "unit"
    / "core"
    / "application"
    / "experiments"
    / "test_experiment_submit.py": (re.compile(r"row\.experiment_id"),),
    ROOT / "ergon_core" / "tests" / "unit" / "state" / "test_type_invariants.py": (
        re.compile(r"run\.experiment_id is None"),
    ),
}


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
                    allowed = ALLOWED_EXPERIMENT_ID_PATTERNS_BY_FILE.get(path.resolve(), ())
                    if any(pattern.search(line) for pattern in allowed):
                        continue
                    hits.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    assert hits == []
