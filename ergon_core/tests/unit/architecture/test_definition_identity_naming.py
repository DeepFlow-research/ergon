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
ALLOWED_EXPERIMENT_ID_PATH_PREFIXES = (
    ROOT / "ergon_core" / "ergon_core" / "api" / "experiment",
    ROOT / "ergon_core" / "ergon_core" / "core" / "application" / "experiments",
    ROOT / "ergon_core" / "ergon_core" / "core" / "persistence" / "experiments",
    ROOT / "ergon_core" / "ergon_core" / "core" / "views" / "experiments",
    ROOT / "ergon_core" / "ergon_core" / "core" / "views" / "samples",
    ROOT / "ergon_core" / "ergon_core" / "core" / "rl",
    ROOT / "ergon_core" / "tests" / "integration" / "experiments",
    ROOT / "ergon_core" / "tests" / "unit" / "api",
    ROOT / "ergon_core" / "tests" / "unit" / "core" / "application" / "experiments",
    ROOT / "ergon_core" / "tests" / "unit" / "read_models",
    ROOT / "ergon_core" / "tests" / "unit" / "rest_api",
    ROOT / "ergon_core" / "tests" / "unit" / "rl",
    ROOT / "ergon_cli" / "ergon_cli" / "domains" / "experiments",
    ROOT / "ergon_cli" / "ergon_cli" / "domains" / "samples",
    ROOT / "ergon_cli" / "ergon_cli" / "domains" / "training",
    ROOT / "ergon_cli" / "tests" / "unit" / "cli",
    ROOT / "ergon_infra" / "ergon_infra" / "adapters",
    ROOT / "ergon_infra" / "ergon_infra" / "training",
    ROOT / "ergon_infra" / "tests" / "unit",
    ROOT / "ergon-dashboard" / "src" / "app" / "experiments",
    ROOT / "ergon-dashboard" / "src" / "app" / "samples",
    ROOT / "ergon-dashboard" / "src" / "components" / "experiments",
    ROOT / "ergon-dashboard" / "src" / "components" / "indexes",
    ROOT / "ergon-dashboard" / "src" / "components" / "samples",
    ROOT / "ergon-dashboard" / "src" / "generated" / "rest",
    ROOT / "ergon-dashboard" / "src" / "lib" / "sample-state",
    ROOT / "ergon-dashboard" / "tests" / "components",
    ROOT / "ergon-dashboard" / "tests" / "contracts",
    ROOT / "ergon-dashboard" / "tests" / "unit",
    ROOT / "tests" / "examples",
)
ALLOWED_EXPERIMENT_ID_FILES = {
    ROOT
    / "ergon_core"
    / "ergon_core"
    / "core"
    / "infrastructure"
    / "http"
    / "routes"
    / "experiments.py",
    ROOT
    / "ergon_core"
    / "ergon_core"
    / "core"
    / "infrastructure"
    / "http"
    / "routes"
    / "samples.py",
    ROOT / "ergon_core" / "ergon_core" / "core" / "persistence" / "telemetry" / "models.py",
    ROOT / "ergon_core" / "tests" / "unit" / "state" / "test_type_invariants.py",
    ROOT / "ergon-dashboard" / "src" / "lib" / "contracts" / "rest.ts",
    ROOT / "ergon-dashboard" / "src" / "lib" / "server-data" / "experiments.ts",
    ROOT / "ergon-dashboard" / "src" / "lib" / "server-data" / "samples.ts",
    ROOT
    / "ergon_core"
    / "ergon_core"
    / "core"
    / "infrastructure"
    / "http"
    / "routes"
    / "rollouts.py",
}
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
        re.compile(r"experiment_id=handle\.experiment_id"),
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
        re.compile(r"ref\.experiment_id"),
    ),
    ROOT / "ergon_core" / "ergon_core" / "core" / "application" / "experiments" / "submission.py": (
        re.compile(r"experiment_id=handle\.experiment_id"),
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


def _allows_experiment_identity_path(path: Path) -> bool:
    resolved = path.resolve()
    if resolved in ALLOWED_EXPERIMENT_ID_FILES:
        return True
    return any(resolved.is_relative_to(prefix) for prefix in ALLOWED_EXPERIMENT_ID_PATH_PREFIXES)


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
            if _allows_experiment_identity_path(path):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if EXPERIMENT_ID_PATTERN.search(line):
                    allowed = ALLOWED_EXPERIMENT_ID_PATTERNS_BY_FILE.get(path.resolve(), ())
                    if any(pattern.search(line) for pattern in allowed):
                        continue
                    hits.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    assert hits == []
