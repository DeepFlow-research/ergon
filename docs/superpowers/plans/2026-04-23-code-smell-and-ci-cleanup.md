# Code Smell and CI Cleanup Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all identified code smells (lazy imports, sentinel value, slop suppression comments) and confirm every CI gate — ruff lint/format, ty, slopcop, xenon, frontend ESLint/TypeScript, and unit tests — is green.

**Architecture:** Each change is a surgical edit to a single file. No new abstractions. Lazy imports move to module top-level; the UUID sentinel is replaced with `UUID | None`; noqa comments that are no longer needed are deleted. Part 2 runs the full CI suite locally and fixes any remaining failures.

**Tech Stack:** Python 3.13, uv workspace (ergon_core / ergon_builtins / ergon_cli / ergon_infra), ruff, ty, slopcop, xenon, pnpm / ESLint / TypeScript.

---

## Part 1 — Code Smell Removal

### Lazy-import policy reminder (from CLAUDE.md)

The only acceptable reason to defer an import to call-site scope is a genuine
circular import that cannot be resolved by restructuring modules.  "Heavy deps",
"startup cost", "tests can monkeypatch" are **not** acceptable.  The package
extras (`ergon-builtins[local-models]`, `ergon-builtins[data]`) are the isolation
mechanism — not lazy imports.

---

### Task 1: `transformers_backend.py` — promote lazy imports to top-level

**Files:**
- Modify: `ergon_builtins/ergon_builtins/models/transformers_backend.py`

Context: `import torch` and `import outlines` are *already* top-level (lines 14–16).
`from transformers import AutoModelForCausalLM, AutoTokenizer` is deferred inside
`_ensure_loaded` with reason "defer heavy deps" — slop.  A second `import torch`
inside `_compute_logprobs` is deferred with reason "keeps torch out of module load
path for tests that mock the model" — also slop per CLAUDE.md.

- [ ] **Step 1: Add `transformers` import to module top-level**

  In `ergon_builtins/ergon_builtins/models/transformers_backend.py`, after the
  existing `import torch` line (currently line 16), add:

  ```python
  from transformers import AutoModelForCausalLM, AutoTokenizer
  ```

- [ ] **Step 2: Remove both lazy imports from `_ensure_loaded`**

  Delete the two deferred-import lines and their `# reason:` comments inside
  `_ensure_loaded`:

  ```python
  # DELETE these two blocks:
  # reason: defer heavy deps until first use so importing this module does not load torch/transformers.
  import torch

  # reason: (same as torch above)
  from transformers import AutoModelForCausalLM, AutoTokenizer
  ```

- [ ] **Step 3: Remove lazy `import torch` from `_compute_logprobs`**

  Delete this block inside `_compute_logprobs`:

  ```python
  # DELETE:
  # reason: local import keeps torch import out of module load path for tests that mock the model.
  import torch
  ```

- [ ] **Step 4: Run unit tests to verify nothing broke**

  ```bash
  cd /path/to/ergon
  uv run pytest tests/unit -q -k "transformers" --durations=5
  ```

  Expected: all pass (or no tests collected — the model is exercised via integration).

- [ ] **Step 5: Commit**

  ```bash
  git add ergon_builtins/ergon_builtins/models/transformers_backend.py
  git commit -m "fix: promote lazy transformers/torch imports to module top-level"
  ```

---

