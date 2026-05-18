"""Dead-method audit on the repository layer.

Every public method on every Repository class must have at least one
production caller (non-test file). The audit is scoped tightly to the
repository layer rather than tree-wide because that's where v1's audit
found real dead helpers — going wider has too much false-positive noise
from Inngest registration, Pydantic decorators, etc.

No known-unused ledger is allowed; methods either have production callers
or should be deleted.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

# Import the shared discovery helpers from the conventions guard.
from ergon_core.tests.unit.architecture import (
    test_repository_layer_conventions as _conv,
)

REPO_CLASSES = _conv.REPO_CLASSES

ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOTS = (
    ROOT / "ergon_core" / "ergon_core",
    ROOT / "ergon_builtins" / "ergon_builtins",
    ROOT / "ergon_cli" / "ergon_cli",
)
EXEMPT_PARTS: frozenset[str] = frozenset({"tests", "migrations", "__pycache__"})


def _all_public_methods() -> list[tuple[type, str]]:
    methods: list[tuple[type, str]] = []
    for cls in REPO_CLASSES:
        for name, _ in inspect.getmembers(cls, inspect.isfunction):
            if not name.startswith("_"):
                methods.append((cls, name))
    return methods


def _grep_production_callers(pattern: str, exclude_path: Path | None = None) -> list[str]:
    hits: list[str] = []
    for root in PRODUCTION_ROOTS:
        for path in root.rglob("*.py"):
            if EXEMPT_PARTS.intersection(path.parts):
                continue
            if exclude_path is not None and path == exclude_path:
                continue
            if pattern in path.read_text():
                hits.append(str(path.relative_to(ROOT)))
    return sorted(hits)


def _cases() -> list:
    return [
        pytest.param(cls, method, id=f"{cls.__name__}.{method}")
        for cls, method in _all_public_methods()
    ]


@pytest.mark.parametrize("cls,method", _cases())
def test_repository_method_has_a_production_caller(cls: type, method: str) -> None:
    """Pattern `.method(` catches the common call form. Defining-file
    is excluded so the method's own definition doesn't count as its
    caller."""

    defining_file = Path(inspect.getfile(cls))
    callers = _grep_production_callers(f".{method}(", exclude_path=defining_file)
    assert callers, (
        f"{cls.__name__}.{method} has no production callers. "
        "Either add a caller or delete the method."
    )
