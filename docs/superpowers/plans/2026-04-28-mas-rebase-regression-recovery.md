# MAS Rebase Regression Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover changes lost or blurred during the `feature/mas-main-rebase` merge, without undoing intentional main-branch experiment-run work.

**Architecture:** Treat this as a rebase audit and repair plan. Definite regressions get direct test-first fixes; the older object-first `ExperimentRunHandle` / `Experiment.run()` API is intentionally retired in favor of the newer experiment definition and launch services.

**Tech Stack:** Python 3.13, Pydantic, SQLModel, pytest, uv, Ergon core/runtime/API packages.

---

## Audit Summary

The rebase worktree is clean at `feature/mas-main-rebase` with `HEAD` at `ab28db3` (`Merge main into MAS debugger branch`). The broad cleanup survived, but two regressions need action.

### Preserved Work

- Public API thinning survived: removed `ergon_core.api.generation`, `json_types`, `run_resource`, `criterion_runtime`, `dependencies`, and `types`.
- Runtime homes survived: `core/runtime/resources.py`, `core/runtime/dependencies.py`, and `core/runtime/evaluation/protocols.py`.
- Context schema consolidation survived: `ContextPart`, `ContextPartChunk`, and `ContextPartChunkLog` are the core stream/log schemas; old `GenerationTurn` and old `*Payload` context-event classes are gone from core.
- File moves survived: Inngest client/registry under `core/runtime/inngest/`, sandbox under `core/sandbox/`, ResearchRubrics sandbox manager under builtins, OpenRouter budget under `tests/real_llm`, and tracing split into `core/runtime/tracing/`.
- `error_payload.py`, `build_error_json`, `RuntimeErrorPayload`, and `_worker_execute_result_from_exception` remain removed.

### Definite Regression

`_worker_execute_result_from_output()` has reappeared in `ergon_core/ergon_core/core/runtime/inngest/worker_execute.py`, along with `tests/unit/runtime/test_worker_execute_output_failure.py`.

Today's intended state was:

- No private adapter helper for `WorkerOutput -> WorkerExecuteResult`.
- Success result construction inlined at the only callsite.
- No helper-level test importing `_worker_execute_result_from_output`.

### Intentional Retirement

`ExperimentRunHandle` and `Experiment.run()` existed on `safety/mas-before-main-rebase`, but are absent in `feature/mas-main-rebase`.

Current state:

- `ergon_core/ergon_core/api/handles.py` defines only `PersistedExperimentDefinition`.
- `ergon_core/ergon_core/api/__init__.py` exports only `PersistedExperimentDefinition`, not `ExperimentRunHandle`.
- `ergon_core/ergon_core/api/experiment.py` exposes `persist()` but no `run()`.
- Main added experiment launch/read services under `core/runtime/services/experiment_*`, and that newer model is the one we want to keep.

Decision: do **not** restore `ExperimentRunHandle` or `Experiment.run()`. Treat the older object-run API as retired. The fix is to remove stale handle/run wording and add tests that prevent the old single-run handle from returning to `ergon_core.api`.

---

## Files To Touch

### Definite Helper Regression

- Modify: `ergon_core/ergon_core/core/runtime/inngest/worker_execute.py`
- Delete: `tests/unit/runtime/test_worker_execute_output_failure.py`
- Modify or add guard: `tests/unit/runtime/test_import_boundaries.py` or `tests/unit/architecture/test_public_api_boundaries.py`

### Experiment Handle Retirement

- Modify: `ergon_core/ergon_core/api/handles.py` docstring
- Modify/add API boundary test confirming no `ExperimentRunHandle` / no `Experiment.run`
- Update docs that still describe `run()` as part of the object-first authoring API.

---

## Task 1: Lock In The Helper Removal Regression

**Files:**
- Modify: `tests/unit/runtime/test_import_boundaries.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/worker_execute.py`
- Delete: `tests/unit/runtime/test_worker_execute_output_failure.py`

- [ ] **Step 1: Add a failing guard for deleted worker helper adapters**

Add this test to `tests/unit/runtime/test_import_boundaries.py`:

```python
def test_worker_execute_does_not_expose_result_adapter_helpers() -> None:
    import ergon_core.core.runtime.inngest.worker_execute as worker_execute

    assert not hasattr(worker_execute, "_worker_execute_result_from_output")
    assert not hasattr(worker_execute, "_worker_execute_result_from_exception")
```

