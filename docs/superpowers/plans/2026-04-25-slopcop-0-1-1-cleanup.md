# Slopcop 0.1.1 Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra` pass on `slopcop 0.1.1` by fixing the flagged code rather than growing suppressions.

**Architecture:** Treat every `0.1.1` finding as a real review item. Fix `no-async-from-sync` by moving async flow upward to the CLI entrypoint, fix `no-or-empty-coalesce` by distinguishing `None` from valid falsy values, and fix `no-typing-any`/bare `object` by introducing narrow JSON aliases, protocols, or domain models only where they make the code more accurate. Suppress only stable boundaries such as the console-script event-loop bridge or untyped third-party SDK surfaces, and every suppression must include an inline reason.

**Tech Stack:** Python 3.13, uv workspace, Slopcop 0.1.1, Ruff, ty, pytest, Pydantic, SQLModel.

---

## Current State

- `pyproject.toml` now requires `slopcop>=0.1.1`.
- `uv.lock` resolves `slopcop==0.1.1`.
- `uv run slopcop --format json ergon_core ergon_builtins ergon_cli ergon_infra` reports:
  - `no-async-from-sync`: 1 error at `ergon_cli/ergon_cli/main.py`.
  - `no-or-empty-coalesce`: 42 warnings across CLI, runtime, builtins, and smoke fixtures.
  - `no-typing-any`: 121 warnings, including both `Any` and bare `object`.
- The previous smoke-fixture move is complete; live paths are under `ergon_core/ergon_core/test_support/smoke_fixtures`.
- The suppression budget currently fails because the console-script bridge added one `slopcop: ignore`; this is acceptable only if the ignore is correctly placed on the line above and documented as the single event-loop boundary.

## Working Rules

- Do not convert `Any` to `object`; Slopcop 0.1.1 correctly flags both.
- Do not replace `x or ""`, `x or []`, `x or {}`, or `x or 0` mechanically with a different fallback. Decide whether the field can be `None`.
- Preserve meaningful falsy values:
  - Empty string `""` is a valid command output, cohort name, model target, etc.
  - Empty list `[]` and empty dict `{}` are valid persisted JSON values.
  - Numeric `0` and `0.0` are valid return codes and scores.
- Do not manufacture empty strings for missing domain values. If a value is
  optional, keep it optional and let the boundary decide how to represent
  missingness. For trace attributes specifically, `normalize_attributes()` skips
  `None`, so passing `None` is usually better than serializing `""`.
- Prefer direct, local `is None` handling at the use site. A generic helper like
  `_text_or_empty()` hides the question Slopcop is forcing us to answer: is an
  empty string a valid value here, or are we normalizing a missing value from an
  external boundary?
- Add a helper only when it has a domain name that preserves intent, such as
  `_sandbox_stream_text(stream: str | None) -> str` in one sandbox adapter file.
  Do not create generic "or empty" helpers.

- For JSON-shaped data, prefer a recursive alias in a shared local module or the file that owns the boundary:

```python
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
```

---

## Task 1: Finish the CLI Async Boundary Fix

**Files:**
- Modify: `ergon_cli/ergon_cli/main.py`
- Modify: `ergon_cli/ergon_cli/commands/benchmark.py`
- Modify: `ergon_cli/ergon_cli/commands/eval.py`
- Modify: `ergon_core/ergon_core/core/rl/eval_runner.py`
- Test: existing CLI import/type checks

- [ ] **Step 1: Ensure the only sync/async bridge is `main()`**

`ergon_cli/ergon_cli/main.py` should keep `main()` sync for the console script. Slopcop 0.1.1 recognizes this suppression only on the `asyncio.run(...)` call line, so keep the call short enough that Ruff does not move the suppression to a continuation line:

```python
async def _main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "benchmark":
        return await handle_benchmark(args)
    elif args.command == "eval":
        return await handle_eval(args)
    # existing sync handlers remain direct returns


def main(argv: list[str] | None = None) -> int:
    coroutine = _main(argv)
    return asyncio.run(coroutine)  # slopcop: ignore[no-async-from-sync] -- CLI entrypoint
```

