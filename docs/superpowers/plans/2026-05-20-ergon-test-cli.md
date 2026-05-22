# Ergon Test CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public `ergon test` command that runs the repo's common test suites by domain and suite type without exposing contributors to long pytest/pnpm incantations.

**Architecture:** Keep test selection logic in the Python CLI as the canonical source of truth, with root `package.json` scripts as thin aliases. Do not add per-package `package.json` files to Python subdomains; those packages already use `pyproject.toml`, and extra JS package manifests would create a second ownership model. Implement the command as a typed catalog of known suites plus a small subprocess runner that prints the command before executing it.

**Tech Stack:** Python argparse, Pydantic command models, subprocess execution, pytest via `uv run`, dashboard tests via `pnpm -C ergon-dashboard`, root `package.json` aliases.

---

## Proposed Public Interface

```bash
ergon test list
ergon test smoke
ergon test smoke researchrubrics
ergon test smoke minif2f
ergon test smoke swebench-verified
ergon test full unit
ergon test core unit
ergon test builtins unit
ergon test cli unit
ergon test ingestion unit
ergon test dashboard unit
ergon test backend integration
ergon test full smoke
ergon test backend smoke
ergon test dashboard smoke
ergon test backend e2e
ergon test real-llm full
ergon test full full
```

Common options:

```bash
ergon test cli unit --dry-run
ergon test core unit -- -k runtime
ergon test backend integration -- --maxfail=1
ergon test smoke "${SMOKE_ENV}" -- --timeout=330 --tb=short
```

Behavior:

- `--dry-run` prints the resolved command and exits `0`.
- Arguments after `--` are appended to the underlying pytest/pnpm command.
- No suite defaults to all domains implicitly; use the explicit `full` domain, as in `ergon test full unit`.
- `ergon test smoke` is the canonical benchmark smoke entrypoint. It runs all canonical benchmark smoke files by default; pass a benchmark slug to run one matrix leg.
- `ergon test full full` runs backend unit, backend integration, dashboard unit, and dashboard contracts. It should not run real-LLM or browser e2e by default.
- `ergon test real-llm full` remains explicit because it requires credentials and can spend money.

## Command Catalog

Use this initial suite map:

| Public command | Underlying command |
| --- | --- |
| `ergon test smoke` | all canonical benchmark smoke files in `tests/e2e` |
| `ergon test smoke researchrubrics` | `uv run pytest tests/e2e/test_researchrubrics_smoke.py -v` |
| `ergon test smoke minif2f` | `uv run pytest tests/e2e/test_minif2f_smoke.py -v` |
| `ergon test smoke swebench-verified` | `uv run pytest tests/e2e/test_swebench_smoke.py -v` |
| `ergon test full unit` | `uv run pytest ergon_core/tests/unit ergon_builtins/tests/unit ergon_cli/tests/unit ergon_ingestion/tests/unit -q -n auto --durations=20` |
| `ergon test core unit` | `uv run pytest ergon_core/tests/unit -q -n auto --durations=20` |
| `ergon test builtins unit` | `uv run pytest ergon_builtins/tests/unit -q -n auto --durations=20` |
| `ergon test cli unit` | `uv run pytest ergon_cli/tests/unit -q -n auto --durations=20` |
| `ergon test ingestion unit` | `uv run pytest ergon_ingestion/tests/unit -q -n auto --durations=20` |
| `ergon test dashboard unit` | `pnpm -C ergon-dashboard run test:unit` |
| `ergon test backend integration` | `uv run pytest tests/integration -v --timeout=300` |
| `ergon test full smoke` | `uv run pytest tests/integration/smokes -v --timeout=300` then `pnpm -C ergon-dashboard run e2e:live` |
| `ergon test backend smoke` | `uv run pytest tests/integration/smokes -v --timeout=300` |
| `ergon test dashboard smoke` | `pnpm -C ergon-dashboard run e2e:live` |
| `ergon test backend e2e` | `uv run pytest tests/e2e -v` |
| `ergon test real-llm full` | `ERGON_REAL_LLM=1 uv run pytest tests/real_llm -v` |
| `ergon test full full` | unit full, integration backend, dashboard unit, dashboard contracts |

