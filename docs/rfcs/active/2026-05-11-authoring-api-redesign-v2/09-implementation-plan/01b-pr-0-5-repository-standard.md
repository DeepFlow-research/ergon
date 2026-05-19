# PR 0.5 — Repository Layer Standard And Guards

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repository layer's shape explicit and enforceable, so
the v2 deletions and the post-v2 cleanup work against a known standard
rather than five subtly different conventions.

**Architecture:** Three architecture-guard tests encode the repository
layer's conventions: file/class naming, sync/async split, transaction
ownership, error-typing, contract location, and dead-method audit. PRs
that touch a violator flip the corresponding xfail to green; no
violator stays unfixed past its scheduled landing PR.

**Tech Stack:** pytest parametrized guards, source-text architecture
checks, the same `xfail(strict=True)` ledger pattern PR 0 introduced.

This PR sits between PR 0 (transition ledger) and PR 1 (run-tier task
snapshot) because the conventions it pins are load-bearing for every
later PR that touches a repository — particularly PR 2's typed
`graph_repo.node`, PR 4's `WorkerOutputRepository`, and PR 7's
collapsed read paths.

---

## Files

**Create:**

```text
ergon_core/tests/unit/architecture/test_repository_layer_conventions.py
ergon_core/tests/unit/architecture/test_repository_companion_files.py
ergon_core/tests/unit/architecture/test_no_dead_repository_methods.py
```

**Modify:**

```text
docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/07-test-strategy.md
docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/00-program.md
```

## Current State

Five repository packages, three different shapes:

| Package | Repo file | errors.py | Notes |
|---|---|---|---|
| `core/application/tasks/` | `repository.py` | ✅ | clean |
| `core/application/experiments/` | `repository.py` | ❌ raises `ValueError` directly | typed-error gap |
| `core/application/resources/` | `repository.py` | ❌ no raises today | OK |
| `core/application/graph/` | `repository.py` | ✅ | clean (35+ methods) |
| `core/persistence/telemetry/` | **`repositories.py` (plural!)** | ❌ | + `CreateTaskEvaluation` DTO leaks into the repo file |

Additional patterns observed:

- `WorkflowGraphRepository` enforces "writes async, reads sync" by
  convention but nothing pins it.
- `experiments/repository.py` raises `ValueError("ExperimentDefinitionTask
  {id} not found")` — generic exception, callers can't catch specifically.
- `telemetry/repositories.py` defines `class CreateTaskEvaluation(BaseModel)`
  inline at line 12 — a request DTO living in the repo file instead of
  `telemetry/models.py`.
- Several public methods on `TaskExecutionRepository` (e.g.
  `latest_for_definition_task`, `task_payload_for_execution`,
  `next_attempt_for_definition_task`) may not have callers after the v2
  cutovers land, but nothing catches "method has no production callers"
  today — the same audit failure mode v1 had with `Worker.from_buffer`.

## Target State For This PR

Three guard test files land. Each enforces one slice of the standard:

1. **Conventions** — class naming, file naming, method signatures,
   sync/async split, no `session.commit()` in repo methods, no
   `core.infrastructure` imports.
2. **Companion files** — `errors.py` exists iff package raises;
   DTO classes don't live in `repository.py`.
3. **Dead-method audit** — every public Repository method has at least
   one non-test caller, with an xfail allowlist mirror of PR 0's
   dead-path audit pattern.

Current violators are xfailed with `strict=True`, keyed to the PR that
fixes each:

- PR 1: rename `telemetry/repositories.py` → `telemetry/repository.py`.
- PR 4: move `CreateTaskEvaluation` from `telemetry/repository.py` to
  `telemetry/models.py`.
- PR 7: add `experiments/errors.py` with typed exceptions
  (`DefinitionNotFoundError`, `InstanceNotFoundError`), replace
  `ValueError` raises.
- PR 11: deletes methods on `TaskExecutionRepository` whose callers go
  away during the v2 cutover.

## Task 1: Land The Repository Layer Standard

**Files:**

- Modify: `docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/07-test-strategy.md`

- [x] **Step 1: Add the standard section**

Add a new section to `07-test-strategy.md` after § 0 documenting the
10 rules — see Task 1 Step 2 of `07-test-strategy.md` update. The
section is the canonical reference the guard tests cite in error
messages.

## Task 2: Add `test_repository_layer_conventions.py`

**Files:**

- Create: `ergon_core/tests/unit/architecture/test_repository_layer_conventions.py`

- [x] **Step 1: Write the guard file**

