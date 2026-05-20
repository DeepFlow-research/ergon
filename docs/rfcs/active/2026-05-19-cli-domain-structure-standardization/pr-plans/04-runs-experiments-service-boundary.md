# PR 04: Runs And Experiments Service Boundary

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove direct SQLModel/session ownership from CLI run and experiment
handlers.

**Architecture:** CLI domains own parsing, command models, and rendering.
Core views/runtime services own persisted state access.

**Tech Stack:** Pydantic v2 command/result models, core views/runtime services,
pytest, architecture import guards.

---

## Goal

Remove direct persistence/session ownership from CLI run and experiment command
handlers.

## Source PRDs

- `../README.md`
- `../01-smell-remediation-map.md`
- `../02-target-folder-shape.md`

## Scope

## Base Assumption

This PR must be implemented on top of
[DeepFlow-research/ergon#91](https://github.com/DeepFlow-research/ergon/pull/91)
or later. On that base, `ergon_core.core.application.read_models` is a retired
package. Use `ergon_core.core.views.runs`, `ergon_core.core.views.experiments`,
and narrow `ergon_core.core.application.runtime` APIs instead.

## Current State

`commands/run.py` and `commands/experiment.py` import core persistence models,
sessions, and `ensure_db()` directly. They also parse UUIDs and render output
inside the same functions that perform reads.

## Target State For This PR

Run and experiment command handlers call CLI services backed by core
views/runtime services. Direct persistence imports disappear from these CLI
domains.

## Tasks

### Move runs into a typed CLI domain

Create:

```text
ergon_cli/ergon_cli/domains/runs/
  __init__.py
  parser.py
  commands.py
  models.py
  service.py
```

Modify:

- `ergon_cli/ergon_cli/commands/run.py`

Work:

- [ ] **Step 1: Add run command models**

  ```python
  class ListRunsCommand(BaseModel):
      limit: int = 20
      status: str | None = None
      definition_id: UUID | None = None
      experiment: str | None = None

  class RunStatusCommand(BaseModel):
      run_id: UUID

  class CancelRunCommand(BaseModel):
      run_id: UUID
  ```

- [ ] **Step 2: Add run result models**

  Add display-focused models such as `RunSummaryView` and `RunStatusView` in
  `domains/runs/models.py`.

- [ ] **Step 3: Add run service**

  `domains/runs/service.py` should call `ergon_core.core.views.runs.service`
  for read/display queries and `ergon_core.core.application.runtime.run_records`
  for cancellation/runtime lifecycle operations. If no core service exists for
  a valid CLI query, add the narrow method to `core/views/runs/service.py` or
  `core/application/runtime/run_records.py` instead of importing persistence in
  CLI.

- [ ] **Step 4: Remove direct persistence imports**

  `domains/runs/*` must not import `ergon_core.core.persistence`.

Acceptance:

- Runs command handlers do not import SQLModel sessions or persistence models.
- Invalid UUIDs become CLI errors, not tracebacks.

### Move experiments into a typed CLI domain

Create:

```text
ergon_cli/ergon_cli/domains/experiments/
  __init__.py
  parser.py
  commands.py
  models.py
  service.py
```

Modify:

- `ergon_cli/ergon_cli/commands/experiment.py`

Work:

- [ ] **Step 1: Add experiment command models**

  Add `ListExperimentsCommand`, `ShowExperimentCommand`, `ListTagsCommand`, and
  `ListByTagCommand`.

- [ ] **Step 2: Add experiment result models**

  Use result/view models that match terminal output and JSON rendering needs.

- [ ] **Step 3: Add experiment service**

  `ShowExperimentCommand` should use `definition_id`, matching the PR #91 CLI
  parser and `ExperimentDefinition` identity language. Delegate to
  `ergon_core.core.views.experiments.service.ExperimentReadService`. Add a
  narrow views method only if the CLI need is valid and not already present. Do
  not recreate the retired
  `ergon_core.core.application.read_models` package.

- [ ] **Step 4: Normalize output**

  Replace logging-as-output with `shared.output`.

Acceptance:

- Experiment command handlers do not import persistence models directly.
- Logging is not used as the user-facing output channel.

### Add architecture checks

Add:

- `ergon_cli/tests/unit/architecture/test_cli_persistence_boundaries.py`

Work:

- [ ] **Step 1: Add import-boundary test**

  Scan converted domain files for forbidden imports:

  ```python
  FORBIDDEN = ("ergon_core.core.persistence", "sqlmodel.Session")
  ```

- [ ] **Step 2: Add temporary exemption list**

  If an unconverted domain still violates the rule, list it explicitly with the
  PR that removes the exemption.

Acceptance:

- Boundary tests prevent reintroducing direct persistence imports.

## Tests

Run:

```bash
uv run ruff check ergon_cli/ergon_cli ergon_core/ergon_core
uv run pytest ergon_cli/tests/unit/cli
uv run pytest ergon_cli/tests/unit/architecture/test_cli_persistence_boundaries.py
```

If core services are added, also run their focused tests.

## PR Ledger

- **Invariant landed:** run/experiment CLI domains no longer own direct
  persistence access.
- **Bridge code introduced:** narrow core views/runtime service methods if
  missing.
- **Old path still intentionally alive:** other unconverted domains may still
  have direct imports until later PRs.
- **Deletion gate:** PR 06 removes exemptions and old command modules.
- **Tests added or updated:** run/experiment CLI tests, architecture import
  boundary tests, focused core service tests if needed.
- **Modules owned by this PR:** runs domain, experiments domain, relevant core
  views/runtime services.

## Out Of Scope

- Dashboard/views redesign.
- Deleting legacy experiment/cohort compatibility unless already covered by core
  refactor PRDs.
- Benchmark/onboarding metadata ownership.

## Depends On

- PR 03