## Files

- Create: `ergon_cli/ergon_cli/domains/tests/__init__.py`
- Create: `ergon_cli/ergon_cli/domains/tests/models.py`
- Create: `ergon_cli/ergon_cli/domains/tests/catalog.py`
- Create: `ergon_cli/ergon_cli/domains/tests/service.py`
- Create: `ergon_cli/ergon_cli/domains/tests/commands.py`
- Create: `ergon_cli/ergon_cli/domains/tests/parser.py`
- Modify: `ergon_cli/ergon_cli/app.py`
- Modify: `package.json`
- Modify: `.github/workflows/ci-fast.yml`
- Modify: `.github/workflows/e2e-benchmarks.yml`
- Modify: `CLAUDE.md`
- Create: `ergon_cli/tests/unit/cli/test_test_cli.py`
- Modify: `ergon_cli/tests/unit/cli/test_parser_registration.py`

---

### Task 1: Public Parser Contract

**Files:**
- Modify: `ergon_cli/tests/unit/cli/test_parser_registration.py`
- Create: `ergon_cli/tests/unit/cli/test_test_cli.py`

- [ ] **Step 1: Write failing parser tests**

Add this to `ergon_cli/tests/unit/cli/test_parser_registration.py`:

```python
def test_test_command_is_public() -> None:
    args = build_parser().parse_args(["test", "cli", "unit"])

    assert callable(args.handler)
    assert args.command == "test"
    assert args.test_domain == "cli"
    assert args.test_suite == "unit"
```

Create `ergon_cli/tests/unit/cli/test_test_cli.py`:

```python
from argparse import Namespace

import pytest

import ergon_cli.domains.tests.service as test_service
from ergon_cli.domains.tests.commands import handle_test
from ergon_cli.domains.tests.models import TestCommand


def test_unit_cli_resolves_to_cli_pytest_command() -> None:
    command = test_service.resolve_test_command(
        TestCommand(suite="unit", domain="cli", dry_run=True, extra_args=())
    )

    assert command.commands == (
        ("uv", "run", "pytest", "ergon_cli/tests/unit", "-q", "-n", "auto", "--durations=20"),
    )


def test_extra_args_are_appended_to_each_resolved_command() -> None:
    command = test_service.resolve_test_command(
        TestCommand(suite="unit", domain="cli", dry_run=True, extra_args=("-k", "parser"))
    )

    assert command.commands[0][-2:] == ("-k", "parser")


def test_dry_run_prints_command_without_executing(monkeypatch, capsys) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run must not execute subprocesses")

    monkeypatch.setattr(test_service.subprocess, "run", fail_if_called)

    rc = handle_test(
        Namespace(test_suite="unit", test_domain="cli", dry_run=True, extra_args=[])
    )

    assert rc == 0
    assert "uv run pytest ergon_cli/tests/unit" in capsys.readouterr().out


def test_full_unit_is_explicit_all_unit_command() -> None:
    command = test_service.resolve_test_command(
        TestCommand(suite="unit", domain="full", dry_run=True, extra_args=())
    )

    assert command.commands == (
        (
            "uv",
            "run",
            "pytest",
            "ergon_core/tests/unit",
            "ergon_builtins/tests/unit",
            "ergon_cli/tests/unit",
            "ergon_ingestion/tests/unit",
            "-q",
            "-n",
            "auto",
            "--durations=20",
        ),
    )


def test_benchmark_smoke_target_resolves_to_one_e2e_file() -> None:
    command = test_service.resolve_test_command(
        TestCommand(domain="smoke", suite="swebench-verified", dry_run=True, extra_args=())
    )

    assert command.commands == (
        ("uv", "run", "pytest", "tests/e2e/test_swebench_smoke.py", "-v"),
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest ergon_cli/tests/unit/cli/test_parser_registration.py ergon_cli/tests/unit/cli/test_test_cli.py -q
```

Expected: fail because `ergon_cli.domains.tests` and `ergon test` do not exist yet.