- [ ] **Step 2: Keep async handlers async all the way down**

`ergon_cli/ergon_cli/commands/benchmark.py`:

```python
async def handle_benchmark(args: Namespace) -> int:
    if args.bench_action == "list":
        benchmarks = list_benchmarks()
        render_table(["Slug", "Name", "Description"], benchmarks)
        return 0
    elif args.bench_action == "run":
        return await run_benchmark(args)
    elif args.bench_action == "setup":
        return setup_benchmark(args)
    else:
        print("Usage: ergon benchmark {list|run|setup}")
        return 1


async def run_benchmark(args: Namespace) -> int:
    # existing setup/persist code unchanged
    run_handle = await _create_and_dispatch(
        persisted,
        timeout=args.timeout,
        cohort_id=cohort.id,
    )
```

`ergon_cli/ergon_cli/commands/eval.py`:

```python
async def handle_eval(args: Namespace) -> int:
    if args.eval_action == "watch":
        return await _watch(args)
    elif args.eval_action == "checkpoint":
        return await _checkpoint(args)
    else:
        print("Usage: ergon eval {watch|checkpoint}")
        return 1
```

`ergon_core/ergon_core/core/rl/eval_runner.py`:

```python
async def evaluate_checkpoint(
    checkpoint_path: str,
    benchmark_type: str,
    *,
    evaluator_type: str = "stub-rubric",
    model_base: str | None = None,
    eval_limit: int | None = None,
) -> int:
    ckpt = CheckpointInfo(path=checkpoint_path, step=0, has_config=True, has_model=True)
    return await _run_local_eval(
        ckpt,
        benchmark_type=benchmark_type,
        evaluator_type=evaluator_type,
        model_base=model_base,
        eval_limit=eval_limit,
    )
```

- [ ] **Step 3: Verify the async rule**

Run:

```bash
uv run ruff format ergon_cli/ergon_cli/main.py ergon_cli/ergon_cli/commands/benchmark.py ergon_cli/ergon_cli/commands/eval.py ergon_core/ergon_core/core/rl/eval_runner.py
uv run ruff check ergon_cli/ergon_cli/main.py ergon_cli/ergon_cli/commands/benchmark.py ergon_cli/ergon_cli/commands/eval.py ergon_core/ergon_core/core/rl/eval_runner.py
uv run slopcop ergon_cli ergon_core/ergon_core/core/rl/eval_runner.py
uv run python scripts/check_suppression_budget.py
```

Expected:
- Ruff passes.
- `no-async-from-sync` is absent except the accepted console-script boundary.
- Suppression budget either passes with `slopcop_ignore=240` after an explicit budget update, or the bridge is handled without adding a counted ignore if Slopcop recognizes a better layout.

---

## Task 2: Fix Command Output Coalescing

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/minif2f/rules/proof_verification.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/minif2f/toolkit.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_manager.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/toolkit.py`
- Modify: `ergon_core/ergon_core/test_support/smoke_fixtures/workers/minif2f_smoke.py`
- Modify: `ergon_core/ergon_core/test_support/smoke_fixtures/workers/researchrubrics_smoke.py`
- Modify: `ergon_core/ergon_core/test_support/smoke_fixtures/workers/swebench_smoke.py`
- Test: existing benchmark/toolkit and smoke fixture unit tests

- [ ] **Step 1: Make every stdout/stderr fallback explicit**

Do not introduce a generic `_text_or_empty()` helper. For command output, keep
the `None` normalization visible at the sandbox or subprocess boundary:

If the value comes from an untyped exception via `getattr`, split the operations:

```python
stdout = getattr(exc, "stdout", None)  # slopcop: ignore[no-hasattr-getattr] -- sandbox SDK exception may carry stdout
stderr = getattr(exc, "stderr", None)  # slopcop: ignore[no-hasattr-getattr] -- sandbox SDK exception may carry stderr
stdout_text = "" if stdout is None else stdout
stderr_text = "" if stderr is None else stderr
output = stdout_text + stderr_text
```

- [ ] **Step 2: Replace stdout/stderr coalescing**

Examples to apply:

```python
# Before
output = (result.stdout or "") + (result.stderr or "")

