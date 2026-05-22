# PR 00: CLI Hygiene Cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete obvious dead/stale CLI code and make unsupported workflow
authoring fail clearly before larger refactors start.

**Architecture:** This is a guardrail PR. It changes the minimum amount of code
needed to stop preserving no-ops, ignored flags, stale discovery slugs, and weak
typing artifacts.

**Tech Stack:** argparse, pytest, ruff, small helper modules.

---

## Goal

Delete obvious dead code and fix stale or misleading CLI behavior before any
large folder migration.

This PR should be small and behavior-preserving except where the current
behavior is plainly wrong or falsely advertised.

## Source PRDs

- `../prds/00-cli-hygiene-audit.md`
- `../01-smell-remediation-map.md`

## Scope

## Current State

- `main.py` imports and calls no-op bootstrap/default-registration helpers.
- `doctor --verbose` is parsed but unused.
- On the PR #91 base, `workflow task-tree` uses task identity
  (`--parent-task-id`). Keep a focused regression test so the parser and
  handler do not drift again.
- Workflow parser exposes mutation actions whose live behavior is missing or
  intentionally rejected by core.
- CLI discovery rows include stale builtins slugs.
- `commands/benchmark.py` contains brittle sandbox template path arithmetic.
- `BuildLog(Protocol)` models only `str(x)`.

## Target State For This PR

- No executable no-op compatibility helpers remain.
- Every audited flag is either implemented or removed.
- Live dynamic task authoring is removed from the human CLI surface; PR 01
  deletes `workflow manage` entirely.
- Static discovery rows are corrected while still marked temporary.
- Benchmark template lookup is isolated behind a helper.

## Tasks

### Delete no-op compatibility code

Modify:

- `ergon_cli/ergon_cli/main.py`
- `ergon_cli/ergon_cli/bootstrap.py`

Work:

- [ ] **Step 1: Remove default component no-op**

  Delete this function from `ergon_cli/ergon_cli/main.py`:

  ```python
  def register_default_components() -> None:
      return None
  ```

- [ ] **Step 2: Remove builtin bootstrap no-op**

  Delete `ergon_cli/ergon_cli/bootstrap.py` if its only production symbol is:

  ```python
  def register_and_publish_builtins() -> None:
      return None
  ```

- [ ] **Step 3: Remove calls/imports**

  Remove imports and conditional calls for both symbols from `main.py`.

- [ ] **Step 4: Verify no references remain**

  ```bash
  rg "register_and_publish_builtins|register_default_components" ergon
  ```

  Expected: no production references.

Acceptance:

- `rg "register_and_publish_builtins|register_default_components" ergon` has
  no production references.
- CLI startup behavior is unchanged.

### Fix or remove unused command flags

Modify:

- `ergon_cli/ergon_cli/main.py`
- `ergon_cli/ergon_cli/commands/doctor.py`
- `ergon_cli/ergon_cli/commands/workflow.py`

Work:

- [ ] **Step 1: Remove `doctor --verbose`**

  Remove parser registration:

  ```python
  doctor.add_argument("--verbose", action="store_true", help="Show detailed output")
  ```

  Do not add a replacement until a real detail mode is specified.

- [ ] **Step 2: Guard `task-tree --parent-task-id`**

  On the PR #91 base, the handler should read:

  ```python
  parent = UUID(args.parent_task_id) if args.parent_task_id else None
  ```

  Do not reintroduce `--parent-node-id`; PR #91 moved the CLI surface to task
  identity.

- [ ] **Step 3: Remove `resource-list --explain`**

  Delete the parser flag unless implementing real explanation output in the same
  commit.

- [ ] **Step 4: Make unsupported workflow mutations explicit**

  For non-dry-run unsupported mutations, return a `WorkflowCommandOutput` with:

  ```text
  dynamic workflow mutation from CLI is unsupported; use WorkerContext.spawn_task(Task(...))
  ```

  Keep dry-run only where tests prove the behavior is useful.

