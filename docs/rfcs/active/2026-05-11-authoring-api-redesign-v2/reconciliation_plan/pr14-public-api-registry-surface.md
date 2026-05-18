# PR 14 Public API And Registry Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the core process-local registry and make the v2 public authoring surface fully object-bound.

**Architecture:** Object snapshots using `_type` discriminators are the canonical runtime serialization path. No core process-local registry remains for runtime, discovery, onboarding, tests, CLI, or admin composition. Replacement discovery uses explicit imports, benchmark dependency declarations, package entrypoints, or local fixture factories. Public core imports guide authors toward `Benchmark`, `Task`, `Worker`, `Sandbox`, `Evaluator`, `Criterion`, and object-bound dynamic task APIs. ReAct `Toolkit` authoring, if public, belongs under a stable builtins/baselines package path rather than `ergon_core`.

**Tech Stack:** Python, pytest, import-boundary tests, CLI tests.

---

## Scope

This PR is a registry deletion and public-surface PR. It should not change
runtime task identity or evaluator dispatch; those belong to PR 12 and PR 13.

## Primary Files

- Modify: `ergon_core/ergon_core/api/__init__.py`
- Delete: `ergon_core/ergon_core/api/registry.py`
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/toolkit.py`
- Modify: `ergon_core/ergon_core/core/application/tasks/management.py`
- Modify: `ergon_core/ergon_core/core/application/workflow/service.py`
- Modify: `ergon_cli/tests/unit/state/test_subtask_lifecycle_toolkit.py`
- Modify: `ergon_cli/tests/unit/cli/test_workflow_cli.py`
- Delete or replace: `ergon_core/tests/unit/registry/test_core_registry_boundary.py`
- Delete or replace: `ergon_core/tests/unit/registry/test_component_registry.py`
- Delete: `ergon_core/tests/unit/registry/test_component_catalog_model.py`
- Modify: `ergon_builtins/tests/unit/architecture/test_object_bound_benchmarks_no_registry.py`

## Code TODOs / Comments To Remove

When PR 14 lands, registry-related comments should disappear with the registry
rather than moving into PR 16. Expected cleanup targets include:

- `ergon_builtins/AGENTS.md`: remove or rewrite all references to
  `ergon_builtins/registry_core.py`, `WORKERS`, `BENCHMARKS`, `EVALUATORS`,
  and `SANDBOX_MANAGERS` as registry tables.
- `ergon_core/ergon_core/api/worker/context.py`: remove the typing comment
  that says the "real objects" create a cycle through `ergon_core.api.registry`
  once the registry import path is deleted.
- CLI, onboarding, smoke fixture, and REST startup files: remove comments that
  describe registry discovery as a temporary bridge or fallback.
- Builtins benchmark docs and comments: remove references to
  `_legacy_workers.py`, registry-string bridges, and PR 11 deleting registry
  compatibility where those comments are only explaining deleted migration code.
- Registry tests and architecture ledgers: delete comments that allow
  `ComponentCatalog`, `registry.workers`, or `ergon_core.api.registry` as known
  transitional exceptions.

## Locked Decisions

- Delete the process-local core registry entirely.
- Delete the persistent component catalog model/tests.
- Keep `Toolkit` out of core; expose it only through a stable
  builtins/baselines import path if it remains public.
- Treat `SubtaskLifecycleToolkit` as a worker-authoring toolkit, not an
  operator/admin slug-registry surface.

## Tasks

### Task 1: Replace Registry Discovery Consumers

- [ ] Add failing tests showing no production, CLI, onboarding, REST startup, smoke fixture, or test harness path imports `ergon_core.api.registry`.
- [ ] Replace CLI/onboarding discovery with explicit benchmark imports, benchmark dependency declarations, package entrypoints, or fixture-local factories.
- [ ] Add a test proving persisted task execution uses `_type` rehydration rather than registry worker lookup.
- [ ] Run:

```bash
cd /Users/charliemasters/.config/superpowers/worktrees/ergon/codex-v2-pr-11-deletion-final-schema
uv run pytest ergon_core/tests/unit/runtime/test_import_boundaries.py ergon_builtins/tests/unit/architecture/test_object_bound_benchmarks_no_registry.py -q
```

Expected before implementation: failure while any registry import remains.

### Task 2: Stabilize Builtins Toolkit Import

- [ ] Expose `Toolkit` through a stable builtins/baselines package path if `ReActWorker(toolkit=...)` remains the intended authoring pattern.
- [ ] Do not export `Toolkit` from `ergon_core.api`; core should not depend on or present builtins ReAct composition as a core primitive.
- [ ] Create or document the builtins import path and use it consistently.
- [ ] Update builtins and examples to import from the stable path.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_import_boundaries.py ergon_builtins/tests/unit/architecture/test_object_bound_benchmarks_no_registry.py -q
```