# After
stdout = "" if result.stdout is None else result.stdout
stderr = "" if result.stderr is None else result.stderr
output = stdout + stderr
```

```python
# Before
probe_stdout = (probe.stdout or "").strip()[:4096]

# After
probe_stdout = ("" if probe.stdout is None else probe.stdout).strip()[:4096]
```

```python
# Before
tail = (r.stdout or "")[-1000:]

# After
stdout = "" if r.stdout is None else r.stdout
tail = stdout[-1000:]
```

- [ ] **Step 3: Fix SWE-Bench grading text without losing empty logs**

In `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py`:

```python
log = "" if r.stdout is None else r.stdout
```

For error detail, preserve first non-`None` text while allowing empty strings:

```python
detail = r.stdout if r.stdout is not None else r.stderr
return _error_result(self.name, self.weight, "install_repo failed", "" if detail is None else detail)
```

For `_write_and_apply`:

```python
stdout = "" if r.stdout is None else r.stdout
raise RuntimeError(f"git apply {path} failed: {stdout[-800:]}")
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run ruff check ergon_builtins/ergon_builtins/benchmarks/minif2f ergon_builtins/ergon_builtins/benchmarks/swebench_verified ergon_core/ergon_core/test_support/smoke_fixtures
uv run pytest tests/unit/smoke_base tests/unit/benchmarks tests/integration/minif2f -q
uv run slopcop ergon_builtins/ergon_builtins/benchmarks/minif2f ergon_builtins/ergon_builtins/benchmarks/swebench_verified ergon_core/ergon_core/test_support/smoke_fixtures
```

Expected:
- No `no-or-empty-coalesce` findings in the listed files.
- Existing smoke and benchmark tests pass or fail only for known external-service requirements.

---

## Task 3: Fix Runtime and API Coalescing

**Files:**
- Modify: `ergon_cli/ergon_cli/commands/benchmark.py`
- Modify: `ergon_core/ergon_core/core/api/runs.py`
- Modify: `ergon_core/ergon_core/core/api/test_harness.py`
- Modify: `ergon_core/ergon_core/core/persistence/telemetry/models.py`
- Modify: `ergon_core/ergon_core/core/persistence/telemetry/repositories.py`
- Modify: `ergon_core/ergon_core/core/rl/eval_runner.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/execute_task.py`
- Modify: `ergon_core/ergon_core/core/runtime/inngest/sandbox_setup.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/evaluation_persistence_service.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/evaluator_dispatch_service.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/experiment_persistence_service.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/run_service.py`
- Test: focused unit tests for runtime DTOs, Inngest services, and API run views

- [ ] **Step 1: Fix CLI cohort fallback**

In `ergon_cli/ergon_cli/commands/benchmark.py`:

```python
cohort_name = args.slug if args.cohort is None else args.cohort
```

This preserves `--cohort ""` if a caller intentionally passes an empty string.

- [ ] **Step 2: Fix API DTO fallbacks**

In `ergon_core/ergon_core/core/api/runs.py`, replace these patterns:

```python
worker = worker_by_binding.get(node.assigned_worker_slug or "")
error_msg = ex.error_json.get("message") or str(ex.error_json)
total_score=ev.score or 0.0
```

With:

```python
worker = (
    worker_by_binding.get(node.assigned_worker_slug)
    if node.assigned_worker_slug is not None
    else None
)
message = ex.error_json.get("message")
error_msg = message if isinstance(message, str) else str(ex.error_json)
total_score=0.0 if ev.score is None else ev.score
```

- [ ] **Step 3: Fix JSON defaults in test harness and telemetry**

Use explicit `None` checks:

```python
meta = {} if r.summary_json is None else r.summary_json
```

For list JSON accessors:

```python
tool_calls = [] if self.tool_calls_json is None else self.tool_calls_json
return [ToolCall.model_validate(tc) for tc in tool_calls]
```

For summary merging:

```python
existing_summary = dict({} if run.summary_json is None else run.summary_json)
```

- [ ] **Step 4: Fix runtime trace attributes without inventing empty strings**

In runtime/Inngest files, do not replace `x or ""` with
`"" if x is None else x`. That is the same behavior with different syntax.
Instead, decide whether each attribute is required or optional:

- Required fields should be enforced before the span is emitted. If task
  execution cannot continue without the value, raise the existing
  `ConfigurationError`/`ContractViolationError` before tracing.
- Optional trace-only fields should stay as `None` in `CompletedSpan.attributes`.
  `ergon_core.core.runtime.tracing.normalize_attributes()` drops `None`, so the
  exported span omits absent attributes instead of pretending the value is an
  empty string.

Then replace:

```python
"worker_type": prepared.worker_type or "",
"assigned_worker_slug": prepared.assigned_worker_slug or "",
"model_target": prepared.model_target or "",
"sandbox_id": result.sandbox_id or "",
```

With invariant checks or nullable attributes:

```python
if prepared.worker_type is None:
    raise ConfigurationError(
        "Task has no worker_type configured",
        run_id=payload.run_id,
        task_id=payload.task_id,
    )

