# PR 03: Shared Output, Errors, Exit Codes, And Command Models

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce shared CLI contracts and convert low-risk domains away from
raw `argparse.Namespace` implementation flow.

**Architecture:** Commands translate argparse into typed Pydantic models;
services operate on typed inputs/results; rendering happens through shared
output helpers.

**Tech Stack:** Pydantic v2, argparse boundary modules, pytest.

---

## Goal

Stop pushing `argparse.Namespace` into implementation code by adding shared CLI
contracts for typed commands, output rendering, and error handling.

## Source PRDs

- `../README.md`
- `../01-smell-remediation-map.md`
- `../02-target-folder-shape.md`

## Scope

## Current State

Command modules accept `argparse.Namespace` directly, print from helper
functions, raise `SystemExit` ad hoc, and mix user output with domain checks.

## Target State For This PR

Converted domains follow:

```text
argparse.Namespace -> Pydantic command model -> service -> result model -> shared.output
```

## Tasks

### Add shared CLI primitives

Create:

```text
ergon_cli/ergon_cli/shared/
  __init__.py
  errors.py
  exit_codes.py
  output.py
  parsing.py
```

Work:

- [ ] **Step 1: Add exit codes**

  In `exit_codes.py`:

  ```python
  OK = 0
  USAGE = 2
  NOT_FOUND = 3
  RUNTIME_ERROR = 1
  ```

- [ ] **Step 2: Add CLI errors**

  In `errors.py`, define `CliError(message: str, exit_code: int)` plus focused
  subclasses for usage, not-found, and dependency errors.

- [ ] **Step 3: Add output helpers**

  In `output.py`, add helpers for table/text/json rendering. Keep printing at
  command boundary:

  ```python
  def render_json(payload: BaseModel | Mapping[str, object]) -> str: ...
  def render_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str: ...
  ```

- [ ] **Step 4: Add parsing helpers**

  In `parsing.py`, add UUID parsing that raises `CliUsageError`, not raw
  `ValueError`.

Acceptance:

- Command handlers can return result objects or raise CLI errors without
  directly calling `SystemExit`.

### Convert low-risk domains first

Modify:

```text
ergon_cli/ergon_cli/domains/doctor/
ergon_cli/ergon_cli/domains/stack/
ergon_cli/ergon_cli/domains/workers/
ergon_cli/ergon_cli/domains/evaluators/
```

Create per domain as needed:

```text
commands.py
models.py
service.py
```

Work:

- [ ] **Step 1: Convert worker/evaluator list**

  Add tiny command/result models and route output through `shared.output`.

- [ ] **Step 2: Convert doctor**

  Add `DoctorCommand` and `DoctorReport`. Check helpers should return data, not
  print directly.

- [ ] **Step 3: Convert stack**

  Add `StackCommand(action: Literal["start", "stop"])` and keep subprocess
  execution in a service.

- [ ] **Step 4: Add boundary assertions**

  Tests should fail if converted services import `argparse`.

Acceptance:

- `argparse.Namespace` does not pass below each converted domain's
  `commands.py`.
- Converted domains have predictable output behavior.

### Leave high-coupling domains for later PRs

Do not convert yet:

- runs
- experiments
- benchmarks/onboarding metadata ownership
- training optional dependency behavior beyond small error handling cleanup

## Tests

Add or update:

- `ergon_cli/tests/unit/cli/test_shared_output.py`
- `ergon_cli/tests/unit/cli/test_shared_errors.py`
- domain tests for doctor, stack, worker list, evaluator list

Run:

```bash
uv run ruff check ergon_cli/ergon_cli
uv run pytest ergon_cli/tests/unit/cli
```

## PR Ledger

- **Invariant landed:** converted domains no longer pass `argparse.Namespace`
  below `commands.py`.
- **Bridge code introduced:** shared CLI primitives used by only low-risk
  domains at first.
- **Old path still intentionally alive:** runs, experiments, benchmarks,
  onboarding, training remain partially unconverted.
- **Deletion gate:** PR 06 final architecture tests enforce this globally.
- **Tests added or updated:** shared output/error tests and converted domain
  tests.
- **Modules owned by this PR:** `shared/*`, doctor, stack, workers, evaluators.

## Out Of Scope

- Direct persistence cleanup in runs/experiments.
- Final folder migration.
- Builtins metadata catalogue.

## Depends On

- PR 02
