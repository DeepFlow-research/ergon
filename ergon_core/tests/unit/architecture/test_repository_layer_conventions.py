"""Repository layer conventions — see
`docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/07-test-strategy.md`
§ Repository layer standard.

For every Repository class discovered in `ergon_core`, enforce:
  - Class name ends with `Repository`.
  - Containing file is `repository.py` (singular).
  - Public methods take `session` as the first non-self positional arg.
  - Write methods (add_/update_/remove_/delete_/set_/create_/append_/
    insert_/persist_) are async; read methods may be sync OR async (async
    is required only when the method performs genuine I/O like a live
    sandbox attach — `graph_repo.node` is the textbook case).
  - No `session.commit(` calls inside repository methods (transactions
    belong to the caller).
  - The repository module does not import from
    `ergon_core.core.infrastructure.*` (keeps the data layer
    framework-agnostic — see graph/errors.py for the rationale).
"""

from __future__ import annotations

import ast
import importlib
import inspect
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOT = ROOT / "ergon_core" / "ergon_core"
CORE_ROOT = PRODUCTION_ROOT / "core"
APPLICATION_ROOT = CORE_ROOT / "application"
APPLICATION_PREFIX = "ergon_core.core.application"

_REPOSITORY_REEXPORT_IMPORT_LEDGER = ()


_WRITE_PREFIXES = (
    "add_",
    "update_",
    "remove_",
    "delete_",
    "set_",
    "create_",
    "append_",
    "insert_",
    "persist_",
)


def _discover_repository_classes() -> list[type]:
    """Walk `ergon_core` and import every `*/repository.py` and
    `*/repositories.py`, returning the classes whose name ends in
    `Repository`."""

    pkg_root = PRODUCTION_ROOT / "core"
    classes: list[type] = []
    for path in pkg_root.rglob("repository.py"):
        classes.extend(_load_classes_from_file(path))
    # NB: `repositories.py` (plural) is a known violator captured by
    # the companion-files guard; we still load it here so its classes
    # get audited.
    for path in pkg_root.rglob("repositories.py"):
        classes.extend(_load_classes_from_file(path))
    return classes


def _load_classes_from_file(path: Path) -> list[type]:
    rel = path.relative_to(ROOT / "ergon_core")
    module_name = ".".join(rel.with_suffix("").parts)
    module = importlib.import_module(module_name)
    return [
        cls
        for _name, cls in inspect.getmembers(module, inspect.isclass)
        if cls.__name__.endswith("Repository") and cls.__module__ == module.__name__
    ]


REPO_CLASSES: list[type] = _discover_repository_classes()


def _is_write_method(name: str) -> bool:
    return any(name.startswith(p) for p in _WRITE_PREFIXES)


def _public_methods(cls: type) -> Iterator[tuple[str, object]]:
    for name, method in inspect.getmembers(cls, inspect.isfunction):
        if name.startswith("_"):
            continue
        yield name, method


# --- Naming ------------------------------------------------------------


@pytest.mark.parametrize("cls", REPO_CLASSES, ids=lambda c: c.__name__)
def test_repository_class_name_ends_in_Repository(cls: type) -> None:
    assert cls.__name__.endswith("Repository"), (
        f"{cls.__name__} must end in 'Repository' per the repository layer standard"
    )


@pytest.mark.parametrize("cls", REPO_CLASSES, ids=lambda c: c.__name__)
def test_repository_file_is_singular(cls: type) -> None:
    """File must be `repository.py`, not `repositories.py`."""

    filename = Path(inspect.getfile(cls)).name
    assert filename == "repository.py", (
        f"{cls.__name__} lives in {filename}; the standard requires "
        "`repository.py` (singular) even when multiple Repository "
        "classes share the file."
    )


# --- Method signatures -------------------------------------------------


def _takes_session_first(method: object) -> bool:
    """A method is a 'data-access method' iff its first non-self
    positional parameter is named `session`. Configuration setters like
    `add_mutation_listener(self, listener)` are deliberately exempt
    from the session-first and writes-are-async rules; they aren't
    data access."""

    params = list(inspect.signature(method).parameters)
    non_self = params[1:] if params and params[0] in {"self", "cls"} else params
    return bool(non_self) and non_self[0] == "session"


@pytest.mark.parametrize("cls", REPO_CLASSES, ids=lambda c: c.__name__)
def test_public_data_access_methods_take_session_first(cls: type) -> None:
    """Every public data-access method takes `session` first.

    A method is *not* a data-access method if it never accepts a
    session at all (e.g. `add_mutation_listener(self, listener)`).
    Those methods are exempt — the rule applies only to the methods
    that actually read or write the database.
    """

    offenders: list[str] = []
    for name, method in _public_methods(cls):
        params = list(inspect.signature(method).parameters)
        # Method takes no session at all → not a data-access method,
        # exempt. (Configuration setters fall into this bucket.)
        if "session" not in params:
            continue
        if not _takes_session_first(method):
            offenders.append(f"{cls.__name__}.{name}({params!r})")
    assert offenders == [], (
        "Repository data-access methods must take `session` as the first "
        f"non-self positional arg. Offenders: {offenders}"
    )


@pytest.mark.parametrize("cls", REPO_CLASSES, ids=lambda c: c.__name__)
def test_write_methods_are_async(cls: type) -> None:
    """Methods named with a write prefix (`add_`, `update_`, etc.) must
    be async. Configuration setters (no session parameter) are exempt.
    Reads may be sync OR async — async reads are only required when the
    method performs genuine I/O (e.g. `graph_repo.node` after PR 5
    attaches a live sandbox)."""

    offenders: list[str] = []
    for name, method in _public_methods(cls):
        if not _is_write_method(name):
            continue
        # Exempt configuration setters (no session = not data access).
        if not _takes_session_first(method):
            continue
        if not inspect.iscoroutinefunction(method):
            offenders.append(f"{cls.__name__}.{name}")
    assert offenders == [], (
        "Write methods must be async (the naming heuristic catches the "
        f"common write prefixes). Offenders: {offenders}"
    )