### Task 2: `gdpeval/loader.py` — promote lazy imports to top-level

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/loader.py`

Context: `pandas` and `huggingface_hub` symbols are imported lazily inside four
functions (`_load_parquet`, two helper functions at lines 78 and 105, and a fourth
at line 127).  All are covered by `ergon-builtins[data]`.

- [ ] **Step 1: Add top-level imports**

  Replace the existing top-level import block (currently `functools`, `json`,
  `pathlib`, `typing`) with:

  ```python
  import functools
  import json
  from pathlib import Path
  from typing import Any

  import pandas as pd
  from huggingface_hub import hf_hub_download, snapshot_download
  ```

- [ ] **Step 2: Remove all lazy import lines in `_load_parquet`**

  Delete:
  ```python
  # Deferred: optional dependency
  import pandas as pd

  # Deferred: optional dependency
  from huggingface_hub import hf_hub_download
  ```

- [ ] **Step 3: Remove all remaining lazy `hf_hub_download` / `snapshot_download` lines**

  Search for and delete every `from huggingface_hub import ...` inside function
  bodies (lines 78, 105, 127).  The symbol is now available from the top-level import.

- [ ] **Step 4: Run unit tests**

  ```bash
  uv run pytest tests/unit -q -k "gdpeval" --durations=5
  ```

  Expected: pass (or no tests collected).

- [ ] **Step 5: Commit**

  ```bash
  git add ergon_builtins/ergon_builtins/benchmarks/gdpeval/loader.py
  git commit -m "fix: promote lazy pandas/huggingface_hub imports in gdpeval loader"
  ```

---

### Task 3: Benchmark files — promote lazy `datasets` / `huggingface_hub` imports

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/benchmark.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/benchmark.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/minif2f/benchmark.py`

All three are in `ergon-builtins[data]` territory.

- [ ] **Step 1: `swebench_verified/benchmark.py` — add top-level import, remove lazy**

  Add to the top-level import block:
  ```python
  from datasets import load_dataset
  ```

  Delete from inside the method body at line 79:
  ```python
  from datasets import load_dataset
  ```

- [ ] **Step 2: `researchrubrics/benchmark.py` — add top-level imports, remove lazy**

  Add to the top-level import block:
  ```python
  from datasets import load_dataset
  from huggingface_hub import HfApi
  ```

  Delete from inside the method body at lines 97–100:
  ```python
  from datasets import load_dataset
  from huggingface_hub import HfApi
  ```

- [ ] **Step 3: `minif2f/benchmark.py` — add top-level import, remove lazy**

  Add to the top-level import block:
  ```python
  from huggingface_hub import hf_hub_download
  ```

  Delete from inside the method body at line 90:
  ```python
  from huggingface_hub import hf_hub_download
  ```

- [ ] **Step 4: Run unit tests**

  ```bash
  uv run pytest tests/unit -q -k "swebench or researchrubrics or minif2f" --durations=5
  ```

  Expected: pass (or no tests collected).

- [ ] **Step 5: Commit**

  ```bash
  git add ergon_builtins/ergon_builtins/benchmarks/swebench_verified/benchmark.py \
          ergon_builtins/ergon_builtins/benchmarks/researchrubrics/benchmark.py \
          ergon_builtins/ergon_builtins/benchmarks/minif2f/benchmark.py
  git commit -m "fix: promote lazy datasets/huggingface_hub imports in benchmark files"
  ```

---

### Task 4: `ergon_cli/main.py` — promote lazy CLI handler imports

**Files:**
- Modify: `ergon_cli/ergon_cli/main.py`

Context: Eight CLI command handlers are imported lazily inside the `main()` dispatch
block with reason "CLI startup cost" — not an acceptable reason per CLAUDE.md.

- [ ] **Step 1: Add all handler imports to module top-level**

  After the existing top-level imports in `main.py`, add:

  ```python
  from ergon_cli.commands.benchmark import handle_benchmark
  from ergon_cli.commands.doctor import handle_doctor
  from ergon_cli.commands.eval import handle_eval
  from ergon_cli.commands.evaluator import handle_evaluator
  from ergon_cli.commands.onboard import handle_onboard
  from ergon_cli.commands.run import handle_run
  from ergon_cli.commands.train import handle_train
  from ergon_cli.commands.worker import handle_worker
  ```

