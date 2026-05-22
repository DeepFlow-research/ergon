# PR 16 Core Debt Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove residual dead code, stale comments, duplicate lifecycle paths, and unfinished PR ledgers after the main v2 runtime/public-surface decisions have landed.

**Architecture:** This is intentionally a sweep PR. It should not make new architecture decisions. It deletes code already made unreachable by PRs 11-15, tightens guards, implements cancelled-task sandbox release, and removes all lingering xfails/ledgers so the v2 core is easier to reason about.

**Tech Stack:** Python, pytest, architecture tests, docs.

---

## Scope

This PR should land after PRs 12-15. It should leave no known-violator ledgers,
xfails, or unresolved cleanup exceptions behind.

## Primary Files

- Delete or modify: `ergon_builtins/ergon_builtins/benchmarks/minif2f/_legacy_toolkit.py`
- Delete or modify: `ergon_core/ergon_core/core/application/context/output_extraction.py`
- Modify: `ergon_core/ergon_core/core/application/workflow/service.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/sandbox_cleanup.py`
- Modify: `ergon_core/ergon_core/core/application/tasks/management.py`
- Modify: `ergon_core/tests/unit/runtime/test_workflow_service.py`
- Modify: `ergon_core/tests/unit/runtime/test_failed_task_sandbox_cleanup.py`
- Modify: `ergon_core/tests/unit/runtime/test_sandbox_cleanup.py`
- Modify: `ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py`
- Modify: `ergon_core/tests/unit/architecture/test_repository_companion_files.py`
- Modify: `ergon_builtins/AGENTS.md`
- Modify: stale comments in builtins and core files identified by `dead_code.MD`

## Code TODOs / Comments To Remove

PR 16 is the final cleanup pass. It should not carry forward broad "maybe
later" TODOs created by the v2 migration. Expected cleanup targets include:

- `ergon_core/ergon_core/core/application/context/output_extraction.py`: delete
  the file if it is dead, or replace the file-level TODO with a precise live
  responsibility if it remains as a read-model adapter.
- `ergon_core/ergon_core/core/application/graph/propagation.py`: resolve the
  remaining service/repository-ownership TODO if it still exists after PR 12
  and PR 16's lifecycle consolidation.
- `ergon_core/ergon_core/core/application/jobs/__init__.py`,
  `ergon_core/ergon_core/core/application/evaluation/__init__.py`,
  `ergon_core/ergon_core/core/application/graph/models.py`, and
  `ergon_core/ergon_core/core/application/evaluation/scoring.py`: delete or
  narrow broad module-structure TODOs for domains this PR actually touches;
  leave only specific, non-migration follow-ups if a larger refactor is out of
  scope.
- Sandbox cleanup files and tests: remove comments that promise cancelled-task
  release without implementing it, and remove failed-task duplicate-terminator
  notes once `sandbox_cleanup` is the only owner.
- Architecture tests and ledgers: delete remaining known-violator comments,
  xfail reasons, and `landing_pr="PR 11"` expectations that no longer describe
  the current stack.
- Builtins/core stale comments discovered by the final search for
  `legacy bridge`, `_legacy_workers`, `registry_core`, `CriterionExecutor`,
  `inngest criterion`, `sandbox_manager`, and `evaluate_legacy` should either
  be gone or live only in historical RFC prose, not production code.

## Tasks

### Task 1: Re-Audit Dead-Code Candidates Against Current Head

- [ ] Run source searches for each candidate in `dead_code.MD`.
- [ ] Record only current-head facts in the PR description; do not rely on old audit wording.
- [ ] Use this command set:

```bash
cd /Users/charliemasters/.config/superpowers/worktrees/ergon/codex-v2-pr-11-deletion-final-schema
rg -n "output_extraction|_legacy_toolkit|prepare_dispatch|evaluator_binding_keys|ComponentCatalog|restart_task\\(|abandon_task\\(" ergon_core ergon_builtins ergon_cli
```

Expected before deletion: every deletion target has no runtime references or a clear replacement task in this plan.

### Task 2: Delete MiniF2F Legacy Toolkit If Unused