attributes={
    "run_id": str(payload.run_id),
    "definition_id": str(payload.definition_id),
    "task_id": str(payload.task_id),
    "execution_id": str(prepared.execution_id),
    "task_slug": prepared.task_slug,
    "benchmark_type": prepared.benchmark_type,
    "worker_type": prepared.worker_type,
    "assigned_worker_slug": prepared.assigned_worker_slug,
    "model_target": prepared.model_target,
    "skipped": False,
    "status": "completed",
}
```

For sandbox setup, `sandbox_id` should be treated as part of the returned
contract. If it can truly be absent, omit the trace attribute by passing `None`;
if downstream requires it, raise a contract error before emitting:

```python
if result.sandbox_id is None:
    raise ContractViolationError(
        "sandbox-setup returned no sandbox_id",
        run_id=run_id,
        task_id=task_id,
    )

attributes={
    "run_id": str(run_id),
    "task_id": str(task_id),
    "benchmark_type": benchmark_type,
    "sandbox_id": result.sandbox_id,
    "input_resource_count": len(payload.input_resource_ids),
}
```

- [ ] **Step 5: Fix subprocess return code handling**

In `ergon_core/ergon_core/core/rl/eval_runner.py`:

```python
exit_code = 0 if proc.returncode is None else proc.returncode
```

- [ ] **Step 6: Run focused verification**

Run:

```bash
uv run ruff check ergon_cli/ergon_cli/commands/benchmark.py ergon_core/ergon_core/core/api/runs.py ergon_core/ergon_core/core/api/test_harness.py ergon_core/ergon_core/core/persistence/telemetry ergon_core/ergon_core/core/runtime ergon_core/ergon_core/core/rl/eval_runner.py
uv run pytest tests/unit/state tests/unit/runtime tests/unit/test_app_mounts_harness_conditionally.py -q
uv run slopcop ergon_cli/ergon_cli/commands/benchmark.py ergon_core/ergon_core/core/api/runs.py ergon_core/ergon_core/core/api/test_harness.py ergon_core/ergon_core/core/persistence/telemetry ergon_core/ergon_core/core/runtime ergon_core/ergon_core/core/rl/eval_runner.py
```

Expected:
- No `no-or-empty-coalesce` findings in runtime/API files.
- No new ty diagnostics in touched files.

---

## Task 4: Audit `Any` and Bare `object` by Boundary

**Files:**
- Modify: `ergon_core/ergon_core/core/persistence/definitions/models.py`
- Modify: `ergon_core/ergon_core/core/persistence/saved_specs/models.py`
- Modify: `ergon_core/ergon_core/core/persistence/graph/models.py`
- Modify: `ergon_core/ergon_core/core/persistence/telemetry/models.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/*_dto.py`
- Modify: `ergon_core/ergon_core/core/runtime/evaluation/evaluation_schemas.py`
- Modify: `ergon_core/ergon_core/api/*.py`
- Modify: `ergon_builtins/ergon_builtins/tools/*.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/*/*.py`
- Modify: `ergon_infra/ergon_infra/adapters/*.py`
- Test: corresponding unit tests and `ty`

- [ ] **Step 1: Introduce a shared JSON type alias**

If there is no existing equivalent, create `ergon_core/ergon_core/api/json_types.py`:

```python
"""JSON-compatible public type aliases."""

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
```

Use this only for real JSON boundaries: persisted model JSON columns, API metadata bags, trace attributes, tool payloads, and third-party HTTP payloads.

- [ ] **Step 2: Replace bare `object` when code expects JSON**

Examples:

```python
from ergon_core.api.json_types import JsonObject, JsonValue

metadata: JsonObject
task_payload: JsonObject
attributes: dict[str, JsonValue]
```

Do not use `JsonValue` when the code expects a model, SDK object, callable, or protocol.

- [ ] **Step 3: Replace tool call shapes with typed models or aliases**

For toolkits in `ergon_builtins/ergon_builtins/tools`, inspect how each value is accessed. If the function returns a fixed response shape, create a Pydantic response model instead of `dict[str, object]`:

```python
class ToolResult(BaseModel):
    success: bool
    message: str
    data: JsonObject | None = None
```

Use existing project response models when they already exist.

- [ ] **Step 4: Keep true untyped third-party boundaries suppressed with reasons**

Acceptable examples:

```python
def get_eval_report(
    *,
    test_spec: Any,  # slopcop: ignore[no-typing-any] -- SWE-Bench returns an untyped TestSpec object
    prediction: dict[str, str],
    test_log_path: str,
    include_tests_status: bool = True,
) -> dict[str, JsonValue]:
```

Unacceptable examples:

```python
payload: dict[str, Any]
metadata: dict[str, object]
```

These should become `JsonObject`, a Pydantic model, or a protocol.

- [ ] **Step 5: Run type and Slopcop verification by domain**

Run after each domain batch:

```bash
uv run ty check ergon_core/ergon_core ergon_builtins ergon_infra
uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra
uv run pytest tests/unit -q
```

Expected:
- `no-typing-any` count falls after each batch.
- Remaining `Any` suppressions have reasons tied to real external or framework boundaries.

---

## Task 5: Tighten the CI Contract

**Files:**
- Modify: `package.json`
- Modify: `.github/workflows/ci-fast.yml`
- Modify: `scripts/check_suppression_budget.py`
- Test: `tests/unit/test_suppression_budget.py`

- [ ] **Step 1: Keep Slopcop strict**

Do not change CI to `--warn-only`. `slopcop 0.1.1` is repo-specific enough that warnings should be treated as work items.

Keep:

```json
"check:be:slopcop": "uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra"
```

And:

```yaml
- name: slopcop check
  run: uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra
```

- [ ] **Step 2: Update the suppression budget only for reviewed suppressions**

If the console-script bridge remains the only new suppression:

```python
BUDGET = SuppressionCounts(
    slopcop_ignore=240,
    noqa=0,
    type_ignore=83,
)
```

Do not raise the budget for avoidable `Any`, coalescing, or broad exception suppressions.

- [ ] **Step 3: Verify the final gates**

Run:

```bash
uv run ruff check ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
uv run ruff format --check ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
uv run ty check ergon_core/ergon_core ergon_builtins ergon_cli ergon_infra
uv run slopcop ergon_core ergon_builtins ergon_cli ergon_infra
uv run python scripts/check_suppression_budget.py
uv run pytest tests/unit -q
```

Expected:
- Slopcop exits 0 with no errors or warnings.
- Suppression budget passes.
- Unit tests pass.

---

## Self-Review

- Spec coverage: The plan covers the new `slopcop 0.1.1` rules currently failing the gate: async bridge, empty coalescing, and `Any`/bare `object`.
- Placeholder scan: No task says "TBD" or "fix appropriately"; each task includes concrete file paths, example code, and commands.
- Type consistency: `JsonValue` and `JsonObject` are consistently named across tasks; no generic empty-string helper remains.
- Remaining risk: The `Any` cleanup is large and should be executed in domain batches. Do not attempt a single mechanical all-repo replacement.