- [ ] **Step 2: Replace each lazy-import dispatch block with a direct call**

  Each block like:
  ```python
  elif args.command == "benchmark":
      # Deferred: CLI startup cost
      from ergon_cli.commands.benchmark import handle_benchmark
      return handle_benchmark(args)
  ```

  Becomes:
  ```python
  elif args.command == "benchmark":
      return handle_benchmark(args)
  ```

  Apply to all eight command branches.

- [ ] **Step 3: Verify the CLI still works**

  ```bash
  uv run ergon --help
  uv run ergon benchmark --help
  ```

  Expected: help text printed, exit 0.

- [ ] **Step 4: Run unit tests**

  ```bash
  uv run pytest tests/unit/cli -q --durations=5
  ```

  Expected: all pass.

- [ ] **Step 5: Commit**

  ```bash
  git add ergon_cli/ergon_cli/main.py
  git commit -m "fix: promote lazy CLI handler imports to module top-level"
  ```

---

### Task 5: `app.py:70` — fix env-var-conditional import

**Files:**
- Modify: `ergon_core/ergon_core/core/api/app.py`

Context: `app.py:70` defers `from ergon_core.core.api.test_harness import router`
inside an `if os.environ.get("ENABLE_TEST_HARNESS") == "1":` guard with
`# noqa: PLC0415`.  This is not a circular dependency — it is conditional
behaviour.  The import itself is safe at module level; only the *mounting* should
be conditional.

Note: `app.py:42` (`from ergon_builtins.registry import SANDBOX_MANAGERS`) is a
genuine circular import (ergon_builtins → ergon_core, not the reverse) and must
**stay** deferred with its existing `# reason:` comment and `# noqa: PLC0415`.
Do not touch line 42.

- [ ] **Step 1: Move the test harness import to module top-level**

  Add to the top-level import block in `app.py`:

  ```python
  from ergon_core.core.api.test_harness import router as _test_harness_router
  ```

- [ ] **Step 2: Remove the lazy import from the conditional block, keep the mount**

  The block currently reads:
  ```python
  if os.environ.get("ENABLE_TEST_HARNESS") == "1":
      from ergon_core.core.api.test_harness import router as _test_harness_router  # noqa: PLC0415
      app.include_router(_test_harness_router)
  ```

  Change it to:
  ```python
  if os.environ.get("ENABLE_TEST_HARNESS") == "1":
      app.include_router(_test_harness_router)
  ```

- [ ] **Step 3: Run the test that guards this behaviour**

  ```bash
  uv run pytest tests/unit/test_app_mounts_harness_conditionally.py -v
  ```

  This test imports `app` after setting/unsetting `ENABLE_TEST_HARNESS` — confirm
  it still passes.  If it fails because it relied on the late import (post-env-set),
  update the test to patch `_test_harness_router` at the top-level name instead.

- [ ] **Step 4: Commit**

  ```bash
  git add ergon_core/ergon_core/core/api/app.py \
          tests/unit/test_app_mounts_harness_conditionally.py
  git commit -m "fix: promote test_harness conditional import to module top-level"
  ```

---

