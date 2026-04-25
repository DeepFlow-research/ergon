# Slopcop Ignore Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace avoidable `slopcop`, `noqa`, and `type: ignore` suppressions with real fixes, starting with the currently failing slopcop gate.

**Architecture:** Treat suppressions as lint debt, not as the fix. First make `uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra` pass without adding new ignores, then remove broad clusters of existing suppressions by introducing narrow project types, moving imports, and replacing dataclasses with project-standard value models. Keep any remaining ignores only where the code is intentionally adapting to untyped third-party APIs or tool limitations, and require an inline reason.

**Tech Stack:** Python 3.13, uv workspace, slopcop, ruff, ty, pytest.

---

## Current Inventory

- No literal `SlotCop`, `slotcop`, or `slot_cop` symbols were found in `ergon`; the tool is `slopcop`.
- `slopcop` is a dev dependency in `pyproject.toml` and CI runs `uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra`.
- The suppression budget currently counts these inline comment suppressions outside docs:
  - `slopcop: ignore`: 239
  - `# noqa`: 0
  - `# type: ignore`: 89
- The earlier broad `rg` inventory found 241 `# slopcop: ignore[...]` suppressions:
  - `ergon_core`: 125
  - `ergon_builtins`: 92
  - `ergon_cli`: 8
  - `ergon_infra`: 2
  - `tests`: 14
  - `scripts`: 0
- At initial inspection, `uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra` failed with 16 warnings across 4 files. On the current dirty branch, it now passes; do not reintroduce suppressions for these items.
  - `ergon_core/ergon_core/api/benchmark.py`: `no-typing-any`
  - `ergon_core/ergon_core/core/api/runs.py`: seven `guarded-function-import` warnings
  - `ergon_core/ergon_core/test_support/smoke_fixtures/sandbox.py`: `no-future-annotations`, `no-dataclass`, `no-str-empty-default`
  - `ergon_core/ergon_core/test_support/smoke_fixtures/smoke_base/subworker.py`: `no-dataclass`

## Fix Policy

- Do not add new `slopcop: ignore[...]` unless the violation is a stable public API boundary, an untyped third-party API boundary, or a known slopcop false positive.
- Every remaining `slopcop: ignore[...]` must include a short reason after the rule name.
- Prefer moving imports to module scope over adding `# reason:` comments for `guarded-function-import`.
- Prefer narrow aliases or Pydantic models over `Any` only when they make the code more accurate. Do not replace `Any` with `object` just to satisfy the linter; if callers intentionally pass arbitrary JSON or framework payloads, keep `Any` and document the boundary.
- Prefer Pydantic `BaseModel` with `model_config = {"frozen": True}` over dataclasses.
- For `noqa` and `type: ignore`, remove first and run the owning checker before deciding whether to keep it.

---

### Task 1: Make The Current Slopcop Gate Pass

**Files:**
- Modify: `ergon_core/ergon_core/api/benchmark.py`
- Modify: `ergon_core/ergon_core/core/api/runs.py`
- Modify: `ergon_core/ergon_core/test_support/smoke_fixtures/sandbox.py`
- Modify: `ergon_core/ergon_core/test_support/smoke_fixtures/smoke_base/subworker.py`
- Test: `tests/unit/state/test_benchmark_contract.py`
- Test: `tests/unit/smoke_base/test_leaf_sends_completion_message.py`
- Test: `tests/unit/test_app_mounts_harness_conditionally.py`

- [ ] **Step 1: Establish the failing baseline**

Run:

```bash
uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra
```

Expected: 16 warnings across the 4 files listed above.

- [ ] **Step 2: Keep `Benchmark.parse_task_payload` honest**

In `ergon_core/ergon_core/api/benchmark.py`, do not replace `Any` with `object`. This method accepts arbitrary persisted JSON or a Pydantic model and then validates through `task_payload_model`; `Any` is the accurate public boundary type here.

Add a justified slopcop suppression to the signature:

```python
def parse_task_payload(  # slopcop: ignore[no-typing-any] -- arbitrary persisted JSON validated below
    cls,
    payload: BaseModel | Mapping[str, Any] | None,
) -> BaseModel:
```

This is an intentional boundary annotation, not a cleanup-by-renaming. Keep the existing `isinstance(payload, BaseModel)` branch before `model_validate`.

- [ ] **Step 3: Move `RunReadService` import to module scope**

