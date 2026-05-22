# PR 02: CLI Composition Root And Parser Split

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `main.py` a console-script shim and move parser registration
into domain-local modules without changing command semantics.

**Architecture:** Introduce the final domain package names while leaving old
command implementation modules in place. This is a composition-only PR.

**Tech Stack:** argparse, pytest parser tests, existing command handlers.

---

## Goal

Make `ergon_cli.main` a thin composition root by moving parser registration into
domain-local modules without changing command behavior.

## Source PRDs

- `../README.md`
- `../02-target-folder-shape.md`

## Scope

## Current State

`ergon_cli.main.build_parser()` defines all command groups, all flags, and the
top-level dispatch maps in one file. Every CLI change touches the central
entrypoint.

## Target State For This PR

`main.py` delegates to `app.py`; `app.py` calls one parser registration function
per domain. Existing command handlers still live under `ergon_cli.commands`.

## Tasks

### Add app composition module

Create:

- `ergon_cli/ergon_cli/app.py`

Modify:

- `ergon_cli/ergon_cli/main.py`

Work:

- [ ] **Step 1: Create `app.py`**

  Add:

  ```python
  def build_parser() -> argparse.ArgumentParser:
      parser = argparse.ArgumentParser(...)
      subparsers = parser.add_subparsers(dest="command")
      register_run_parser(subparsers)
      register_experiment_parser(subparsers)
      ...
      return parser
  ```

- [ ] **Step 2: Shrink `main.py`**

  `main.py` should import `build_parser` from `app.py` and keep the console
  entrypoint plus a small dispatch helper.

- [ ] **Step 3: Preserve behavior**

  Do not change flag names, defaults, or command handlers in this PR.

Acceptance:

- `main.py` contains no domain-specific flag definitions after this PR.

### Create domain parser modules

Create:

```text
ergon_cli/ergon_cli/domains/
  __init__.py
  benchmarks/parser.py
  doctor/parser.py
  eval/parser.py
  evaluators/parser.py
  experiments/parser.py
  ingestion/parser.py
  onboarding/parser.py
  runs/parser.py
  stack/parser.py
  training/parser.py
  workers/parser.py
  workflow/parser.py
```

Work:

- [ ] **Step 1: Create domain package skeleton**

  Create the listed `domains/*/parser.py` files with one
  `register_<domain>_parser(subparsers)` function per domain.

- [ ] **Step 2: Move parser code verbatim**

  Move the existing argparse setup from `main.py` into matching parser modules.
  Keep imports pointed at old `ergon_cli.commands.*` handlers.

- [ ] **Step 3: Add parser smoke tests**

  For each command group, parse at least one representative command to ensure
  `command` and action fields match the old behavior.

Acceptance:

- Adding a flag for one domain does not require editing `main.py`.
- Existing CLI commands parse the same arguments as before.

### Simplify dispatch

Modify:

- `ergon_cli/ergon_cli/app.py`
- `ergon_cli/ergon_cli/main.py`

Work:

- [ ] **Step 1: Bind handlers at parse time**

  Prefer:

  ```python
  parser.set_defaults(handler=handle_run)
  ```

  on each command group, or keep one central registry if handler binding creates
  too much churn.

- [ ] **Step 2: Add one async-aware dispatch helper**

  ```python
  async def dispatch(args: argparse.Namespace) -> int:
      result = args.handler(args)
      if inspect.isawaitable(result):
          return await result
      return result
  ```

- [ ] **Step 3: Preserve help behavior**

  Missing command/help cases should behave as before.

Acceptance:

- There is one obvious command execution path.
- Unknown or missing commands still print help and return the expected exit
  code.

## Tests

Add or update:

- `ergon_cli/tests/unit/cli/test_parser_registration.py`
- existing command parser tests

Run:

```bash
uv run ruff check ergon_cli/ergon_cli
uv run pytest ergon_cli/tests/unit/cli
```

## PR Ledger

- **Invariant landed:** `main.py` contains no domain-specific parser
  registration.
- **Bridge code introduced:** domain parser modules importing old command
  handlers.
- **Old path still intentionally alive:** `ergon_cli.commands.*`.
- **Deletion gate:** PR 06 removes old command package references.
- **Tests added or updated:** parser registration smoke tests.
- **Modules owned by this PR:** `app.py`, `main.py`, `domains/*/parser.py`.

## Out Of Scope

- Moving command implementation modules.
- Introducing typed command models.
- Rewriting output/error handling.

## Depends On

- PR 00
- PR 01 if workflow parser churn overlaps
