"""Repository package companion files — see
`docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/07-test-strategy.md`
§ Repository layer standard.

For every package containing a Repository:
  - If any `.py` file other than `errors.py` contains a `raise` line,
    the package must have an `errors.py` carrying typed exceptions.
    Generic `raise ValueError(...)` in a repository is a typed-error
    gap.
  - `repository.py` must not define Pydantic BaseModel DTOs (request
    or response shapes). Those belong in `models.py`. SQLModel tables
    are not BaseModel DTOs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOT = ROOT / "ergon_core" / "ergon_core"


def _discover_repo_packages() -> list[Path]:
    packages: list[Path] = []
    for path in (PRODUCTION_ROOT / "core").rglob("repository.py"):
        packages.append(path.parent)
    for path in (PRODUCTION_ROOT / "core").rglob("repositories.py"):
        packages.append(path.parent)
    return sorted(set(packages))


REPO_PACKAGES = _discover_repo_packages()


_RAISE_RE = re.compile(r"^\s*raise\s+\w", re.MULTILINE)
_BASEMODEL_DEF_RE = re.compile(
    r"^class\s+\w+\s*\(\s*BaseModel\b",
    re.MULTILINE,
)


# Same shape as test_repository_layer_conventions.py — applied by the
# shared conftest.py hook. Keys are (test_name, parametrize_id) tuples.
_KNOWN_VIOLATORS: dict[tuple[str, str], str] = {
    (
        "test_package_has_errors_py_if_repository_raises",
        "ergon_core/ergon_core/core/application/experiments",
    ): "PR 7: add experiments/errors.py with typed DefinitionNotFoundError "
    "and replace ValueError raises.",
    (
        "test_repository_file_does_not_define_dtos",
        "ergon_core/ergon_core/core/persistence/telemetry",
    ): "PR 4: move CreateTaskEvaluation to telemetry/models.py.",
}


@pytest.mark.parametrize("pkg", REPO_PACKAGES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_package_has_errors_py_if_repository_raises(pkg: Path) -> None:
    """If `repository.py` (or `repositories.py`) raises, `errors.py`
    must exist with typed exception classes — callers can then catch
    specifically rather than catching generic `ValueError`.

    Scoped to the repository file specifically; raises in `models.py`
    are typically Pydantic field validation (which conventionally uses
    `ValueError`) and don't need a domain-layer `errors.py`.
    """

    raisers: list[str] = []
    for repo_filename in ("repository.py", "repositories.py"):
        repo_path = pkg / repo_filename
        if not repo_path.exists():
            continue
        if _RAISE_RE.search(repo_path.read_text()):
            raisers.append(repo_filename)
    if not raisers:
        return  # no raises in repo files, no errors.py needed
    assert (pkg / "errors.py").exists(), (
        f"{pkg.relative_to(ROOT)} has raises in {raisers} but no "
        "errors.py. Add typed exception classes so callers can catch "
        "specifically rather than catching generic ValueError."
    )


@pytest.mark.parametrize("pkg", REPO_PACKAGES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_repository_file_does_not_define_dtos(pkg: Path) -> None:
    """Pydantic DTOs (request / response shapes) live in `models.py`,
    not in `repository.py`. A BaseModel definition in `repository.py`
    indicates a contract leak."""

    for repo_file in ("repository.py", "repositories.py"):
        path = pkg / repo_file
        if not path.exists():
            continue
        matches = _BASEMODEL_DEF_RE.findall(path.read_text())
        assert matches == [], (
            f"{path.relative_to(ROOT)} defines Pydantic BaseModel "
            f"classes inline ({matches}); move them to "
            f"{pkg.relative_to(ROOT)}/models.py."
        )