In `ergon_core/ergon_core/core/api/runs.py`, add this top-level import with the other project imports:

```python
from ergon_core.core.runtime.services.run_read_service import RunReadService
```

Then delete the seven function-scope imports of `RunReadService` in `build_run_snapshot`, `get_mutations`, `get_generations`, `get_resource_content`, `get_training_curves`, `get_training_sessions`, and `get_training_metrics`.

- [ ] **Step 4: Re-check smoke sandbox dataclasses before changing them**

On the current branch, slopcop passes with these dataclasses and `SubworkerResult` has an explicit comment explaining why positional dataclass construction is more ergonomic than Pydantic for test fixtures. Do not replace these dataclasses for the sake of the linter. Only revisit this step if slopcop starts failing here again or if a concrete behavior/type-safety improvement is identified.

If slopcop fails again, inspect `ergon_core/ergon_core/test_support/smoke_fixtures/sandbox.py`. Avoid this mechanical replacement unless it genuinely improves the code:

In `ergon_core/ergon_core/test_support/smoke_fixtures/sandbox.py`, remove:

```python
from __future__ import annotations
from dataclasses import dataclass
```

Add:

```python
from pydantic import BaseModel
```

Replace `_CommandResult` and `_EntryInfo` with frozen Pydantic models:

```python
class _CommandResult(BaseModel):
    model_config = {"frozen": True}

    stdout: str = Field(default="")
    stderr: str = Field(default="")
    exit_code: int = 0


class _EntryInfo(BaseModel):
    model_config = {"frozen": True}

    name: str
```

If slopcop still flags the empty string defaults, make `stdout` and `stderr` required and update every `_CommandResult()` call in the file to pass `stdout=""` and `stderr=""` explicitly.

- [ ] **Step 5: Replace `SubworkerResult` dataclass**

In `ergon_core/ergon_core/test_support/smoke_fixtures/smoke_base/subworker.py`, replace the dataclass import and decorator with Pydantic:

```python
from pydantic import BaseModel
```

```python
class SubworkerResult(BaseModel):
    model_config = {"frozen": True}

    file_path: str
    probe_stdout: str
    probe_exit_code: int
```

Check callers. If any tests construct it positionally, update those test fixtures to keyword construction.

- [ ] **Step 6: Verify Task 1**

Run:

```bash
uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra
uv run ruff check ergon_core/ergon_core/api/benchmark.py ergon_core/ergon_core/core/api/runs.py ergon_core/ergon_core/test_support/smoke_fixtures/sandbox.py ergon_core/ergon_core/test_support/smoke_fixtures/smoke_base/subworker.py
uv run ty check ergon_core/ergon_core
uv run pytest tests/unit/state/test_benchmark_contract.py tests/unit/smoke_base/test_leaf_sends_completion_message.py tests/unit/test_app_mounts_harness_conditionally.py -q
```

Expected: slopcop passes; ruff passes; ty has no new errors in touched files; tests pass.

---

### Task 2: Audit `no-typing-any` Suppressions For Real Type Improvements

**Files:**
- Modify: `ergon_core/ergon_core/api/benchmark.py`
- Modify: `ergon_core/ergon_core/test_support/smoke_fixtures/smoke_base/criterion_base.py`
- Modify: `ergon_core/ergon_core/test_support/smoke_fixtures/criteria/smoke_rubrics.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/benchmark.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py`
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`
- Test: focused unit/integration tests that cover each changed benchmark or worker.

- [ ] **Step 1: Classify each `Any` before editing**

For every `slopcop: ignore[no-typing-any]`, classify it into one of three buckets:

- Keep: arbitrary framework payloads, persisted JSON before validation, plugin/tool interfaces, or third-party SDK surfaces.
- Replace: places where the code already assumes a concrete structure, such as dictionaries with fixed keys or homogeneous lists.
- Centralize: repeated unavoidable framework types that can live behind one project alias.

Do not perform substitutions like `Any` -> `object` unless all downstream operations work with `object` without casts and the new type communicates the domain better.

- [ ] **Step 2: Type smoke probe payloads**

In `criterion_base.py`, introduce a local Pydantic model:

```python
class ProbeResult(BaseModel):
    exit_code: int | None = None
    stdout: str = ""