```python
"""Repository layer conventions — see 07-test-strategy.md § Repository
layer standard.

For every Repository class discovered in `ergon_core`, enforce:
  - Class name ends with `Repository`.
  - Containing file is `repository.py` (singular).
  - Public methods take `session` as the first non-self positional arg.
  - Write methods are async; read methods may be sync OR async (async
    is required only when the method performs genuine I/O like a live
    sandbox attach — `graph_repo.node` is the textbook case).
  - No `session.commit(` calls inside repository methods (transactions
    belong to the caller).
  - The repository module does not import from
    `ergon_core.core.infrastructure.*` (keeps the data layer framework-
    agnostic — see graph/errors.py for the rationale).
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOT = ROOT / "ergon_core" / "ergon_core"


_WRITE_PREFIXES = (
    "add_", "update_", "remove_", "delete_", "set_",
    "create_", "append_", "insert_", "persist_",
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
    # Strip the leading "ergon_core" since it's already the package root.
    if module_name.startswith("ergon_core."):
        module_name = module_name
    module = importlib.import_module(module_name)
    return [
        cls
        for name, cls in inspect.getmembers(module, inspect.isclass)
        if name.endswith("Repository") and cls.__module__ == module.__name__
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
        f"{cls.__name__} must end in 'Repository' per the repository "
        "layer standard"
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


@pytest.mark.parametrize("cls", REPO_CLASSES, ids=lambda c: c.__name__)
def test_public_methods_take_session_first(cls: type) -> None:
    offenders: list[str] = []
    for name, method in _public_methods(cls):
        params = list(inspect.signature(method).parameters)
        # Skip the implicit `self` / `cls`.
        non_self = params[1:] if params and params[0] in {"self", "cls"} else params
        if not non_self or non_self[0] != "session":
            offenders.append(f"{cls.__name__}.{name}({params!r})")
    assert offenders == [], (
        "Repository methods must take `session` as the first non-self "
        f"positional arg. Offenders: {offenders}"
    )


@pytest.mark.parametrize("cls", REPO_CLASSES, ids=lambda c: c.__name__)
def test_write_methods_are_async(cls: type) -> None:
    """Methods named with a write prefix (`add_`, `update_`, etc.) must
    be async. Reads may be sync OR async — async reads are only required
    when the method performs genuine I/O (e.g. `graph_repo.node` after
    PR 5 attaches a live sandbox)."""

    offenders: list[str] = []
    for name, method in _public_methods(cls):
        if _is_write_method(name) and not inspect.iscoroutinefunction(method):
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
```

- [x] **Step 2: Run the guard**

```bash
uv run pytest ergon_core/tests/unit/architecture/test_repository_layer_conventions.py -q
```

Expected: every case PASS for current repositories EXCEPT the
`test_repository_file_is_singular` case for `TelemetryRepository`,
which fails because it lives in `repositories.py`. Wrap that single
case as `xfail(strict=True, reason="PR 1: telemetry rename")` (see
Task 5 below).

## Task 3: Add `test_repository_companion_files.py`

**Files:**

- Create: `ergon_core/tests/unit/architecture/test_repository_companion_files.py`

- [x] **Step 1: Write the guard file**

```python
"""Repository package companion files — see 07-test-strategy.md §
Repository layer standard.

For every package containing a Repository:
  - If any `.py` file other than `errors.py` contains a `raise` line,
    the package must have an `errors.py` carrying typed exceptions.
    Generic `raise ValueError(...)` in a repository is a typed-error
    gap.
  - `repository.py` must not define Pydantic BaseModel DTOs (request
    or response shapes). Those belong in `models.py`. SQLModel tables
    are not BaseModel DTOs — they live in `models.py` anyway.
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


@pytest.mark.parametrize(
    "pkg", REPO_PACKAGES, ids=lambda p: p.relative_to(ROOT).as_posix()
)
def test_package_has_errors_py_if_it_raises(pkg: Path) -> None:
    """If anything in the package `raise`s, `errors.py` must exist with
    typed exception classes — even one custom exception is better than a
    generic `ValueError` because callers can catch it."""

    raisers: list[str] = []
    for path in pkg.glob("*.py"):
        if path.name in {"errors.py", "__init__.py"}:
            continue
        if _RAISE_RE.search(path.read_text()):
            raisers.append(path.name)
    if not raisers:
        return  # no raises, no errors.py needed
    assert (pkg / "errors.py").exists(), (
        f"{pkg.relative_to(ROOT)} has raises in {raisers} but no "
        "errors.py. Add typed exception classes so callers can catch "
        "specifically rather than catching generic ValueError."
    )


@pytest.mark.parametrize(
    "pkg", REPO_PACKAGES, ids=lambda p: p.relative_to(ROOT).as_posix()
)
def test_repository_file_does_not_define_dtos(pkg: Path) -> None:
    """Pydantic DTOs (request / response shapes) live in `models.py`,
    not in `repository.py`. SQLModel tables are exempt — they live in
    `models.py` anyway by convention, and a BaseModel definition that
    extends a SQLModel is unusual enough to flag if it appears in
    `repository.py`."""

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
```

- [x] **Step 2: Run the guard**

```bash
uv run pytest ergon_core/tests/unit/architecture/test_repository_companion_files.py -q
```

Expected violators (each gets an xfail marker in Step 3):

- `experiments/`: `test_package_has_errors_py_if_it_raises` fails —
  `repository.py` raises `ValueError` without an `errors.py`.
- `telemetry/`: `test_repository_file_does_not_define_dtos` fails —
  `CreateTaskEvaluation` lives in `repositories.py`.

- [x] **Step 3: Add the xfail markers**

Wrap each violator case via parametrize-id targeting:

```python
_PACKAGE_XFAILS = {
    ("core/application/experiments", "test_package_has_errors_py_if_it_raises"):
        "PR 7: add experiments/errors.py with DefinitionNotFoundError etc.",
    ("core/persistence/telemetry", "test_repository_file_does_not_define_dtos"):
        "PR 4: move CreateTaskEvaluation to telemetry/models.py",
}
```

Implement the marker application via a pytest hook in the same file
(see PR 0's `_XFAIL_BY_NAME` pattern for the shape).

## Task 4: Add `test_no_dead_repository_methods.py`

**Files:**

- Create: `ergon_core/tests/unit/architecture/test_no_dead_repository_methods.py`

- [x] **Step 1: Write the guard file**

```python
"""Dead-method audit on the repository layer.

Every public method on every Repository class must have at least one
production caller (non-test file). The audit is scoped tightly to the
repository layer rather than tree-wide because that's where v1's audit
found real dead helpers — going wider has too much false-positive noise
from Inngest registration, Pydantic decorators, etc.

Methods that are PR-scheduled to land callers later (or to be deleted)
are listed in `_KNOWN_UNUSED_FOR_NOW`, mirroring PR 0's
`_XFAIL_BY_SYMBOL` pattern in test_dead_path_audit.py.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOTS = (
    ROOT / "ergon_core" / "ergon_core",
    ROOT / "ergon_builtins" / "ergon_builtins",
    ROOT / "ergon_cli" / "ergon_cli",
)
EXEMPT_PARTS: frozenset[str] = frozenset({"tests", "migrations", "__pycache__"})


def _discover_repository_classes() -> list[type]:
    # Re-use the same discovery as test_repository_layer_conventions —
    # in practice, import the helper from there.
    from ergon_core.tests.unit.architecture import test_repository_layer_conventions as conv

    return conv.REPO_CLASSES


def _all_public_methods() -> list[tuple[type, str]]:
    methods: list[tuple[type, str]] = []
    for cls in _discover_repository_classes():
        for name, _ in inspect.getmembers(cls, inspect.isfunction):
            if not name.startswith("_"):
                methods.append((cls, name))
    return methods


def _grep_production_callers(
    pattern: str, exclude_path: Path | None = None
) -> list[str]:
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


# Methods that have no production callers AND are expected to land one
# (or be deleted) by a specific PR. Mirrors PR 0's _XFAIL_BY_SYMBOL.
_KNOWN_UNUSED_FOR_NOW: dict[tuple[str, str], str] = {
    # Populate with the audit findings from the first run.
    # ("TaskExecutionRepository", "latest_for_definition_task"): "PR 11: callers go away with the cutover",
    # ("TaskExecutionRepository", "next_attempt_for_definition_task"): "PR 11: callers go away with the cutover",
}


def _cases() -> list:
    cases = []
    for cls, method in _all_public_methods():
        marks = []
        key = (cls.__name__, method)
        reason = _KNOWN_UNUSED_FOR_NOW.get(key)
        if reason is not None:
            marks.append(pytest.mark.xfail(reason=reason, strict=True))
        cases.append(
            pytest.param(cls, method, marks=marks, id=f"{cls.__name__}.{method}")
        )
    return cases


@pytest.mark.parametrize("cls,method", _cases())
def test_repository_method_has_a_production_caller(
    cls: type, method: str
) -> None:
    """Pattern `.method(` catches the common call form. Defining-file is
    excluded so the method's own definition doesn't count as its caller."""

    defining_file = Path(inspect.getfile(cls))
    callers = _grep_production_callers(
        f".{method}(", exclude_path=defining_file
    )
    assert callers, (
        f"{cls.__name__}.{method} has no production callers. "
        "Either add a caller, delete the method, or add to "
        "_KNOWN_UNUSED_FOR_NOW with the landing PR."
    )
```

- [ ] **Step 2: Run the guard and populate the allowlist**

```bash
uv run pytest ergon_core/tests/unit/architecture/test_no_dead_repository_methods.py -q
```

Expected: a handful of FAILs surface today. Add each to
`_KNOWN_UNUSED_FOR_NOW` with the landing PR that either ships a caller
or deletes the method. PR 11's structural simplification audit (§ Task 5
of `12-pr-11-deletion-final-schema.md`) is the natural deletion gate
for most of these.

Run again — all FAILs should now be XFAIL. The completion bar mirrors
the other ledgers: PR 11 asserts `_KNOWN_UNUSED_FOR_NOW == {}`.

## Task 5: Register Initial XFails For Today's Violators

**Files:**

- Modify: `ergon_core/tests/unit/architecture/test_repository_layer_conventions.py`
- Modify: `ergon_core/tests/unit/architecture/test_repository_companion_files.py`

- [ ] **Step 1: Map known violators to landing PRs**

```python
_KNOWN_VIOLATORS: dict[tuple[str, str], str] = {
    # (test_name, parametrize_id) -> "<PR>: <fix>"
    ("test_repository_file_is_singular", "TelemetryRepository"):
        "PR 1: rename telemetry/repositories.py -> telemetry/repository.py",
    ("test_package_has_errors_py_if_it_raises",
     "ergon_core/ergon_core/core/application/experiments"):
        "PR 7: add experiments/errors.py with typed DefinitionNotFoundError "
        "and replace ValueError raises",
    ("test_repository_file_does_not_define_dtos",
     "ergon_core/ergon_core/core/persistence/telemetry"):
        "PR 4: move CreateTaskEvaluation to telemetry/models.py",
}
```

- [ ] **Step 2: Apply via `pytest_collection_modifyitems`**

In each of the two test files, add:

```python
def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    for item in items:
        # item.name is "test_name[param_id]"; split it.
        if "[" not in item.name:
            continue
        test_name, _, param = item.name.partition("[")
        param = param.rstrip("]")
        reason = _KNOWN_VIOLATORS.get((test_name, param))
        if reason is not None:
            item.add_marker(pytest.mark.xfail(reason=reason, strict=True))
```

- [ ] **Step 3: Verify ledger state**

```bash
uv run pytest \
  ergon_core/tests/unit/architecture/test_repository_layer_conventions.py \
  ergon_core/tests/unit/architecture/test_repository_companion_files.py \
  ergon_core/tests/unit/architecture/test_no_dead_repository_methods.py -q
```

Expected: all cases PASS or XFAIL. Zero FAIL, zero XPASS.

## Task 6: Add Completion-Bar Assertions

**Files:**

- Modify: `ergon_core/tests/unit/architecture/test_repository_layer_conventions.py`
- Modify: `ergon_core/tests/unit/architecture/test_repository_companion_files.py`
- Modify: `ergon_core/tests/unit/architecture/test_no_dead_repository_methods.py`

Mirror PR 11's `test_no_*_are_still_xfailed` pattern. Each ledger gets a
guard that PR 11 will assert against:

```python
def test_no_repository_violators_remain() -> None:
    assert _KNOWN_VIOLATORS == {}, (
        f"Repository layer cleanup incomplete — violators remain: "
        f"{sorted(_KNOWN_VIOLATORS)}"
    )


def test_no_dead_repository_methods_remain() -> None:
    assert _KNOWN_UNUSED_FOR_NOW == {}, (
        f"Repository layer dead-method audit incomplete: "
        f"{sorted(_KNOWN_UNUSED_FOR_NOW)}"
    )
```

These tests are themselves `xfail(strict=True)` until PR 11 lands —
PR 11 removes the xfail decorator on these two as part of its empty-the-
ledgers task.

## Task 7: Commit

```bash
git add ergon_core/tests/unit/architecture/test_repository_layer_conventions.py \
        ergon_core/tests/unit/architecture/test_repository_companion_files.py \
        ergon_core/tests/unit/architecture/test_no_dead_repository_methods.py \
        docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/07-test-strategy.md \
        docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan
git commit -m "test: add repository layer standard guards"
```

## PR Ledger

Invariant landed: the repository layer has a documented, enforced
standard; current violators are listed with their fix PR; the
dead-method audit is scoped to repositories with an xfail allowlist.

Bridge code introduced: none.

Old path still intentionally alive: `telemetry/repositories.py` (PR 1
renames), `CreateTaskEvaluation` inline (PR 4 moves), `ValueError`
raises in `experiments/repository.py` (PR 7 replaces).

Deletion gate: PR 11 empties `_KNOWN_VIOLATORS` and
`_KNOWN_UNUSED_FOR_NOW`, and removes the `xfail` decorators from
the completion-bar tests in this PR.

Tests added or updated: three new architecture guards; references
added to `07-test-strategy.md`.

Modules owned by this PR: architecture tests and docs only.
