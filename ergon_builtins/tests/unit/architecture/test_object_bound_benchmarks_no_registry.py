"""After PR 10a/10b/10c land, no migrated benchmark module should
import ``ComponentRegistry`` — object-bound benchmarks construct Tasks
directly and don't go through registry resolution."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]

_MIGRATED_BENCHMARKS = (
    "minif2f",
    "swebench_verified",
    "researchrubrics",
    "gdpeval",
)


@pytest.mark.parametrize("slug", _MIGRATED_BENCHMARKS)
def test_object_bound_benchmark_does_not_import_component_registry(
    slug: str,
) -> None:
    pkg = ROOT / "ergon_builtins" / "ergon_builtins" / "benchmarks" / slug
    offenders: list[str] = []
    for path in pkg.rglob("*.py"):
        text = path.read_text()
        if "ComponentRegistry" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], (
        f"{slug} still depends on ComponentRegistry; PR 10 was supposed "
        f"to remove that dependency. Offenders: {offenders}"
    )