```

Then replace `dict[UUID, dict[str, Any]]` with `dict[UUID, ProbeResult]` throughout that file and update call sites to use attributes instead of dictionary indexing.

- [ ] **Step 3: Type HuggingFace research-rubrics rows**

In `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/benchmark.py`, add:

```python
class ResearchRubricsRow(TypedDict, total=False):
    sample_id: str
    domain: str
    ablated_prompt: str
    rubrics: list[RubricRow]
    removed_elements: list[str] | None
    ablation_type: str | None


class RubricRow(TypedDict):
    criterion: str
    axis: str
    weight: float
```

Change `_payload_from_row(row: Mapping[str, Any])` to `_payload_from_row(row: ResearchRubricsRow)`.

- [ ] **Step 4: Centralize unavoidable framework `Any`**

For PydanticAI message parts in `react_worker.py`, introduce project-local aliases such as:

```python
type ModelMessagePart = object
type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
```

Replace `list[Any]`, `type[Any]`, and JSON-safe return annotations where the implementation only inspects attributes or recursively serializes JSON-like values.

- [ ] **Step 5: Verify Task 2**

Run:

```bash
uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra
uv run ty check ergon_core/ergon_core ergon_builtins
uv run pytest tests/unit/state/test_research_rubrics_benchmark.py tests/integration/swebench_verified/test_criterion.py tests/unit/state/test_research_rubrics_workers.py -q
```

Expected: fewer `slopcop: ignore[no-typing-any]` comments, no new ty failures, tests pass.

---

### Task 3: Audit `noqa` Suppressions

**Files:**
- Modify as needed across `ergon_core`, `ergon_builtins`, `ergon_cli`, `ergon_infra`, `tests`, and `scripts`.

- [ ] **Step 1: List active `noqa` usage**

Run:

```bash
rg -n '#\s*noqa' ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
```

- [ ] **Step 2: Remove stale import-order/import-location suppressions first**

For each `# noqa: E402` or `# noqa: PLC0415`, try moving the import to module scope. Keep a function-scope import only if it prevents a real circular import, avoids an optional dependency import on cold paths, or is required for fixture registration order. In that case add a `# reason:` comment immediately above the import.

- [ ] **Step 3: Re-run ruff**

Run:

```bash
uv run ruff check ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
```

Expected: no stale `noqa` comments; any surviving suppressions are justified by runtime behavior.

---

### Task 4: Audit `type: ignore` Suppressions

**Files:**
- Modify as needed across `ergon_core`, `ergon_builtins`, `ergon_cli`, `ergon_infra`, `tests`, and `scripts`.

- [ ] **Step 1: List active type ignores**

Run:

```bash
rg -n '#\s*type:\s*ignore' ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
```

- [ ] **Step 2: Prefer typed fakes over ignored test calls**

For smoke tests that call private methods with `_FakeNode` and `# type: ignore[arg-type]`, replace `_FakeNode` with a tiny builder that returns a real `RunGraphNode` or define a `Protocol` accepted by the private method. Do not keep the ignore if the method only needs `id`, `task_slug`, and `status`.

- [ ] **Step 3: Prefer local protocols for sandbox mocks**

For sandbox manager tests using `# type: ignore[attr-defined]`, expose a narrow protocol or public test helper for `_install_dependencies` calls instead of ignoring private attribute access.

- [ ] **Step 4: Re-run ty**

Run:

```bash
uv run ty check ergon_core/ergon_core ergon_builtins ergon_cli ergon_infra
```

Expected: no new type errors; a smaller, justified set of `type: ignore` comments remains.

---

### Task 5: Add A Suppression Budget Check

**Files:**
- Create: `scripts/check_suppression_budget.py`
- Modify: `.github/workflows/ci-fast.yml`

- [ ] **Step 1: Create the budget checker**

Add a script that counts `slopcop: ignore`, `# noqa`, and `# type: ignore` in code paths, excludes `docs/**`, and fails if counts increase beyond a checked-in baseline.

- [ ] **Step 2: Wire CI**

Add this after slopcop in `.github/workflows/ci-fast.yml`:

```yaml
- name: Suppression budget
  run: uv run python scripts/check_suppression_budget.py
```

- [ ] **Step 3: Verify the full backend gate**

Run:

```bash
uv run ruff check ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
uv run ruff format --check ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
uv run ty check ergon_core/ergon_core ergon_builtins ergon_cli ergon_infra
uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra
uv run python scripts/check_suppression_budget.py
```

Expected: all commands pass, and future agents cannot quietly add suppressions without changing the baseline.