- [ ] **Step 2: Run the guard and verify it fails before the fix**

Run:

```bash
uv run pytest tests/unit/runtime/test_import_boundaries.py::test_worker_execute_does_not_expose_result_adapter_helpers -q
```

Expected before fix:

```text
FAILED ... assert not hasattr(worker_execute, "_worker_execute_result_from_output")
```

- [ ] **Step 3: Inline the success result construction**

In `ergon_core/ergon_core/core/runtime/inngest/worker_execute.py`, remove:

```python
def _worker_execute_result_from_output(output: WorkerOutput) -> WorkerExecuteResult:
    return WorkerExecuteResult(
        success=output.success,
        final_assistant_message=output.output,
        error=None if output.success else output.output,
    )
```

Then replace:

```python
return _worker_execute_result_from_output(output)
```

with:

```python
return WorkerExecuteResult(
    success=output.success,
    final_assistant_message=output.output,
    error=None if output.success else output.output,
)
```

Also remove the now-unused import:

```python
from ergon_core.api.results import WorkerOutput
```

- [ ] **Step 4: Delete helper-specific test**

Delete:

```text
tests/unit/runtime/test_worker_execute_output_failure.py
```

This test asserts a private helper mapping and should not survive once the helper is gone. The behavior is still covered by `worker_execute_fn` return construction and `WorkerExecuteResult` model validation.

- [ ] **Step 5: Run focused verification**

Run:

```bash
uv run pytest tests/unit/runtime/test_import_boundaries.py tests/unit/runtime/test_failure_error_json.py -q
uv run ruff check ergon_core/ergon_core/core/runtime/inngest/worker_execute.py tests/unit/runtime/test_import_boundaries.py
```

Expected:

```text
passed
All checks passed!
```

---

## Task 2: Lock In The New Experiment Launch Model

**Files:**
- Inspect: `ergon_core/ergon_core/api/experiment.py`
- Inspect: `ergon_core/ergon_core/api/handles.py`
- Inspect: `ergon_core/ergon_core/core/runtime/services/run_service.py`
- Inspect: `ergon_core/ergon_core/core/runtime/services/experiment_launch_service.py`
- Inspect: `ergon_cli/ergon_cli/commands/benchmark.py`

- [ ] **Step 1: Confirm current execution entry points**

Run:

```bash
rg "class ExperimentRunHandle|async def run\\(|create_experiment_run|launch" \
  ergon_core/ergon_core/api \
  ergon_core/ergon_core/core/runtime/services \
  ergon_cli/ergon_cli/commands \
  tests -n
```

Expected current signal:

- `ExperimentRunHandle` appears only as a CLI-local class in `ergon_cli/ergon_cli/commands/benchmark.py`.
- `Experiment` has `persist()` but no `run()`.
- Main-branch experiment services own launch/read behavior.

Step 1 confirms that the newer model is active:

- `ExperimentRecord` stores the experiment campaign/sample selection.
- `ExperimentLaunchService.run_experiment()` expands one `ExperimentRecord` into many `RunRecord`s.
- `ExperimentRunResult` returns `run_ids: list[UUID]`, not a single `run_id`.
- `ergon_core.api.Experiment` remains a workflow-definition composition object with `persist()` only.

- [ ] **Step 2: Write a guard for the retired object-run API**

Add tests to `tests/unit/api/test_public_api_imports.py`:

```python
def test_object_first_experiment_run_api_is_retired() -> None:
    public_api = importlib.import_module("ergon_core.api")

    assert not hasattr(public_api, "ExperimentRunHandle")
    assert not hasattr(public_api.Experiment, "run")
```

- [ ] **Step 3: Clean stale handle wording**

Update `ergon_core/ergon_core/api/handles.py` docstring from:

```python
"""Public lifecycle handle types returned by persist() and run()."""
```

to:

```python
"""Public lifecycle handle types returned by Experiment.persist()."""
```

- [ ] **Step 4: Run focused API verification**

Run:

```bash
uv run pytest tests/unit/api/test_public_api_imports.py -q
```

Expected:

```text
passed
```

---

## Task 3: Add A Rebase Recovery Guard For Historical Regressions