### Task 2: Test Command Models and Catalog

**Files:**
- Create: `ergon_cli/ergon_cli/domains/tests/__init__.py`
- Create: `ergon_cli/ergon_cli/domains/tests/models.py`
- Create: `ergon_cli/ergon_cli/domains/tests/catalog.py`

- [ ] **Step 1: Create models**

Create `ergon_cli/ergon_cli/domains/tests/models.py`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict


TestSuite = Literal[
    "list",
    "unit",
    "integration",
    "smoke",
    "e2e",
    "full",
    "researchrubrics",
    "minif2f",
    "swebench-verified",
]
TestDomain = Literal[
    "smoke", "full", "core", "builtins", "cli", "ingestion", "dashboard", "backend", "real-llm"
]


class TestCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    suite: TestSuite
    domain: TestDomain = "full"
    dry_run: bool = False
    extra_args: tuple[str, ...] = ()


class ResolvedTestCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    commands: tuple[tuple[str, ...], ...]
```

- [ ] **Step 2: Create command catalog**

Create `ergon_cli/ergon_cli/domains/tests/catalog.py` with constants for command tuples. Include no subprocess calls in this file.

```python
PY_UNIT_FLAGS = ("-q", "-n", "auto", "--durations=20")

PYTHON_UNIT_COMMANDS = {
    "core": ("uv", "run", "pytest", "ergon_core/tests/unit", *PY_UNIT_FLAGS),
    "builtins": ("uv", "run", "pytest", "ergon_builtins/tests/unit", *PY_UNIT_FLAGS),
    "cli": ("uv", "run", "pytest", "ergon_cli/tests/unit", *PY_UNIT_FLAGS),
    "ingestion": ("uv", "run", "pytest", "ergon_ingestion/tests/unit", *PY_UNIT_FLAGS),
}

PYTHON_UNIT_ALL = (
    "uv",
    "run",
    "pytest",
    "ergon_core/tests/unit",
    "ergon_builtins/tests/unit",
    "ergon_cli/tests/unit",
    "ergon_ingestion/tests/unit",
    *PY_UNIT_FLAGS,
)

DASHBOARD_UNIT = ("pnpm", "-C", "ergon-dashboard", "run", "test:unit")
DASHBOARD_CONTRACTS = ("pnpm", "-C", "ergon-dashboard", "run", "test:contracts")
BACKEND_INTEGRATION = ("uv", "run", "pytest", "tests/integration", "-v", "--timeout=300")
BACKEND_SMOKE = ("uv", "run", "pytest", "tests/integration/smokes", "-v", "--timeout=300")
BACKEND_E2E = ("uv", "run", "pytest", "tests/e2e", "-v")
REAL_LLM = ("uv", "run", "pytest", "tests/real_llm", "-v")
DASHBOARD_SMOKE = ("pnpm", "-C", "ergon-dashboard", "run", "e2e:live")
BENCHMARK_SMOKE_COMMANDS = {
    "researchrubrics": ("uv", "run", "pytest", "tests/e2e/test_researchrubrics_smoke.py", "-v"),
    "minif2f": ("uv", "run", "pytest", "tests/e2e/test_minif2f_smoke.py", "-v"),
    "swebench-verified": ("uv", "run", "pytest", "tests/e2e/test_swebench_smoke.py", "-v"),
}
BENCHMARK_SMOKE_ALL = (
    "uv",
    "run",
    "pytest",
    "tests/e2e/test_researchrubrics_smoke.py",
    "tests/e2e/test_minif2f_smoke.py",
    "tests/e2e/test_swebench_smoke.py",
    "-v",
)
```

- [ ] **Step 3: Run model/import tests**

Run:

```bash
uv run python -c "from ergon_cli.domains.tests.models import TestCommand; print(TestCommand(domain='cli', suite='unit'))"
```

Expected: prints a valid `TestCommand`.

### Task 3: Resolver and Runner

**Files:**
- Create: `ergon_cli/ergon_cli/domains/tests/service.py`
- Test: `ergon_cli/tests/unit/cli/test_test_cli.py`

- [ ] **Step 1: Implement resolver and runner**

Create `ergon_cli/ergon_cli/domains/tests/service.py`:

```python
import os
import subprocess