Expected after implementation: toolkit imports are stable under builtins/baselines, core remains free of toolkit exports, and object-bound benchmarks do not need registry lookup.

### Task 3: Remove Registry Lookup From Dynamic Subtask Creation

- [ ] Update `TaskManagementService.spawn_dynamic_task()` and worker-facing dynamic APIs so object-bound `Task` objects are the only worker-authored creation path.
- [ ] Delete slug/registry dynamic task creation paths instead of moving them to an admin method.
- [ ] Add tests proving `WorkerContext.spawn_task(Task(...))` succeeds with no registry registration.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_spawn_dynamic_task.py ergon_core/tests/unit/runtime/test_worker_context_containment.py -q
```

Expected after implementation: worker-authored dynamic subtasks do not consult the registry.

### Task 4: Make `SubtaskLifecycleToolkit` Worker-Authoring Only

- [ ] Delete or replace `SubtaskLifecycleToolkit` methods that accept worker slugs or registry worker names.
- [ ] Ensure `SubtaskLifecycleToolkit` exposes object-bound worker-facing methods only.
- [ ] Update CLI/toolkit tests so they construct concrete `Task` objects rather than selecting workers by slug.
- [ ] Run:

```bash
uv run pytest ergon_cli/tests/unit/state/test_subtask_lifecycle_toolkit.py ergon_cli/tests/unit/cli/test_workflow_cli.py -q
```

Expected after implementation: `SubtaskLifecycleToolkit` is a worker-authoring object-bound toolkit, not an admin/registry escape hatch.

### Task 5: Delete Persistent Component Catalog

- [ ] Confirm source references to `ergon_core/ergon_core/core/persistence/components/models.py`.
- [ ] Delete the persistent component catalog model and its tests.
- [ ] Remove public exports such as `ComponentCatalog` that present the catalog as part of the authoring/runtime surface.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_import_boundaries.py -q
```

Expected after implementation: persistent component catalog code is gone.

### Task 6: Update Public API Docs And Guards

- [ ] Update RFC implementation docs so they say builtins static registries and the core process-local registry are deleted.
- [ ] Remove stale `AGENTS.md` references to deleted `registry_core.py`.
- [ ] Update public `__all__` exports to remove registry and component catalog surfaces.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_import_boundaries.py ergon_builtins/tests/unit/architecture/test_object_bound_benchmarks_no_registry.py -q
```

Expected after implementation: public import surface and guardrails agree.

## Acceptance Criteria

- `ergon_core.api.registry` is deleted.
- Runtime, CLI, onboarding, REST startup, smoke fixtures, and test harnesses do not use registry lookup.
- Worker-authored dynamic tasks use object-bound `Task` inputs.
- `Toolkit` has a stable builtins/baselines import path and is not exported from core.
- Persistent component catalog is deleted.

## Do Not Include

- Schema identity work.
- Evaluator fallback deletion.
- Dashboard event parser rewrites.
