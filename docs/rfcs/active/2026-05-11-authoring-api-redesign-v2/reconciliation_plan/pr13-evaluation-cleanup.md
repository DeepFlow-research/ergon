# PR 13 Evaluation Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the remaining evaluator v1 dispatch path and make object-bound `Task.evaluators` the only runtime evaluator source.

**Architecture:** Evaluation fanout starts from the run-tier task snapshot, counts inline evaluator objects, and sends id-only `TaskEvaluateRequest` payloads. The receiver reloads the task snapshot and executes `task.evaluators[evaluator_index]`. Definition evaluator rows may remain only as persistence/read-model metadata and FK targets, not as runtime dispatch sources.

**Tech Stack:** Python, Pydantic, SQLModel, Inngest, pytest.

---

## Scope

This PR should follow PR 12 so task identity vocabulary is stable. It should
keep normalized evaluator persistence rows for `RunTaskEvaluation`
FK/read-model/query ergonomics. It deletes runtime dispatch duplication without
trying to collapse evaluator metadata into `task_json`.

## Primary Files

- Modify: `ergon_core/ergon_core/api/benchmark/task.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/execute_task.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py`
- Modify: `ergon_core/ergon_core/core/application/evaluation/service.py`
- Modify: `ergon_core/ergon_core/core/application/evaluation/models.py`
- Modify: `ergon_core/ergon_core/core/persistence/experiment_definition_writer.py`
- Modify: `ergon_core/tests/unit/runtime/test_execute_task_evaluator_fanout.py`
- Modify: `ergon_core/tests/unit/runtime/test_dynamic_task_evaluation_mapping.py`
- Modify: `ergon_core/tests/unit/runtime/test_rubric_evaluation_service.py`
- Modify: `ergon_core/tests/unit/core/application/jobs/test_execute_task_object_bound_fanout.py`
- Modify: `ergon_core/tests/unit/runtime/test_evaluation_context_schemas.py`

## Code TODOs / Comments To Remove

When PR 13 lands, delete the comments and TODOs that only existed to mark the
temporary evaluator bridge. Expected cleanup targets include:

- `ergon_core/ergon_core/core/application/jobs/models.py`: remove the
  `TaskEvaluateRequest` docstring sentence that says the binding-key fallback
  remains only until PR 11.
- `ergon_core/ergon_core/core/application/jobs/execute_task.py`: remove the
  `_fan_out_evaluators()` legacy binding-key fallback docstring and the
  `TODO(PR 11)` comment above the fallback branch when the branch is deleted.
- `ergon_core/ergon_core/core/application/evaluation/service.py`: remove
  comments that refer to `evaluate_legacy`, v1 executor-based signatures, or
  PR 11 deleting those methods after the v1 dispatch path is gone.
- `ergon_builtins/ergon_builtins/evaluators/criteria/code_check.py` and any
  remaining evaluator files: remove comments that describe deleted
  `CriterionExecutor`, Inngest criterion executor, or bridge wiring.
- `ergon_core/ergon_core/api/rubric/evaluator.py` and benchmark rubric files:
  resolve TODOs about unused runtime dependency validation if this PR proves
  those hooks are obsolete; otherwise leave a precise non-transitional comment
  explaining the live public contract.

## Tasks

### Task 1: Prove Binding Fallback Is Unsupported

- [ ] Add a failing test that constructs a task with `evaluator_binding_keys` and no inline `evaluators`.
- [ ] Assert `persist_benchmark()` rejects that task with a clear object-bound evaluator error, or assert model construction no longer accepts the field after deletion.
- [ ] Add a runtime fanout test proving `execute_task` does not emit evaluator jobs when a task has no inline evaluators.
- [ ] Run:

```bash
cd /Users/charliemasters/.config/superpowers/worktrees/ergon/codex-v2-pr-11-deletion-final-schema
uv run pytest ergon_core/tests/unit/runtime/test_execute_task_evaluator_fanout.py ergon_core/tests/unit/core/application/jobs/test_execute_task_object_bound_fanout.py -q
```

Expected before implementation: failure on fallback behavior or accepted legacy field.

### Task 2: Delete `Task.evaluator_binding_keys`

- [ ] Remove `evaluator_binding_keys` from `Task`.
- [ ] Remove serialization/deserialization compatibility for that field.
- [ ] Replace any tests or fixtures that used binding keys with inline evaluator objects.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_definition_task_payload_typing.py ergon_core/tests/unit/runtime/test_run_graph_task_snapshot.py -q
```

Expected after implementation: task snapshots round-trip through inline evaluator objects only.

### Task 3: Remove Runtime Fallback Fanout

- [ ] Delete the fallback branch in `execute_task._fan_out_evaluators()` that derives evaluator count from binding keys or definition rows.
- [ ] Keep fanout behavior simple: `for evaluator_index in range(len(task.evaluators))`.
- [ ] Ensure zero inline evaluators means zero evaluator jobs and valid task completion.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_execute_task_evaluator_fanout.py ergon_core/tests/unit/runtime/test_evaluation_score_aggregation.py -q
```

Expected after implementation: fanout count is tied only to `task.evaluators`.

### Task 4: Delete V1 Dispatch DTOs And Service Method

- [ ] Delete `EvaluationService.prepare_dispatch()` after source search confirms no production path calls it.
- [ ] Delete stale internal DTOs from `ergon_core/ergon_core/core/application/evaluation/models.py`: `PreparedEvaluation`, `EvaluationDispatch`, internal `TaskEvaluationContext`, and internal `CriterionContext`.
- [ ] Replace test coverage with direct coverage of `TaskEvaluateRequest` and `EvaluationService.evaluate()`.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_rubric_evaluation_service.py ergon_core/tests/unit/runtime/test_evaluation_context_schemas.py -q
```

Expected after implementation: evaluation service tests cover execution, not dispatch preparation.

### Task 5: Tighten Dynamic Evaluation Mapping

- [ ] Add a test where a dynamic task has two inline evaluators and the second evaluator persists to the correct `definition_evaluator_id` or documented dynamic fallback id.
- [ ] Ensure `evaluate_task_run` maps `evaluator_index` through the run-tier task snapshot and definition evaluator metadata without consulting deleted dispatch DTOs.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_dynamic_task_evaluation_mapping.py -q
```

Expected after implementation: dynamic task evaluator mapping is deterministic.

### Task 6: Clean Stale Comments And Guards

- [ ] Remove comments mentioning deleted `CriterionExecutor`, `inngest_executor`, or legacy evaluator bridge wiring.
- [ ] Add an architecture test or import-boundary assertion preventing runtime jobs from importing deleted evaluation dispatch modules.
- [ ] Run:

```bash
uv run pytest ergon_core/tests/unit/runtime/test_import_boundaries.py ergon_core/tests/unit/architecture/test_runtime_read_boundaries.py -q
```

Expected after implementation: no runtime path can revive v1 evaluator dispatch.

## Acceptance Criteria

- `Task.evaluator_binding_keys` is gone.
- Runtime evaluator fanout depends only on inline `Task.evaluators`.
- `evaluate_task_run` executes the evaluator from the run-tier task snapshot.
- V1 dispatch DTOs and tests are deleted or renamed as non-runtime read-model helpers.
- Existing rubric/evaluation summary tests pass.

## Do Not Include

- Reworking rubric scoring semantics.
- Removing normalized evaluator definition rows.
- Dashboard UI changes except generated/read-model updates caused by deleted fields.