from ergon_cli.domains.tests.catalog import (
    BACKEND_E2E,
    BACKEND_INTEGRATION,
    BACKEND_SMOKE,
    BENCHMARK_SMOKE_ALL,
    BENCHMARK_SMOKE_COMMANDS,
    DASHBOARD_CONTRACTS,
    DASHBOARD_SMOKE,
    DASHBOARD_UNIT,
    PYTHON_UNIT_ALL,
    PYTHON_UNIT_COMMANDS,
    REAL_LLM,
)
from ergon_cli.domains.tests.models import ResolvedTestCommand, TestCommand
from ergon_cli.shared import exit_codes


def resolve_test_command(command: TestCommand) -> ResolvedTestCommand:
    if command.suite == "list":
        return ResolvedTestCommand(label="Available test suites", commands=())
    if command.domain == "smoke":
        commands = _benchmark_smoke_commands(command.suite)
    elif command.suite == "unit":
        commands = _unit_commands(command.domain)
    elif command.suite == "integration":
        _require_domain(command, "backend")
        commands = (BACKEND_INTEGRATION,)
    elif command.suite == "smoke":
        commands = _smoke_commands(command.domain)
    elif command.suite == "e2e":
        _require_domain(command, "backend")
        commands = (BACKEND_E2E,)
    elif command.domain == "real-llm" and command.suite == "full":
        commands = (REAL_LLM,)
    elif command.domain == "full" and command.suite == "full":
        commands = (PYTHON_UNIT_ALL, BACKEND_INTEGRATION, DASHBOARD_UNIT, DASHBOARD_CONTRACTS)
    else:
        raise ValueError(f"unsupported test target: {command.domain} {command.suite}")
    return ResolvedTestCommand(
        label=f"{command.domain}:{command.suite}",
        commands=tuple((*cmd, *command.extra_args) for cmd in commands),
    )


def run_test_command(command: TestCommand) -> int:
    resolved = resolve_test_command(command)
    if command.suite == "list":
        print_available_suites()
        return exit_codes.OK
    for argv in resolved.commands:
        print(f"$ {' '.join(argv)}")
        if command.dry_run:
            continue
        env = os.environ.copy()
        if command.domain == "real-llm":
            env["ERGON_REAL_LLM"] = "1"
        result = subprocess.run(argv, check=False, env=env)
        if result.returncode != 0:
            return result.returncode
    return exit_codes.OK


def print_available_suites() -> None:
    print("smoke: full, researchrubrics, minif2f, swebench-verified")
    print("full: unit, smoke, full")
    print("core: unit")
    print("builtins: unit")
    print("cli: unit")
    print("ingestion: unit")
    print("dashboard: unit, smoke")
    print("backend: integration, smoke, e2e")
    print("real-llm: full")


def _unit_commands(domain: str) -> tuple[tuple[str, ...], ...]:
    if domain == "full":
        return (PYTHON_UNIT_ALL,)
    if domain == "dashboard":
        return (DASHBOARD_UNIT,)
    if domain in PYTHON_UNIT_COMMANDS:
        return (PYTHON_UNIT_COMMANDS[domain],)
    raise ValueError(f"unit tests do not support domain {domain!r}")


def _smoke_commands(domain: str) -> tuple[tuple[str, ...], ...]:
    if domain == "full":
        return (BACKEND_SMOKE, DASHBOARD_SMOKE)
    if domain == "backend":
        return (BACKEND_SMOKE,)
    if domain == "dashboard":
        return (DASHBOARD_SMOKE,)
    raise ValueError(f"smoke tests do not support domain {domain!r}")


def _benchmark_smoke_commands(target: str) -> tuple[tuple[str, ...], ...]:
    if target == "full":
        return (BENCHMARK_SMOKE_ALL,)
    if target in BENCHMARK_SMOKE_COMMANDS:
        return (BENCHMARK_SMOKE_COMMANDS[target],)
    raise ValueError(f"benchmark smoke tests do not support target {target!r}")