### Task 6: Replace `DYNAMIC_TASK_SENTINEL_ID` sentinel with `UUID | None`

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/events/task_events.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/task_propagation_service.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/task_management_service.py`
- Modify (if needed): any downstream consumer that reads `event.task_id` and checks
  for the zero UUID

Context: `DYNAMIC_TASK_SENTINEL_ID = UUID("00000000-0000-0000-0000-000000000000")` is
used in two call sites:
1. `task_propagation_service.py:84` — `task_id=rn.definition_task_id or DYNAMIC_TASK_SENTINEL_ID`
2. `task_management_service.py:702` — `task_id=DYNAMIC_TASK_SENTINEL_ID` (hardcoded for dynamic dispatch)

The four `TaskReadyEvent`-family classes all have `task_id: UUID`.  Changing to
`UUID | None` requires updating those schemas and any downstream consumers that
compare `task_id` against the zero UUID.

- [ ] **Step 1: Audit downstream consumers before changing anything**

  ```bash
  grep -rn "task_id" ergon_core/ergon_core/core/runtime/ --include="*.py" | \
      grep -v "definition_task_id\|completed_task_id\|#"
  ```

  Read each hit.  Note any code that does `if event.task_id == DYNAMIC_TASK_SENTINEL_ID`
  or equivalent — these need updating to `if event.task_id is None`.

- [ ] **Step 2: Update event schemas in `task_events.py`**

  Change `task_id: UUID` → `task_id: UUID | None` on every event class that uses it
  (`TaskReadyEvent`, `TaskStartedEvent`, `TaskCompletedEvent`, `TaskFailedEvent` — check
  each one).  Remove `DYNAMIC_TASK_SENTINEL_ID` and its import of `UUID` if UUID is
  no longer used standalone (it still will be for other fields, so just remove the
  sentinel constant).

  Example diff for `TaskReadyEvent`:
  ```python
  # Before
  task_id: UUID

  # After
  task_id: UUID | None
  ```

- [ ] **Step 3: Update `task_propagation_service.py`**

  ```python
  # Before
  task_id=rn.definition_task_id or DYNAMIC_TASK_SENTINEL_ID,

  # After
  task_id=rn.definition_task_id,
  ```

  Remove the `from ergon_core.core.runtime.events.task_events import DYNAMIC_TASK_SENTINEL_ID`
  import.

- [ ] **Step 4: Update `task_management_service.py`**

  ```python
  # Before
  task_id=DYNAMIC_TASK_SENTINEL_ID,

  # After
  task_id=None,
  ```

  Remove the `DYNAMIC_TASK_SENTINEL_ID` import.

- [ ] **Step 5: Update any sentinel comparisons found in Step 1**

  For each site that reads `task_id` and compares it to the zero UUID:
  ```python
  # Before
  if event.task_id == DYNAMIC_TASK_SENTINEL_ID:

  # After
  if event.task_id is None:
  ```

- [ ] **Step 6: Run affected unit and state tests**

  ```bash
  uv run pytest tests/unit/state/ tests/unit -q -k "task" --durations=10
  ```

  Expected: all pass.

- [ ] **Step 7: Commit**

  ```bash
  git add ergon_core/ergon_core/core/runtime/events/task_events.py \
          ergon_core/ergon_core/core/runtime/services/task_propagation_service.py \
          ergon_core/ergon_core/core/runtime/services/task_management_service.py
  # Add any other files touched in Step 5
  git commit -m "fix: replace DYNAMIC_TASK_SENTINEL_ID with UUID | None"
  ```

---

## Part 2 — CI Gate Audit and Fixes

Run every check that CI runs (`pnpm run check:fast`) plus unit tests.  Triage each
failure, fix it, and re-run until all gates are green.  The fixes in Part 1 may
introduce new ty errors (e.g. if `UUID | None` is now passed where `UUID` was
expected) — those surface here.

---

### Task 7: Ruff lint (`check:be:lint`)

- [ ] **Step 1: Run ruff check**

  ```bash
  cd /path/to/ergon
  uv run ruff check ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
  ```

  Capture the output.  Common failures after Part 1:
  - `RUF100` (unused `# noqa` directive) — any `# noqa: PLC0415` left on imports
    that are now top-level
  - Anything new introduced by the import moves

- [ ] **Step 2: Auto-fix what ruff can fix**

  ```bash
  uv run ruff check --fix ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
  ```

- [ ] **Step 3: Manually fix remaining errors**

  For each remaining ruff error, make the minimal edit.  The most likely survivors:
  - Stale `# noqa: PLC0415` comments — delete the comment (not the import).
  - Any import ordering issue from the new top-level additions — ruff's `I` rules
    are not selected, so this is unlikely; if they surface check the select config.

- [ ] **Step 4: Re-run to confirm zero errors**

  ```bash
  uv run ruff check ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
  ```

  Expected: no output (exit 0).