- [ ] Delete `ergon_builtins/ergon_builtins/benchmarks/minif2f/_legacy_toolkit.py` if it remains unreferenced.
- [ ] Remove stale comments in MiniF2F files pointing at deleted legacy workers.
- [ ] Run:

```bash
uv run pytest ergon_builtins/tests/unit/architecture/test_object_bound_benchmarks_no_registry.py -q
```

Expected after implementation: MiniF2F object-bound benchmark tests pass with no legacy toolkit.

### Task 3: Delete Or Rename Context Output Extraction

- [ ] If `output_extraction.py` is unreferenced, delete it and any tests that only cover the dead path.
- [ ] If still referenced by an external contract, rename it to a read-model adapter and document why it exists.
- [ ] Ensure terminal output persistence still flows through `WorkerOutputRepository.persist()` and `RunTaskExecution.worker_output_json`.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_worker_execute_stream_contract.py ergon_core/tests/unit/runtime/test_persist_outputs_resources.py -q
```

Expected after implementation: worker output tests pass without dead extraction helpers.

### Task 4: Consolidate Workflow Lifecycle Methods

- [ ] Delete `WorkflowService.restart_task()` and `WorkflowService.abandon_task()` after moving remaining callers to `TaskManagementService`.
- [ ] Ensure terminal guards, cascade invalidation, dispatch, and containment checks live in one service.
- [ ] Update CLI dry-run/non-dry-run tests to call the canonical service path.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_workflow_service.py ergon_cli/tests/unit/state/test_workflow_cli_tool.py -q
```

Expected after implementation: restart/abandon semantics are covered once and are not weaker through workflow service.

### Task 5: Make Sandbox Cleanup Single-Owner

- [ ] Remove failed-task sandbox termination from propagation because `sandbox_cleanup` owns terminal sandbox release.
- [ ] Add tests proving a failed task emits exactly one cleanup action and one terminal sandbox event.
- [ ] Implement and test sandbox release for cancelled tasks.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_failed_task_sandbox_cleanup.py ergon_core/tests/unit/runtime/test_sandbox_cleanup.py -q
```

Expected after implementation: failed-task cleanup has one owner and cancelled tasks release sandboxes.

### Task 6: Drain Remaining Ledgers And Xfails

- [ ] Remove the remaining `_KNOWN_VIOLATORS` entry from `ergon_core/tests/unit/architecture/test_repository_companion_files.py` by adding the missing companion file or deleting the stale exception.
- [ ] Un-xfail the walkthrough sandbox acquire/release completion guard and make it pass.
- [ ] Delete any remaining known-violator ledgers instead of moving them to follow-ups.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/architecture/test_repository_companion_files.py ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py -q
```

Expected after implementation: no undocumented ledger exceptions remain.

### Task 7: Clean Stale Docs And Comments

- [ ] Update `ergon_builtins/AGENTS.md` so it no longer points at deleted registry files.
- [ ] Remove comments in builtins/core files that reference deleted bridge modules, deleted criterion executors, or deleted sandbox managers.
- [ ] Run:

```bash
rg -n "legacy bridge|_legacy_workers|registry_core|CriterionExecutor|inngest criterion|sandbox_manager|evaluate_legacy" ergon_core ergon_builtins docs
```

Expected after implementation: matches are either gone or intentionally describe historical RFC context.

### Task 8: Final Verification Sweep

- [ ] Run focused backend suites touched by this PR.
- [ ] Run import-boundary and architecture tests.
- [ ] Run diff checks.
- [ ] Commands:

```bash
uv run pytest ergon_core/tests/unit/runtime ergon_core/tests/unit/architecture ergon_builtins/tests/unit/architecture -q
git diff --check
```

Expected after implementation: all touched suites pass and no whitespace/check errors remain.

## Acceptance Criteria

- Dead files listed in this plan are deleted or explicitly documented as live.
- Duplicate lifecycle paths are collapsed to a single owner.
- Failed-task sandbox cleanup is single-owner.
- Cancelled tasks release sandboxes.
- PR ledgers and xfails are fully drained.
- Stale comments no longer mislead readers about deleted v1 paths.

## Do Not Include

- New schema identity work.
- New evaluator architecture.
- New dashboard contracts.