def _require_domain(command: TestCommand, expected: str) -> None:
    if command.domain != expected:
        raise ValueError(f"{command.suite} tests require domain {expected!r}")
```

- [ ] **Step 2: Run resolver tests**

Run:

```bash
uv run pytest ergon_cli/tests/unit/cli/test_test_cli.py -q
```

Expected: failing only because command handler/parser are not created yet, or passing for resolver-only tests if imports are complete.

### Task 4: Command Handler and Parser

**Files:**
- Create: `ergon_cli/ergon_cli/domains/tests/commands.py`
- Create: `ergon_cli/ergon_cli/domains/tests/parser.py`
- Modify: `ergon_cli/ergon_cli/app.py`

- [ ] **Step 1: Create command handler**

Create `ergon_cli/ergon_cli/domains/tests/commands.py`:

```python
from argparse import Namespace

from ergon_cli.domains.tests.models import TestCommand
from ergon_cli.domains.tests.service import run_test_command


def handle_test(args: Namespace) -> int:
    return run_test_command(
        TestCommand(
            domain=args.test_domain,
            suite=args.test_suite,
            dry_run=args.dry_run,
            extra_args=tuple(args.extra_args or ()),
        )
    )
```

- [ ] **Step 2: Create parser**

Create `ergon_cli/ergon_cli/domains/tests/parser.py`:

```python
import argparse

from ergon_cli.domains.tests.commands import handle_test