# --- Transaction ownership --------------------------------------------


@pytest.mark.parametrize("cls", REPO_CLASSES, ids=lambda c: c.__name__)
def test_no_commit_inside_repository(cls: type) -> None:
    src = inspect.getsource(cls)
    assert "session.commit(" not in src, (
        f"{cls.__name__} commits inside the repository — transactions "
        "belong to the caller (the service / job body), not the data "
        "layer. Remove the `session.commit()` call and let the caller "
        "decide when to commit."
    )


# --- Layer boundary ---------------------------------------------------


@pytest.mark.parametrize("cls", REPO_CLASSES, ids=lambda c: c.__name__)
def test_repository_does_not_import_infrastructure(cls: type) -> None:
    """The data layer must stay framework-agnostic so it can be reused
    in training pipelines, replay systems, and test harnesses that
    don't run inside Inngest. See graph/errors.py docstring for the
    rationale."""

    src = Path(inspect.getfile(cls)).read_text()
    assert "ergon_core.core.infrastructure" not in src, (
        f"{cls.__name__}'s module imports from "
        "`ergon_core.core.infrastructure`. Repositories must stay "
        "framework-agnostic."
    )


def _module_name_for_path(path: Path) -> str:
    rel = path.relative_to(ROOT / "ergon_core")
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _source_package_parts(path: Path, module_name: str) -> list[str]:
    parts = module_name.split(".")
    if path.name == "__init__.py":
        return parts
    return parts[:-1]


def _resolve_import_from_base(
    *,
    path: Path,
    source_module: str,
    level: int,
    module: str | None,
) -> str:
    if level == 0:
        return module or ""

    package_parts = _source_package_parts(path, source_module)
    kept_parts = package_parts[: len(package_parts) - (level - 1)]
    base = ".".join(kept_parts)
    if module:
        return f"{base}.{module}"
    return base


def _source_application_domain(path: Path) -> str | None:
    try:
        return path.relative_to(APPLICATION_ROOT).parts[0]
    except ValueError:
        return None


def _repository_import_target(base: str, alias: str) -> tuple[str, str] | None:
    if not base.startswith(f"{APPLICATION_PREFIX}."):
        return None

    parts = base.split(".")
    if len(parts) < 4:
        return None

    domain = parts[3]
    if len(parts) == 4 and alias == "repository":
        return domain, f"{base}.repository"
    if len(parts) >= 5 and parts[4] == "repository":
        return domain, ".".join(parts[:5])
    if len(parts) == 4 and alias in _repository_reexports(domain):
        return domain, f"{base}.{alias}"
    return None


def _repository_reexports(domain: str) -> set[str]:
    init_path = APPLICATION_ROOT / domain / "__init__.py"
    if not init_path.exists():
        return set()

    tree = ast.parse(init_path.read_text(), filename=str(init_path))
    reexports: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or not node.module.endswith(".repository"):
            continue
        reexports.update(alias.asname or alias.name for alias in node.names)
    return reexports


def _application_repository_imports() -> set[tuple[str, str]]:
    imports: set[tuple[str, str]] = set()
    for path in CORE_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue

        source_module = _module_name_for_path(path)
        source_domain = _source_application_domain(path)
        tree = ast.parse(path.read_text(), filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(_plain_repository_imports(node, source_module, source_domain))
                continue

            if not isinstance(node, ast.ImportFrom) or node.module == "__future__":
                continue

            imports.update(_from_repository_imports(path, node, source_module, source_domain))

    return imports


def _plain_repository_imports(
    node: ast.Import,
    source_module: str,
    source_domain: str | None,
) -> set[tuple[str, str]]:
    imports: set[tuple[str, str]] = set()
    for alias in node.names:
        target = _repository_import_target(alias.name, "")
        if target is None:
            continue
        target_domain, target_module = target
        if source_domain != target_domain:
            imports.add((source_module, target_module))
    return imports


def _from_repository_imports(
    path: Path,
    node: ast.ImportFrom,
    source_module: str,
    source_domain: str | None,
) -> set[tuple[str, str]]:
    imports: set[tuple[str, str]] = set()
    base = _resolve_import_from_base(
        path=path,
        source_module=source_module,
        level=node.level,
        module=node.module,
    )
    for alias in node.names:
        target = _repository_import_target(base, alias.name)
        if target is None:
            continue
        target_domain, target_module = target
        if source_domain != target_domain:
            imports.add((source_module, target_module))
    return imports


@pytest.mark.parametrize(
    ("source_module", "target_module"),
    _REPOSITORY_REEXPORT_IMPORT_LEDGER,
)
def test_ledgered_application_repository_imports_are_removed(
    source_module: str,
    target_module: str,
) -> None:
    """Strict xfail ledger for repository imports hidden behind package exports."""

    assert (source_module, target_module) not in _application_repository_imports()


def test_application_repositories_are_imported_only_within_their_domain() -> None:
    ledgered = {(param.values[0], param.values[1]) for param in _REPOSITORY_REEXPORT_IMPORT_LEDGER}
    offenders = [
        f"{source_module} imports repository module {target_module}"
        for source_module, target_module in sorted(_application_repository_imports() - ledgered)
    ]

    assert offenders == []
