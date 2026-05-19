# PR 06: Final Domain Folder Migration And Compatibility Deletion

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the CLI domain migration and delete transitional import paths.

**Architecture:** This is the cleanup gate PR. It should mostly move/delete
files and land architecture guards that prevent regression to the old shape.

**Tech Stack:** pytest architecture tests, ruff, import-boundary scans.

---

## Goal

Complete the CLI domain migration and delete transitional compatibility modules.

## Source PRDs

- `../README.md`
- `../02-target-folder-shape.md`

## Scope

## Current State

Earlier PRs introduced domain modules and shared helpers while preserving some
old import paths for review safety.

## Target State For This PR

The final folder shape matches `../02-target-folder-shape.md`; old
compatibility packages are deleted or reduced to documented shims with explicit
deletion gates.

### Move remaining domains into final folder shape

Ensure final source tree matches:

```text
ergon_cli/ergon_cli/
  main.py
  app.py
  shared/
  domains/
    benchmarks/
    doctor/
    eval/
    evaluators/
    experiments/
    ingestion/
    onboarding/
    runs/
    stack/
    training/
    workers/
    workflow/
```

Work:

- [ ] **Step 1: Inventory remaining old imports**

  ```bash
  rg "ergon_cli\\.(commands|discovery|rendering|onboarding)" ergon
  ```

- [ ] **Step 2: Move remaining implementation**

  Move remaining code into the final `domains/` or `shared/` owners.

- [ ] **Step 3: Delete empty packages**

  Delete old packages once all imports are gone.

- [ ] **Step 4: Preserve console behavior**

  Run parser and command tests before and after file moves.

Acceptance:

- Old compatibility packages are deleted or contain only temporary import
  shims with deletion comments.

### Add final architecture tests

Create or extend:

```text
ergon_cli/tests/unit/architecture/
  test_cli_domain_boundaries.py
  test_cli_import_boundaries.py
```

Rules:

- `argparse.Namespace` does not pass below domain `commands.py`.
- Domain services do not import `argparse`.
- CLI domains do not import `ergon_core.core.persistence`.
- `ergon_builtins` production code does not import `ergon_cli`.
- Generic CLI code does not hardcode benchmark-specific metadata.
- Output printing lives at command/rendering boundaries, not service internals.

Work:

- [ ] **Step 1: Add Namespace boundary guard**

  Assert `argparse.Namespace` appears only in parser/commands boundary modules.

- [ ] **Step 2: Add import guards**

  Assert:

  ```text
  ergon_cli domains -> no ergon_core.core.persistence
  ergon_builtins production -> no ergon_cli
  domain services -> no argparse
  ```

- [ ] **Step 3: Add benchmark metadata guard**

  Assert generic CLI code does not hardcode benchmark-specific template paths or
  dependency tables.

- [ ] **Step 4: Add output boundary guard**

  Audit converted services for direct `print(` calls and forbid them where the
  domain has shared output models.

Acceptance:

- Architecture tests fail for the main old smells.

### Remove temporary shims

Work:

- [ ] **Step 1: Delete old shims**

  Remove old modules after architecture tests pass.

- [ ] **Step 2: Update docs references**

  Replace references to old command module paths in RFC/docs where needed.

- [ ] **Step 3: Run final search**

  ```bash
  rg "ergon_cli.commands|ergon_cli.discovery|ergon_cli.rendering" ergon
  ```

  Expected: no production references, or documented compatibility comments only.

Acceptance:

- `rg "ergon_cli.commands" ergon` has no production references unless an
  intentional backward-compatibility shim is still documented.
- `rg "ergon_cli.discovery|ergon_cli.rendering" ergon` has no production
  references after deletion.

## Tests

Run:

```bash
uv run ruff check ergon_cli/ergon_cli ergon_builtins/ergon_builtins ergon_core/ergon_core
uv run pytest ergon_cli/tests/unit
uv run pytest ergon_builtins/tests/unit
uv run pytest ergon_builtins/tests/integration/tools
uv run pytest ergon_core/tests/unit/runtime/test_spawn_dynamic_task.py
```

## PR Ledger

- **Invariant landed:** final CLI domain folder structure is enforced.
- **Bridge code introduced:** none.
- **Old path still intentionally alive:** none unless explicitly documented.
- **Deletion gate:** this PR is the deletion gate.
- **Tests added or updated:** CLI architecture boundaries and import guards.
- **Modules owned by this PR:** all CLI package compatibility/deletion paths.

## Out Of Scope

- New CLI features.
- Further workflow product design.
- Core architecture refactors already covered by core RFCs.

## Depends On

- PR 00
- PR 01
- PR 02
- PR 03
- PR 04
- PR 05