**Files:**
- Modify: `tests/unit/architecture/test_public_api_boundaries.py`
- Modify: `tests/unit/runtime/test_import_boundaries.py`

- [ ] **Step 1: Guard deleted API facade modules by module spec**

Add to `tests/unit/architecture/test_public_api_boundaries.py`:

```python
import importlib.util


def test_removed_api_facade_modules_do_not_exist() -> None:
    removed_modules = (
        "ergon_core.api.generation",
        "ergon_core.api.json_types",
        "ergon_core.api.run_resource",
        "ergon_core.api.criterion_runtime",
        "ergon_core.api.dependencies",
        "ergon_core.api.types",
    )

    for module_name in removed_modules:
        assert importlib.util.find_spec(module_name) is None
```

- [ ] **Step 2: Guard worker private adapter helpers**

Use the helper guard from Task 1.

- [ ] **Step 3: Run architecture guards**

Run:

```bash
uv run pytest tests/unit/architecture/test_public_api_boundaries.py tests/unit/runtime/test_import_boundaries.py -q
```

Expected:

```text
passed
```

---

## Task 4: Final Verification

**Files:**
- All touched files from Tasks 1-3.
- Verify: `tests/integration/smokes/test_smoke_harness.py`
- Verify: `tests/e2e/`

- [ ] **Step 1: Run focused test group**

Run:

```bash
uv run pytest \
  tests/unit/api/test_public_api_imports.py \
  tests/unit/architecture/test_public_api_boundaries.py \
  tests/unit/runtime/test_import_boundaries.py \
  tests/unit/runtime/test_failure_error_json.py \
  -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run targeted lint**

Run:

```bash
uv run ruff check \
  ergon_core/ergon_core/core/runtime/inngest/worker_execute.py \
  ergon_core/ergon_core/api/handles.py \
  ergon_core/ergon_core/api/__init__.py \
  ergon_core/ergon_core/api/experiment.py \
  tests/unit/api/test_public_api_imports.py \
  tests/unit/architecture/test_public_api_boundaries.py \
  tests/unit/runtime/test_import_boundaries.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 3: Run local integration/e2e acceptance for the newer cohort -> experiment -> run model**

Use this as the main system-level confidence metric for the rebase:

> A local checkout can define an experiment through the newer cohort/experiment model, launch runs for selected samples, drive those runs through the runtime, persist graph/evaluation/resource outputs, and pass the e2e smoke path without relying on retired `Experiment.run()` / `ExperimentRunHandle`.

Run the local smoke/e2e set used by this branch:

```bash
uv run pytest tests/integration/smokes/test_smoke_harness.py -q
uv run pytest tests/e2e -q
```

Expected:

```text
passed
```

If the e2e suite requires local services, start the normal local stack first, then rerun the same commands. A failure here is a blocker unless it is a documented environment prerequisite rather than a model/API regression.

- [ ] **Step 4: Check git diff for scope**

Run:

```bash
git diff --stat
git diff --name-status
```

Expected changed files should be limited to:

- `docs/superpowers/plans/2026-04-28-mas-rebase-regression-recovery.md`
- `ergon_core/ergon_core/core/runtime/inngest/worker_execute.py`
- `tests/unit/runtime/test_import_boundaries.py`
- `tests/unit/runtime/test_worker_execute_output_failure.py` deleted
- plus the accept-main guard/docstring files from Task 2.

---

## Non-Goals

- Do not reintroduce `ergon_core.api.generation`, `json_types`, `run_resource`, `criterion_runtime`, `dependencies`, or `types`.
- Do not reintroduce `error_payload.py`, `build_error_json`, or `RuntimeErrorPayload`.
- Do not undo main's experiment-run domain model or revive `ExperimentRunHandle` / `Experiment.run()`.
- Do not edit historical docs/RFCs unless they are actively misleading for the current public API.

## Completion Criteria

- `_worker_execute_result_from_output` and `_worker_execute_result_from_exception` are absent.
- `test_worker_execute_output_failure.py` is deleted or rewritten to avoid private helper imports.
- Public API state around `ExperimentRunHandle` is explicit and tested as intentionally absent.
- Local smoke/e2e tests pass through the newer `cohort -> experiment -> run` model without using the retired object-run API.
- Focused pytest and ruff checks pass.