- [ ] **Step 5: Remove ignored dependency slugs with manage deletion**

  Treat `--depends-on-task-slug` as part of the workflow management surface that
  PR 01 deletes from `ergon_cli`. Do not preserve it as a human CLI flag.

Acceptance:

- No audited flag is parsed and ignored.
- `workflow task-tree --parent-task-id` has a focused unit test.

### Correct stale discovery rows

Modify:

- `ergon_cli/ergon_cli/discovery/__init__.py`
- `ergon_cli/ergon_cli/commands/worker.py`
- `ergon_cli/ergon_cli/commands/evaluator.py`

Work:

- [ ] **Step 1: Correct known stale slugs**

  Replace stale worker rows such as:

  ```python
  ("react-worker", ...)
  ("training-stub-worker", ...)
  ```

  with current builtins slugs.

- [ ] **Step 2: Add discovery drift tests**

  Add tests that compare CLI list output to known builtins slugs available in
  process. Keep static rows only as a temporary bridge.

Acceptance:

- `ergon worker list` exposes valid builtins worker slugs.
- Static discovery rows are marked temporary if they remain.

### Extract benchmark template lookup

Modify:

- `ergon_cli/ergon_cli/commands/benchmark.py`

Create:

- `ergon_cli/ergon_cli/commands/benchmark_templates.py`

Work:

- [ ] **Step 1: Create helper module**

  Create `benchmark_templates.py` with:

  ```python
  from pathlib import Path

  SANDBOX_TEMPLATES: dict[str, Path] = {...}

  def sandbox_template_for(slug: str) -> Path:
      return SANDBOX_TEMPLATES[slug]
  ```

- [ ] **Step 2: Use helper from command handler**

  `commands/benchmark.py` should import `sandbox_template_for` and no longer
  contain `Path(__file__).parents[...]`.

- [ ] **Step 3: Add helper tests**

  Test valid template slugs and unknown slug behavior.

Acceptance:

- Benchmark setup behavior remains unchanged.
- Generic command code does not contain brittle repo-relative path arithmetic.

### Remove weak protocol type

Modify:

- `ergon_cli/ergon_cli/commands/benchmark.py`

Work:

- [ ] **Step 1: Delete protocol**

  Remove:

  ```python
  class BuildLog(Protocol):
      def __str__(self) -> str: ...
  ```

- [ ] **Step 2: Keep boundary stringification**

  Type the callback input as `object` unless a real E2B type is available:

  ```python
  def _print_build_log(log: object) -> None:
      print(str(log))
  ```

Acceptance:

- No one-method protocol exists only to model `str(x)`.

## Tests

Add or update:

- `ergon_cli/tests/unit/cli/test_workflow_cli.py`
- `ergon_cli/tests/unit/cli/test_doctor_cli.py`
- `ergon_cli/tests/unit/cli/test_discovery_cli.py`
- `ergon_cli/tests/unit/cli/test_benchmark_setup.py`

Run:

```bash
uv run ruff check ergon_cli/ergon_cli
uv run pytest ergon_cli/tests/unit/cli
```

## PR Ledger

- **Invariant landed:** no known no-op bootstrap, ignored audited flags, or stale
  discovery slugs remain.
- **Bridge code introduced:** `benchmark_templates.py` as a temporary local
  helper before builtins metadata ownership.
- **Old path still intentionally alive:** static discovery rows until PR 05/06.
- **Deletion gate:** PR 06 deletes compatibility command/discovery packages.
- **Tests added or updated:** workflow CLI, doctor parser, discovery, benchmark
  setup.
- **Modules owned by this PR:** `main.py`, `commands/workflow.py`,
  `commands/doctor.py`, `commands/benchmark.py`, `discovery`.

## Out Of Scope

- Moving command modules into final `domains/`.
- Removing all direct DB access from CLI.
- Replacing static discovery with builtins metadata.
- Implementing real dynamic task authoring.

## Depends On

- External base:
  [DeepFlow-research/ergon#91](https://github.com/DeepFlow-research/ergon/pull/91)
  or a later mainline commit containing PR #91.
- No earlier CLI refactor PR. This is the first PR in the CLI stack.