- [ ] **Step 5: Commit any fixes**

  ```bash
  git add -p   # stage only lint-fix changes
  git commit -m "fix: ruff lint cleanup after lazy-import promotion"
  ```

---

### Task 8: Ruff format (`check:be:fmt`)

- [ ] **Step 1: Run format check**

  ```bash
  uv run ruff format --check ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
  ```

- [ ] **Step 2: Auto-format if needed**

  ```bash
  uv run ruff format ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
  ```

- [ ] **Step 3: Re-run check to confirm zero diffs**

  ```bash
  uv run ruff format --check ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
  ```

  Expected: exit 0.

- [ ] **Step 4: Commit if any formatting changed**

  ```bash
  git add -p
  git commit -m "fix: ruff format after lazy-import promotion"
  ```

---

### Task 9: Type check — ty (`check:be:type`)

- [ ] **Step 1: Run ty**

  ```bash
  uv run ty check ergon_core ergon_builtins ergon_cli ergon_infra
  ```

  Expected new failures after Part 1:
  - `task_id: UUID | None` passed to a function expecting `UUID` — fix by adding
    a guard (`if task_id is None: ...`) or asserting non-None at the call site.
  - Any cascade from `from transformers import AutoModelForCausalLM, AutoTokenizer`
    at module level — these are already in `allowed-unresolved-imports` in
    `pyproject.toml` so ty ignores them; this should be fine.

- [ ] **Step 2: Fix each error**

  For each `ty` error:
  - **`UUID | None` passed where `UUID` expected** — add `assert task_id is not None`
    or an early return at the relevant call site.  Do not widen the receiving type
    unless the None case is genuinely handled there.
  - **Unresolved attribute after optional-dep import** — check the `ty.overrides`
    section in `pyproject.toml`; the optional-dep modules already have
    `invalid-argument-type = "warn"` and similar rules set to `"warn"`, so these
    should not be errors.  If a new error appears, add it to the appropriate
    existing `[[tool.ty.overrides]]` block.

- [ ] **Step 3: Re-run to confirm zero errors**

  ```bash
  uv run ty check ergon_core ergon_builtins ergon_cli ergon_infra
  ```

  Expected: exit 0.

- [ ] **Step 4: Commit any type fixes**

  ```bash
  git add -p
  git commit -m "fix: ty errors after UUID | None sentinel replacement"
  ```

---

### Task 10: slopcop (`check:be:slopcop`)

- [ ] **Step 1: Run slopcop**

  ```bash
  uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra
  ```

  Expected failures after Part 1:
  - Any `# Deferred:` comments left in files after the lazy imports were removed —
    these become dangling comments, not slopcop violations per se, but ruff may
    flag them.  Delete them.
  - Any noqa comments referencing now-removed lazy imports.

  Unexpected failures (pre-existing, may have been masked):
  - `no-broad-except` on the `BLE001` sites in `subtask_lifecycle_toolkit.py`
    (7 instances) and `bash_sandbox_tool.py` — these currently have
    `# slopcop: ignore[no-broad-except]` or `# noqa: BLE001`; verify the
    annotation is the form slopcop accepts.
  - `global-modified` on `rollouts.py:35` and `openrlhf_http.py:31` — check
    `PLW0603` annotation form.

- [ ] **Step 2: Fix any violations**

  For a slopcop violation with no legitimate justification, fix the underlying code.
  For a violation with a legitimate justification that is missing its annotation,
  add `# slopcop: ignore[<rule>] -- <reason>` on the offending line.

- [ ] **Step 3: Re-run to confirm zero violations**

  ```bash
  uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra
  ```

  Expected: exit 0.

- [ ] **Step 4: Commit if anything changed**

  ```bash
  git add -p
  git commit -m "fix: slopcop violations after lazy-import cleanup"
  ```

---

### Task 11: Cyclomatic complexity — xenon (`check:be:complexity`)