def register_test_parser(subparsers: argparse._SubParsersAction) -> None:
    test = subparsers.add_parser("test", help="Run Ergon test suites")
    test.set_defaults(handler=handle_test)
    domain_sub = test.add_subparsers(dest="test_domain", required=True)

    list_parser = domain_sub.add_parser("list", help="List available test suites")
    list_parser.set_defaults(test_suite="list")
    list_parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    list_parser.add_argument("extra_args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)

    smoke_parser = domain_sub.add_parser("smoke", help="Run canonical benchmark smoke tests")
    smoke_parser.add_argument(
        "test_suite",
        nargs="?",
        default="full",
        choices=("full", "researchrubrics", "minif2f", "swebench-verified"),
        help="Benchmark smoke target",
    )
    smoke_parser.add_argument("--dry-run", action="store_true", help="Print command without running")
    smoke_parser.add_argument("extra_args", nargs=argparse.REMAINDER, help="Extra args after --")

    _add_domain(domain_sub, "full", "Run suites across all applicable domains", ("unit", "smoke", "full"))
    _add_domain(domain_sub, "core", "Run core tests", ("unit",))
    _add_domain(domain_sub, "builtins", "Run builtins tests", ("unit",))
    _add_domain(domain_sub, "cli", "Run CLI tests", ("unit",))
    _add_domain(domain_sub, "ingestion", "Run ingestion tests", ("unit",))
    _add_domain(domain_sub, "dashboard", "Run dashboard tests", ("unit", "smoke"))
    _add_domain(domain_sub, "backend", "Run backend cross-package tests", ("integration", "smoke", "e2e"))
    _add_domain(domain_sub, "real-llm", "Run real-LLM tests", ("full",))


def _add_domain(
    domain_sub: argparse._SubParsersAction,
    name: str,
    help_text: str,
    suites: tuple[str, ...],
) -> None:
    parser = domain_sub.add_parser(name, help=help_text)
    suite_sub = parser.add_subparsers(dest="test_suite", required=True)
    for suite in suites:
        suite_parser = suite_sub.add_parser(suite)
        suite_parser.add_argument("--dry-run", action="store_true", help="Print command without running")
        suite_parser.add_argument("extra_args", nargs=argparse.REMAINDER, help="Extra args after --")
```

- [ ] **Step 3: Register parser in composition root**

Modify `ergon_cli/ergon_cli/app.py`:

```python
from ergon_cli.domains.tests.parser import register_test_parser
```

and call `register_test_parser(subparsers)` after `register_stack_parser(subparsers)`.

- [ ] **Step 4: Run parser and CLI tests**

Run:

```bash
uv run pytest ergon_cli/tests/unit/cli/test_parser_registration.py ergon_cli/tests/unit/cli/test_test_cli.py -q
```

Expected: all pass.

### Task 5: Package Scripts as Thin Aliases

**Files:**
- Modify: `package.json`

- [ ] **Step 1: Replace duplicated test scripts with `ergon test` aliases**

Modify the root `package.json` scripts to keep the common names but delegate to the CLI:

```json
{
  "test:be:unit": "uv run ergon test full unit",
  "test:be:integration": "uv run ergon test backend integration",
  "test:be:all": "uv run ergon test full unit && uv run ergon test backend integration",
  "test:be:e2e": "uv run ergon test backend e2e",
  "test:be:real-llm": "uv run ergon test real-llm full",
  "test:fe:e2e": "pnpm -C ergon-dashboard run e2e",
  "test:fe:e2e:live": "uv run ergon test dashboard smoke",
  "test:be:fast": "uv run ergon test full unit"
}
```

Leave check/lint/type scripts unchanged.

- [ ] **Step 2: Validate package scripts parse**

Run:

```bash
node -e "JSON.parse(require('fs').readFileSync('package.json', 'utf8')); console.log('ok')"
```

Expected: `ok`.

### Task 6: CI as First Customer

**Files:**
- Modify: `.github/workflows/ci-fast.yml`
- Modify: `.github/workflows/e2e-benchmarks.yml`

- [ ] **Step 1: Update Python unit CI to call `ergon test`**

In `.github/workflows/ci-fast.yml`, replace the current unit test command:

```yaml
run: uv run pytest ergon_core/tests/unit ergon_builtins/tests/unit ergon_cli/tests/unit ergon_ingestion/tests/unit -n auto --cov=ergon_core --cov=ergon_builtins --cov-report=xml:coverage.xml
```

with:

```yaml
run: uv run ergon test full unit -- --cov=ergon_core --cov=ergon_builtins --cov-report=xml:coverage.xml
```

Rationale: CI should exercise the public CLI as a real customer, while coverage-only flags remain CI-local pass-through arguments.

- [ ] **Step 2: Update Python integration CI to call `ergon test`**

In `.github/workflows/ci-fast.yml`, replace:

```yaml
run: uv run pytest tests/integration -v --timeout=300
```

with:

```yaml
run: uv run ergon test backend integration
```

- [ ] **Step 3: Update matrix benchmark smoke workflow to call `ergon test smoke`**

In `.github/workflows/e2e-benchmarks.yml`, replace the `Run smoke` shell block:

```yaml
run: |
  # Translate matrix env id to python module name (swebench-verified → swebench).
  case "${SMOKE_ENV}" in
    researchrubrics)    PYFILE="tests/e2e/test_researchrubrics_smoke.py" ;;
    minif2f)            PYFILE="tests/e2e/test_minif2f_smoke.py" ;;
    swebench-verified)  PYFILE="tests/e2e/test_swebench_smoke.py" ;;
    *)                  echo "unknown env ${SMOKE_ENV}" >&2; exit 2 ;;
  esac
  uv run pytest "${PYFILE}" -v --timeout=330 --tb=short
```

with:

```yaml
run: uv run ergon test smoke "${SMOKE_ENV}" -- --timeout=330 --tb=short
```

Rationale: the CLI owns benchmark-smoke target mapping, and the matrix workflow becomes a direct warning sign when that public smoke interface breaks.

- [ ] **Step 4: Validate workflow references**

Run:

```bash
rg -n "uv run pytest ergon_core/tests/unit|uv run pytest tests/integration -v --timeout=300" .github/workflows/ci-fast.yml
```

Expected: no matches.

Run:

```bash
rg -n "uv run ergon test full unit|uv run ergon test backend integration" .github/workflows/ci-fast.yml
```

Expected: both new commands appear.

Run:

```bash
rg -n "PYFILE=|uv run pytest \"\\$\\{PYFILE\\}\"" .github/workflows/e2e-benchmarks.yml
```

Expected: no matches.

Run:

```bash
rg -n "uv run ergon test smoke" .github/workflows/e2e-benchmarks.yml
```

Expected: the matrix smoke workflow calls `ergon test smoke`.

### Task 7: Agent Memory Update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the canonical agent instructions**

In `CLAUDE.md`, replace the current terse `## Tests` section:

````markdown
## Tests

```bash
pnpm run test:be:fast   # Fast unit/state tests
pnpm run test:be:e2e    # E2E tests (requires Docker stack)
```
````

with:

````markdown
## Local stack and tests

Use the Ergon CLI as the canonical local interface for app startup and tests.
Reach for these before raw `docker compose`, `pytest`, or dashboard package
commands unless you are debugging the wrapper itself.

```bash
ergon start   # Start Postgres, API, Inngest, and dashboard
ergon doctor  # Verify local dependencies and service reachability
ergon stop    # Stop the local stack
```

Common test entrypoints:

```bash
ergon test cli unit
ergon test core unit
ergon test full unit
ergon test backend integration
ergon test smoke
ergon test smoke minif2f
ergon test dashboard unit
ergon test full full
```

Use `--dry-run` to see the underlying command:

```bash
ergon test cli unit --dry-run
```

Use `--` to pass pytest or package-runner flags through:

```bash
ergon test core unit -- -k persistence
ergon test smoke swebench-verified -- --timeout=330 --tb=short
```

Root `package.json` test scripts are thin aliases for `ergon test`; CI also
uses `ergon test` as a first customer. Keep these surfaces aligned when adding
or moving tests.
````

- [ ] **Step 2: Confirm companion memory files still point to CLAUDE.md**

Run:

```bash
rg -n "CLAUDE.md|canonical" AGENTS.md CODEX.md
```

Expected: both files continue to identify `CLAUDE.md` as canonical, so no duplicated command matrix is needed there.

### Task 8: Verification

**Files:**
- No new files.

- [ ] **Step 1: Verify dry-run output**

Run:

```bash
uv run ergon test cli unit --dry-run
uv run ergon test full smoke --dry-run
uv run ergon test full full --dry-run
```

Expected: each prints the command(s) it would run and exits `0`.

- [ ] **Step 2: Run focused implementation tests**

Run:

```bash
uv run pytest ergon_cli/tests/unit/cli/test_test_cli.py ergon_cli/tests/unit/cli/test_parser_registration.py -q
```

Expected: all pass.

- [ ] **Step 3: Run full CLI test suite**

Run:

```bash
uv run pytest ergon_cli/tests/unit/cli -q
```

Expected: all pass.

- [ ] **Step 4: Run the new command for one small real suite**

Run:

```bash
uv run ergon test cli unit
```

Expected: `ergon_cli/tests/unit` passes.

## Self-Review

Spec coverage:
- Domain selection is covered by `core unit`, `builtins unit`, `cli unit`, `ingestion unit`, `dashboard unit`, `backend integration`, and the explicit aggregate domain `full unit`.
- Suite selection is covered by `unit`, `integration`, `smoke`, `e2e`, and `full`.
- CI customer coverage is explicit: `ci-fast.yml` uses `ergon test full unit` and `ergon test backend integration`; `e2e-benchmarks.yml` uses `ergon test smoke "${SMOKE_ENV}"`.
- Future-agent memory is covered by `CLAUDE.md`, the canonical instruction file referenced by `AGENTS.md` and `CODEX.md`.
- Package script strategy is covered by root `package.json` aliases; per-subdomain package manifests are intentionally excluded.

Placeholder scan:
- No TBD/TODO placeholders.
- Every file to create or modify is listed with concrete content.

Type consistency:
- Parser fields are `test_domain`, `test_suite`, `dry_run`, and `extra_args`.
- Handler constructs `TestCommand(domain=..., suite=..., dry_run=..., extra_args=...)`.
- Service accepts `TestCommand` and returns `ResolvedTestCommand`.
