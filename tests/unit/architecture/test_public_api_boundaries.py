"""Architecture guards for the student-facing public API boundary."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

FORBIDDEN_IMPORT_SNIPPETS = (
    "from ergon_core.api.generation import",
    "from ergon_core.api.json_types import",
    "from ergon_core.api.run_resource import",
    "from ergon_core.api.criterion_runtime import",
    "from ergon_core.api.dependencies import",
    "from ergon_core.api.types import",
)

CHECKED_ROOTS = (
    ROOT / "ergon_builtins",
    ROOT / "ergon_cli",
    ROOT / "ergon_core" / "ergon_core" / "core",
)


def test_runtime_and_builtin_code_do_not_import_core_types_through_public_api() -> None:
    offenders: list[str] = []
    for root in CHECKED_ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text()
            for snippet in FORBIDDEN_IMPORT_SNIPPETS:
                if snippet in text:
                    offenders.append(f"{path.relative_to(ROOT)} imports via {snippet!r}")

    assert offenders == []