- [ ] **Step 1: Run xenon**

  ```bash
  uv run xenon --max-absolute F --max-modules E --max-average C \
      ergon_core ergon_builtins ergon_cli ergon_infra
  ```

  The import promotions in Part 1 do not change function complexity, so this gate
  should already pass.  If it fails, it is a pre-existing issue unrelated to this
  branch.

- [ ] **Step 2: If failing, identify the offending function**

  ```bash
  uv run radon cc -s ergon_core ergon_builtins ergon_cli ergon_infra | grep -E "^[A-Z] "
  ```

  Any function graded F is a blocker.  Refactor it to bring the score within
  threshold.  (Note: `pyproject.toml` already has `[tool.ruff.lint.per-file-ignores]`
  entries for known complexity debt — xenon thresholds are independent of those.)

- [ ] **Step 3: Re-run to confirm passing**

  ```bash
  uv run xenon --max-absolute F --max-modules E --max-average C \
      ergon_core ergon_builtins ergon_cli ergon_infra
  ```

  Expected: exit 0.

---

### Task 12: Frontend checks (`check:fe`)

- [ ] **Step 1: Install frontend deps**

  ```bash
  pnpm -C ergon-dashboard install --frozen-lockfile
  ```

- [ ] **Step 2: Run ESLint**

  ```bash
  pnpm -C ergon-dashboard run lint
  ```

  Capture output.  These are independent of the Python changes in Part 1.

- [ ] **Step 3: Run TypeScript check**

  ```bash
  pnpm -C ergon-dashboard run typecheck
  ```

- [ ] **Step 4: Fix any failures**

  ESLint failures: follow the rule message; most are auto-fixable with
  `pnpm -C ergon-dashboard run lint --fix`.

  TypeScript errors: address each one; do not add `// @ts-ignore`.

- [ ] **Step 5: Re-run both checks to confirm zero errors**

  ```bash
  pnpm -C ergon-dashboard run lint && pnpm -C ergon-dashboard run typecheck
  ```

  Expected: both exit 0.

- [ ] **Step 6: Commit any frontend fixes**

  ```bash
  git add ergon-dashboard/
  git commit -m "fix: frontend lint/type errors"
  ```

---

### Task 13: Unit tests (`test:be:fast`)

- [ ] **Step 1: Run the full fast unit suite**

  ```bash
  uv run pytest tests/unit -q -n auto --durations=20
  ```

  Expected: all pass.  Pay attention to any test that relied on the lazy-import
  pattern (e.g. tests that set env vars and then imported a module expecting
  deferred behaviour — `test_app_mounts_harness_conditionally.py` is the known
  candidate; it was already addressed in Task 5).

- [ ] **Step 2: Fix any failures**

  For each failing test, read the failure message.  Common causes:
  - Test imported a module at the top and expected a lazy import to not have fired —
    update the test to mock at the top-level name instead of deferring import.
  - `task_id: UUID | None` assertion in an event snapshot test — update the snapshot.

- [ ] **Step 3: Re-run to confirm all pass**

  ```bash
  uv run pytest tests/unit -q -n auto --durations=20
  ```

  Expected: all pass, no failures, no errors.

- [ ] **Step 4: Commit any test fixes**

  ```bash
  git add tests/
  git commit -m "fix: update unit tests after import promotion and sentinel removal"
  ```

---

### Task 14: Full CI gate verification

- [ ] **Step 1: Run the complete fast check**

  ```bash
  pnpm run check:fast
  ```

  This runs: ruff lint → ruff format → ty → slopcop → xenon → ESLint → TypeScript.
  All must exit 0.

- [ ] **Step 2: Run fast unit tests**

  ```bash
  pnpm run test:be:fast
  ```

  Expected: all pass.

- [ ] **Step 3: If anything is still red, fix it before opening the PR**

  Repeat the relevant task from above.  Do not open the PR until `pnpm run check:fast`
  and `pnpm run test:be:fast` are both fully green.
