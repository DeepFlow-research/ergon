# Test Quality Improvements

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address 45 identified issues across unit and integration tests — covering reuse/DRY, code quality, coverage gaps, assertion strength, performance, isolation (Part 1), and weak-test patterns identified against the pydantic-ai gold standard (Part 2).

---

## Part 2: Weak Tests (pydantic-ai gold standard comparison)

### pydantic-ai testing philosophy applied

- **Precise `pytest.raises`** — always specifies the exact exception type + `match=` regex, never bare `Exception`
- **Parametrize aggressively** — any multi-case boolean/string logic becomes a single parametrized test
- **Error paths as first-class citizens** — every happy path has a corresponding raises/error-state counterpart with message content verified
- **Assert all fields, not just presence** — `result.passed`, `result.score`, `result.feedback` all asserted, not just `result.name`
- **Test behaviour, not structure** — never `inspect.getsource`, never positional index into a list, never `cls.__name__`
- **Exact status codes** — `assert resp.status_code == 404`, never `in (404, 500)`

---

### Task 26: Fix bare `except Exception` in frozen-model tests

**Files:**
- Modify: `tests/unit/state/test_benchmark_contract.py`
- Modify: `tests/unit/state/test_llm_judge_runtime_injection.py`

- [ ] **Step 1: Find all bare `pytest.raises(Exception)` in unit tests**

```bash
rg -n "pytest\.raises\(Exception\)" tests/unit/
```

- [ ] **Step 2: Replace with precise exception type + match=**

Each should become:

```python
with pytest.raises(ValidationError, match="frozen instance"):
    record.some_field = new_value
```

Import `from pydantic import ValidationError` if not already present.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_benchmark_contract.py tests/unit/state/test_llm_judge_runtime_injection.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_benchmark_contract.py tests/unit/state/test_llm_judge_runtime_injection.py
git commit -m "test(state): replace bare pytest.raises(Exception) with precise ValidationError + match"
```

---

### Task 27: Replace `cls.__name__` assertions with `type_slug` / `is` checks

**Files:**
- Modify: `tests/unit/state/test_research_rubrics_benchmark.py`

- [ ] **Step 1: Read lines 15 and 23**

Find both `assert cls.__name__ == "..."` assertions.

- [ ] **Step 2: Replace with behavioural contract**

```python
# Before
assert cls.__name__ == "ResearchRubricsBenchmark"

# After
assert BENCHMARKS["researchrubrics-ablated"] is ResearchRubricsBenchmark
assert issubclass(ResearchRubricsBenchmark, Benchmark)
```

The `is` identity check is the real contract — the slug maps to this exact class.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_research_rubrics_benchmark.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_research_rubrics_benchmark.py
git commit -m "test(registry): assert registry slug maps to correct class identity, not __name__ string"
```

---

### Task 28: Parametrize `test_type_invariants.py`

**Files:**
- Modify: `tests/unit/state/test_type_invariants.py`

- [ ] **Step 1: Read the full file**

```bash
cat -n tests/unit/state/test_type_invariants.py
```

Identify every test class and list the `(ModelClass, field_name, input_value, expected)` tuples.

- [ ] **Step 2: Rewrite as parametrized tests**

```python
import pytest
from pydantic import ValidationError

@pytest.mark.parametrize("cls,kwargs,field,expected", [
    (RunRecord, {...}, "status", RunStatus.PENDING),
    (RunTaskExecution, {...}, "status", ExecutionStatus.PENDING),
    (RunResource, {...}, "node_id", some_node_id),
    # ... all variants
])
def test_field_stores_value(cls, kwargs, field, expected):
    obj = cls(**kwargs)
    assert getattr(obj, field) == expected


@pytest.mark.parametrize("cls,frozen_field,new_value", [
    (RunRecord, "status", RunStatus.COMPLETED),
    # ... all frozen model mutation cases
])
def test_frozen_model_rejects_mutation(cls, frozen_field, new_value):
    obj = cls(...)
    with pytest.raises(ValidationError, match="frozen instance"):
        setattr(obj, frozen_field, new_value)
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_type_invariants.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_type_invariants.py
git commit -m "test(state): parametrize type invariant tests to eliminate per-model boilerplate"
```

---

### Task 29: Fix positional-index tool assertions in `test_subtask_lifecycle_toolkit.py`

**Files:**
- Modify: `tests/unit/smoke_base/test_subtask_lifecycle_toolkit.py`

- [ ] **Step 1: Read the full file**

```bash
cat -n tests/unit/smoke_base/test_subtask_lifecycle_toolkit.py
```

Identify all uses of `tools[0]`, `tools[2]`, etc.

- [ ] **Step 2: Replace count + name checks with a single set assertion**

```python
def test_get_tools_returns_expected_set() -> None:
    tools = _make_toolkit().get_tools()
    names = {t.__name__ for t in tools}
    assert names == {
        "add_subtask", "plan_subtasks", "cancel_task",
        "refine_task", "restart_task", "list_subtasks",
        "get_subtask", "bash",
    }


def test_add_subtask_is_async() -> None:
    tools = _make_toolkit().get_tools()
    add = next(t for t in tools if t.__name__ == "add_subtask")
    assert asyncio.iscoroutinefunction(add)
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/smoke_base/test_subtask_lifecycle_toolkit.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/smoke_base/test_subtask_lifecycle_toolkit.py
git commit -m "test(subtask-lifecycle): replace positional tool[i] indexing with name-based lookup"
```

---

### Task 30: Pin error message content in lifecycle toolkit error-path tests

**Files:**
- Modify: `tests/unit/smoke_base/test_subtask_lifecycle_toolkit.py` (or `tests/unit/state/test_subtask_lifecycle_toolkit.py` — whichever has `assert isinstance(result["error"], str)`)

- [ ] **Step 1: Find the loose error assertions**

```bash
rg -n 'isinstance.*"error".*str\|len.*"error".*> 0' tests/unit/
```

- [ ] **Step 2: Add content assertions**

```python
# Before
assert isinstance(result["error"], str)
assert len(result["error"]) > 0

# After
assert isinstance(result["error"], str)
assert "uuid" in result["error"].lower()  # or "invalid" — match actual message
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest -k "lifecycle_toolkit" -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test(subtask-lifecycle): assert error message content, not just non-empty string"
```

---

### Task 31: Replace `inspect.getsource` ordering test with runtime behaviour test

**Files:**
- Modify: `tests/unit/smoke_base/test_leaf_sends_completion_message.py`

- [ ] **Step 1: Read lines 104-144**

Find the test that does `inspect.getsource(lb.BaseSmokeLeafWorker.execute)` and asserts on text positions.

- [ ] **Step 2: Rewrite as a runtime behaviour test**

Instead of asserting source-code order, execute the code path and observe the outcome:

```python
async def test_completion_message_not_sent_when_subworker_raises(monkeypatch):
    """_send_completion_message must not be called if subworker.work() raises."""
    send_calls = []

    async def _fake_send(*args, **kwargs):
        send_calls.append((args, kwargs))

    monkeypatch.setattr(BaseSmokeLeafWorker, "_send_completion_message", _fake_send)

    leaf = _FailingLeaf(...)  # subworker raises during work()
    with pytest.raises(SomeExpectedException):
        async for _ in leaf.execute(task, context=context):
            pass

    assert send_calls == [], "_send_completion_message must not be called when subworker raises"
```

Adapt to the actual class/exception structure from reading the file.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/smoke_base/test_leaf_sends_completion_message.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/smoke_base/test_leaf_sends_completion_message.py
git commit -m "test(smoke_base): replace inspect.getsource ordering check with runtime behaviour assertion"
```

---

### Task 32: Rename and strengthen context assembly test

**Files:**
- Modify: `tests/unit/state/test_context_assembly.py`

- [ ] **Step 1: Read lines 203-214**

Find `test_only_request_events_no_response`.

- [ ] **Step 2: Rename + strengthen assertion**

```python
def test_pending_request_parts_not_flushed_without_response_event(self):
    """Request events alone must not produce assembled messages — flush requires a response."""
    events = [
        _make_event("system_prompt", SystemPromptPayload(text="sys"), 0),
        _make_event("user_message", UserMessagePayload(text="hi"), 1),
    ]
    messages = assemble_pydantic_ai_messages(events)
    assert messages == []  # exact equality, not just len == 0
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_context_assembly.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_context_assembly.py
git commit -m "test(state): rename and strengthen context assembly flush-semantics test"
```

---

### Task 33: Strengthen MiniF2F criterion result assertions

**Files:**
- Modify: `tests/unit/benchmarks/test_minif2f_proof_verification.py`

- [ ] **Step 1: Read lines 63-86**

Find both tests — the happy path (proof present) and the zero-score path.

- [ ] **Step 2: Assert all result fields**

```python
# Happy path
assert result.passed is True
assert result.score == 1.0
assert result.name  # existing

# Error path (proof missing)
assert result.passed is False
assert result.score == 0.0
assert result.feedback is not None
assert "not found" in result.feedback.lower()  # or whatever the actual message is
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/benchmarks/test_minif2f_proof_verification.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/benchmarks/test_minif2f_proof_verification.py
git commit -m "test(minif2f): assert passed/score/feedback on criterion results, not just name presence"
```

---

### Task 34: Fix tool count assertion in `test_react_factories.py`

**Files:**
- Modify: `tests/unit/registry/test_react_factories.py`

- [ ] **Step 1: Read line 62 and surrounding context**

Find `assert worker.tools != []`. Determine the expected tool count for the MiniF2F factory (check what toolkit it uses).

- [ ] **Step 2: Replace with exact count**

```python
# Before
assert worker.tools != []

# After
assert len(worker.tools) == <N>  # e.g. 6 for MiniF2FToolkit — verify from toolkit source
```

Look at `MiniF2FToolkit.get_tools()` to confirm N.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/registry/test_react_factories.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/registry/test_react_factories.py
git commit -m "test(registry): assert exact tool count for react factory, not just non-empty"
```

---

### Task 35: Parametrize `test_event_schema_phase0.py`

**Files:**
- Modify: `tests/unit/state/test_event_schema_phase0.py`

- [ ] **Step 1: Read the full file**

```bash
cat -n tests/unit/state/test_event_schema_phase0.py
```

List every model class being tested and the constructor kwargs for each.

- [ ] **Step 2: Collapse 8 test class pairs into parametrized functions**

```python
_NODE_ID_MODELS = [
    (TaskReadyEvent, {"run_id": _RUN_ID, "definition_id": _DEF_ID, "task_id": _TASK_ID}),
    (TaskCompletedEvent, {"run_id": _RUN_ID, "node_id": None, ...}),
    # ... all 8 classes
]

@pytest.mark.parametrize("cls,base_kwargs", _NODE_ID_MODELS)
def test_node_id_accepts_value(cls, base_kwargs):
    nid = NodeId(uuid4())
    obj = cls(**base_kwargs, node_id=nid)
    assert obj.node_id == nid
    # Round-trip:
    assert cls.model_validate(obj.model_dump()).node_id == nid


@pytest.mark.parametrize("cls,base_kwargs", _NODE_ID_MODELS)
def test_node_id_defaults_to_none(cls, base_kwargs):
    obj = cls(**base_kwargs)
    assert obj.node_id is None
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_event_schema_phase0.py -v
```

Expected: same number of passing tests as before, now parametrized.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_event_schema_phase0.py
git commit -m "test(state): parametrize event schema node_id tests across all 8 model classes"
```

---

### Task 36: Parametrize LLM judge pass/fail verdict test

**Files:**
- Modify: `tests/unit/state/test_llm_judge_runtime_injection.py`

- [ ] **Step 1: Read lines 57-84**

Find the two near-identical `test_evaluate_calls_runtime` / `test_evaluate_failing_verdict` functions.

- [ ] **Step 2: Collapse to one parametrized test**

```python
@pytest.mark.parametrize("passed,expected_score,reasoning", [
    (True,  1.0, "Good coverage"),
    (False, 0.0, "Report lacks sources"),
])
async def test_evaluate_verdict(passed, expected_score, reasoning, mock_runtime):
    criterion = LLMJudgeCriterion(...)
    mock_runtime.return_value = _JudgeVerdict(passed=passed, reasoning=reasoning)
    result = await criterion.evaluate(ctx)
    assert result.passed is passed
    assert result.score == expected_score
    assert reasoning in result.feedback
```

Adapt to the actual API from reading the file.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_llm_judge_runtime_injection.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_llm_judge_runtime_injection.py
git commit -m "test(criterion): parametrize LLM judge pass/fail verdict into single test"
```

---

### Task 37: Add second-script exit-code test to `test_swebench_sandbox_manager.py`

**Files:**
- Modify: `tests/unit/benchmarks/test_swebench_sandbox_manager.py`

- [ ] **Step 1: Read lines 27-52**

Understand `test_install_raises_on_nonzero_exit` and the `_fake_run` structure.

- [ ] **Step 2: Parametrize across both scripts**

```python
@pytest.mark.parametrize("failing_script", ["setup_env_script", "install_repo_script"])
def test_install_raises_when_script_fails(failing_script, monkeypatch):
    def _fake_run(cmd, **kwargs):
        if failing_script in cmd:
            return FakeResult(exit_code=1, stderr=f"{failing_script} failed")
        return FakeResult(exit_code=0)

    monkeypatch.setattr(sandbox, "run_command", _fake_run)
    with pytest.raises(SandboxSetupError, match=failing_script):
        sandbox.install(task_id=some_uuid)
```

Adapt to actual class/method names from reading the file.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/benchmarks/test_swebench_sandbox_manager.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/benchmarks/test_swebench_sandbox_manager.py
git commit -m "test(swebench): parametrize sandbox install failure across both setup scripts"
```

---

### Task 38: Fix non-deterministic status code in harness mount test

**Files:**
- Modify: `tests/unit/test_app_mounts_harness_conditionally.py`

- [ ] **Step 1: Read lines 29-39**

Find the `assert resp.status_code in (404, 500)` assertion and understand the app loading pattern.

- [ ] **Step 2: Override DB dependency to make response deterministic**

Follow the pattern from `test_test_harness.py` — inject a stub session so DB absence returns 404, not 500:

```python
def test_harness_mounted_when_env_set(monkeypatch):
    app = _reload_app_with(monkeypatch, "1")
    app.dependency_overrides[get_session] = lambda: _null_session()
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    assert resp.status_code == 404  # route exists, run not found — deterministic
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/test_app_mounts_harness_conditionally.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_app_mounts_harness_conditionally.py
git commit -m "test(harness): inject null DB session to get deterministic 404 instead of 500"
```

---

### Task 39: Fix over-mocked `ReActWorker.execute` in `test_research_rubrics_workers.py`

**Files:**
- Modify: `tests/unit/state/test_research_rubrics_workers.py`

- [ ] **Step 1: Read lines 63-118**

Understand what `patch("...ReActWorker.execute")` is replacing and what `worker.tools` is expected to contain.

- [ ] **Step 2: Remove the wholesale execute mock; mock only I/O**

The goal is to verify that `worker.tools` is set up by the `execute` preamble. Instead of mocking `execute` entirely, extract the tool-registration into a dedicated test that doesn't call `execute` at all:

```python
async def test_tools_registered_after_execute_setup(monkeypatch):
    """Tool registration happens in execute() preamble before super().execute()."""
    # Patch super().execute() to stop after preamble, not the whole method
    stopped = []
    async def _stop(*args, **kwargs):
        stopped.append(True)
        return
        yield  # make it an async generator

    monkeypatch.setattr(ReActWorker, "execute", _stop)
    worker = ResearchRubricsManagerWorker(...)
    async for _ in worker.execute(task, context=ctx):
        pass
    assert len(worker.tools) == 12
    assert stopped  # confirm we did enter execute
```

Adapt based on actual class hierarchy.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_research_rubrics_workers.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_research_rubrics_workers.py
git commit -m "test(workers): mock only super().execute to keep tool-registration preamble under test"
```

---

### Task 40: Fix `test_no_retired_slugs_present` to check registry, not module attributes

**Files:**
- Modify: `tests/unit/smoke_base/test_registry_smoke_entries.py`

- [ ] **Step 1: Read lines 40-44**

Find `assert not hasattr(fixtures, "CanonicalSmokeWorker")`.

- [ ] **Step 2: Replace with registry key check**

```python
def test_no_retired_slugs_present() -> None:
    from ergon_builtins.registry_core import WORKERS, EVALUATORS
    retired_worker_slugs = {"canonical-smoke"}
    assert not (retired_worker_slugs & set(WORKERS.keys())), (
        f"Retired worker slugs still in registry: {retired_worker_slugs & set(WORKERS.keys())}"
    )
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/smoke_base/test_registry_smoke_entries.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/smoke_base/test_registry_smoke_entries.py
git commit -m "test(registry): check registry keys for retired slugs, not module attribute presence"
```

---

### Task 41: Assert full expected worker slug set in `test_research_rubrics_benchmark.py`

**Files:**
- Modify: `tests/unit/state/test_research_rubrics_benchmark.py`

- [ ] **Step 1: Read lines 25-29**

Find the single `assert "researchrubrics-researcher" in WORKERS` check.

- [ ] **Step 2: Assert the full expected set**

```python
def test_worker_slugs_registered(self):
    from ergon_builtins.registry_data import WORKERS
    expected = {"researchrubrics-researcher"}  # full authoritative list
    missing = expected - set(WORKERS.keys())
    assert not missing, f"Expected worker slugs missing from registry: {missing}"
```

(Add any additional slugs that should be present beyond the researcher.)

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_research_rubrics_benchmark.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_research_rubrics_benchmark.py
git commit -m "test(registry): assert full expected worker slug set, not just one slug"
```

---

### Task 42: Assert `feedback` content on MiniF2F proof-missing path

**Files:**
- Modify: `tests/unit/benchmarks/test_minif2f_proof_verification.py`

- [ ] **Step 1: Read lines 67-86**

Find `test_scores_zero_when_proof_missing`.

- [ ] **Step 2: Add feedback content assertion**

```python
assert result.score == 0.0
assert not result.passed
assert result.feedback is not None
assert "not found" in result.feedback.lower()  # verify actual message from production code
```

Read the production criterion code to confirm the exact error string used.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/benchmarks/test_minif2f_proof_verification.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/benchmarks/test_minif2f_proof_verification.py
git commit -m "test(minif2f): assert feedback message content on proof-missing error path"
```

---

### Task 43: Consolidate CLI error tests into parametrized rc + stderr checks

**Files:**
- Modify: `tests/unit/cli/test_benchmark_setup.py`

- [ ] **Step 1: Read lines 67-83**

Find `test_fails_when_api_key_unset`, `test_error_message_mentions_api_key`, `test_fails_for_unknown_slug`.

- [ ] **Step 2: Collapse to single parametrized test**

```python
@pytest.mark.parametrize("setup_fn,expected_stderr_fragment", [
    (_unset_api_key,       "api_key"),
    (_set_unknown_slug,    "unknown"),
])
def test_setup_fails_with_informative_error(setup_fn, expected_stderr_fragment, monkeypatch, capsys):
    setup_fn(monkeypatch)
    rc = setup_benchmark(_make_args())
    assert rc != 0
    captured = capsys.readouterr()
    assert expected_stderr_fragment in (captured.err + captured.out).lower()
```

Each case simultaneously checks both the exit code and the message content.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/cli/test_benchmark_setup.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/cli/test_benchmark_setup.py
git commit -m "test(cli): parametrize error cases to assert both exit code and error message content"
```

---

## Part 3: Zero-Value Test Deletions

Tests that pass unconditionally regardless of whether the production code works. Delete outright — no replacement needed.

---

### Task 44: Delete `test_add_subtask_tool_is_async_callable` and `test_get_tools_returns_eight_callables`

**Files:**
- Modify: `tests/unit/state/test_subtask_lifecycle_toolkit.py`

Both functions are redundant noise:
- `test_get_tools_returns_eight_callables` — `len(tools) == 8` is already proved by `test_tools_have_correct_function_names` which lists all 8 names. `all(callable(t) for t in tools)` tests Python's `def` keyword.
- `test_add_subtask_tool_is_async_callable` — `asyncio.iscoroutinefunction(tools[0])` tests Python's `async` keyword via a positional index. Type-checking catches accidental sync-ification; the positional index also makes it fragile to reordering.

- [ ] **Step 1: Delete both functions**

Remove lines 17-27 (both `test_get_tools_returns_eight_callables` and `test_add_subtask_tool_is_async_callable`) from `tests/unit/state/test_subtask_lifecycle_toolkit.py`. Also remove the now-unused `import asyncio` at the top if it's only used by those two tests.

- [ ] **Step 2: Run tests to confirm nothing else was relying on them**

```bash
uv run pytest tests/unit/state/test_subtask_lifecycle_toolkit.py -v
```

Expected: remaining tests still pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/state/test_subtask_lifecycle_toolkit.py
git commit -m "test(subtask-lifecycle): delete zero-value async/callable assertions covered by name test"
```

---

### Task 45: Delete `tests/unit/api/test_types_reexport.py`

**Files:**
- Delete: `tests/unit/api/test_types_reexport.py`

Both functions in this file test Python language mechanics, not application logic:

- `test_tool_is_reexported_from_api_root` — the two assertions (`_takes_tools([]) == 0`, `_takes_tools([object(), object()]) == 2`) test `len()` on literal lists. The comment in the file itself says `# noqa: F401 — import is the assertion`. The import is covered by `ty` type checking.
- `test_tool_module_is_importable` — `hasattr(api_types, "Tool")` is a pure import test. Covered by `ty`.

- [ ] **Step 1: Delete the file**

```bash
git rm tests/unit/api/test_types_reexport.py
```

- [ ] **Step 2: Check nothing imports from it**

```bash
rg "test_types_reexport" tests/
```

Expected: zero matches.

- [ ] **Step 3: Run the api test suite**

```bash
uv run pytest tests/unit/api/ -v
```

- [ ] **Step 4: Commit**

```bash
git commit -m "test(api): delete test_types_reexport — pure import tests covered by ty type checker"
```

---

## Part 4: Gaps to reach 8+/10

Three categories not covered above that are required to reach 8/10: the docstring lie in `test_type_invariants.py`, a small DRY consolidation left unfinished, and zero test coverage for three production abstractions added in the recent refactor.

---

### Task 46: Add invalid-value rejection tests to `test_type_invariants.py`

**Files:**
- Modify: `tests/unit/state/test_type_invariants.py`

The file's docstring says *"Verifies that enum/Literal fields reject invalid values at model construction time"* but contains **zero** tests that pass an invalid value. Every test only constructs with a valid value and asserts it is stored. Task 28 (Part 2) adds parametrize + frozen-mutation tests; this task adds the construction-time rejection tests that the docstring actually promises.

- [ ] **Step 1: Read the file and list every constrained field**

```bash
cat -n tests/unit/state/test_type_invariants.py
```

For each model/field being tested, identify what "invalid" looks like (a string literal outside the enum, `None` for a required field, a negative integer for a `PositiveInt`, etc.).

- [ ] **Step 2: Write rejection tests — one per constrained field**

```python
from pydantic import ValidationError
import pytest

@pytest.mark.parametrize("cls,kwargs_override,invalid_field,invalid_value", [
    (
        RunRecord,
        {"experiment_definition_id": uuid4()},
        "status",
        "not-a-status",
    ),
    (
        RunTaskExecution,
        {"run_id": uuid4(), "definition_task_id": uuid4()},
        "status",
        "garbage",
    ),
    (
        RunGenerationTurn,
        {"run_id": uuid4(), "task_execution_id": uuid4(),
         "worker_binding_key": "w", "turn_index": 0, "raw_response": {}},
        "execution_outcome",
        "unknown-outcome",
    ),
    # ... add a case for every model with a constrained field
])
def test_invalid_field_value_rejected(cls, kwargs_override, invalid_field, invalid_value):
    """Enum/Literal fields must raise ValidationError for invalid values at construction."""
    with pytest.raises(ValidationError):
        cls(**{**kwargs_override, invalid_field: invalid_value})
```

Run it to confirm it fails first (production code should raise — if it doesn't, that's a real bug to fix):

```bash
uv run pytest tests/unit/state/test_type_invariants.py::test_invalid_field_value_rejected -v
```

Expected: PASS (Pydantic should reject these). If any case unexpectedly passes (no error raised), the production model is missing a validator — file a bug and tighten the model.

- [ ] **Step 3: Run the full file**

```bash
uv run pytest tests/unit/state/test_type_invariants.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_type_invariants.py
git commit -m "test(state): add construction-time rejection tests — fulfill docstring contract in test_type_invariants"
```

---

### Task 47: Consolidate cancel/refine/restart error-path tests into one parametrized test

**Files:**
- Modify: `tests/unit/state/test_subtask_lifecycle_toolkit.py`

Task 30 (Part 2) pins the error message content in these three functions. This task consolidates the three near-identical functions into a single parametrized test to remove the copy-paste. Do this after Task 30 so the content assertions are already in place.

- [ ] **Step 1: Read the three functions after Task 30 is applied**

The three functions (`test_cancel_task_handles_invalid_uuid_gracefully`, `test_refine_task_handles_invalid_uuid_gracefully`, `test_restart_task_handles_invalid_uuid_gracefully`) will differ only by which tool they call and what args they pass. Note each: `(tool_name, args_tuple)`.

- [ ] **Step 2: Collapse into one parametrized test**

```python
@pytest.mark.parametrize("tool_name,args", [
    ("cancel_task",  ("not-a-uuid",)),
    ("refine_task",  ("not-a-uuid", "new description")),
    ("restart_task", ("not-a-uuid",)),
])
async def test_invalid_uuid_returns_error(tool_name: str, args: tuple) -> None:
    tools = _make_toolkit().get_tools()
    tool = next(t for t in tools if t.__name__ == tool_name)
    result = await tool(*args)
    assert result["success"] is False
    assert "uuid" in result["error"].lower()
```

- [ ] **Step 3: Delete the three original functions**

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/state/test_subtask_lifecycle_toolkit.py -v
```

Expected: 3 parametrize variants passing, replacing 3 functions.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/state/test_subtask_lifecycle_toolkit.py
git commit -m "test(subtask-lifecycle): consolidate cancel/refine/restart error paths into parametrized test"
```

---

### Task 48: Add unit tests for `is_stub_sandbox_id()`, `VLLMDiscoveryError`, `RunRecordMissingError`

Three production abstractions added in the recent refactor have **zero test coverage**. Confirmed with:

```bash
rg "is_stub_sandbox_id|VLLMDiscoveryError|RunRecordMissingError" tests/unit/ tests/integration/
# → zero matches
```

**Files:**
- Create: `tests/unit/sandbox/test_stub_sandbox_id.py`
- Create: `tests/unit/runtime/test_vllm_discovery_error.py`
- Create: `tests/unit/runtime/test_run_record_missing_error.py`

(Or consolidate into nearby existing test files if they fit naturally — see steps below.)

- [ ] **Step 1: Locate the production implementations**

```bash
rg -n "def is_stub_sandbox_id\|class VLLMDiscoveryError\|class RunRecordMissingError" ergon_core/ ergon_builtins/
```

Read each to understand the contract.

- [ ] **Step 2: Write tests for `is_stub_sandbox_id()`**

```python
# tests/unit/sandbox/test_stub_sandbox_id.py
import pytest
from ergon_core.core.runtime.inngest.execute_task import is_stub_sandbox_id  # adjust import

@pytest.mark.parametrize("sandbox_id,expected", [
    ("stub-sbx-abc123",  True),   # adjust prefix to match actual implementation
    ("sbx-real-123",     False),
    ("",                 False),
    (None,               False),  # if None is a valid input
])
def test_is_stub_sandbox_id(sandbox_id, expected):
    assert is_stub_sandbox_id(sandbox_id) is expected
```

Adjust the parametrize cases to match the actual stub prefix/pattern from reading the source.

- [ ] **Step 3: Write tests for `VLLMDiscoveryError`**

```python
# tests/unit/runtime/test_vllm_discovery_error.py
import pytest
from ergon_core.core.providers.generation.vllm_model import VLLMDiscoveryError, _discover_vllm_model_name

def test_discovery_raises_when_endpoint_unreachable(monkeypatch):
    """_discover_vllm_model_name must raise VLLMDiscoveryError, not return 'default'."""
    import urllib.error
    monkeypatch.setattr(
        "ergon_core.core.providers.generation.vllm_model.urllib.request.urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(urllib.error.URLError("connection refused")),
    )
    with pytest.raises(VLLMDiscoveryError, match="connection refused"):
        _discover_vllm_model_name("http://localhost:8000")


def test_discovery_raises_on_malformed_json(monkeypatch):
    """Malformed JSON response must raise VLLMDiscoveryError, not crash."""
    # monkeypatch urlopen to return b"not json"
    ...
    with pytest.raises(VLLMDiscoveryError):
        _discover_vllm_model_name("http://localhost:8000")
```

Adapt to the actual function signature and import path from step 1.

- [ ] **Step 4: Write tests for `RunRecordMissingError`**

```python
# tests/unit/runtime/test_run_record_missing_error.py
import pytest
from ergon_core.core.runtime.errors.delegation_errors import RunRecordMissingError
from ergon_core.core.runtime.services.task_management_service import TaskManagementService

def test_raises_when_run_record_missing(mock_session):
    """TaskManagementService must raise RunRecordMissingError, not AttributeError or None."""
    # mock_session returns None for RunRecord query
    svc = TaskManagementService()
    with pytest.raises(RunRecordMissingError, match="RunRecord"):
        svc.some_method(mock_session, run_id=uuid4())
```

Read the production code to identify which method triggers this and adapt accordingly.

- [ ] **Step 5: Run all three new test files**

```bash
uv run pytest tests/unit/sandbox/test_stub_sandbox_id.py \
              tests/unit/runtime/test_vllm_discovery_error.py \
              tests/unit/runtime/test_run_record_missing_error.py -v
```

- [ ] **Step 6: Commit**

```bash
git add tests/unit/sandbox/test_stub_sandbox_id.py \
        tests/unit/runtime/test_vllm_discovery_error.py \
        tests/unit/runtime/test_run_record_missing_error.py
git commit -m "test(runtime,sandbox): add unit tests for is_stub_sandbox_id, VLLMDiscoveryError, RunRecordMissingError"
```

---

**Goal:** Address 48 identified issues across unit and integration tests — covering reuse/DRY, code quality, coverage gaps, assertion strength, performance, isolation (Part 1), weak-test patterns against the pydantic-ai gold standard (Part 2), zero-value test deletions (Part 3), and the remaining gaps to reach 8+/10 cleanliness (Part 4).

**Architecture:** No production code changes. All fixes are confined to `tests/unit/` and `tests/integration/` (plus new conftest files). Changes are independent and can be done in any order.

**Tech Stack:** pytest, pytest-asyncio (`asyncio_mode=auto`), pytest-xdist (`-n auto`), SQLModel, unittest.mock

---

## Category 1: Reuse / DRY

### Task 1: Deduplicate `_patch_session_with_rows()` across runtime tests

**Files:**
- Create: `tests/unit/runtime/conftest.py`
- Modify: `tests/unit/runtime/test_criterion_runtime_get_all_files.py`
- Modify: any other runtime test files that define the same helper (verify with `rg "_patch_session_with_rows" tests/unit/runtime/`)

- [ ] **Step 1: Locate all duplicates**

```bash
rg "_patch_session_with_rows" tests/unit/runtime/
```

Note every file that defines this helper.

- [ ] **Step 2: Write the shared fixture**

Create `tests/unit/runtime/conftest.py`:

```python
import contextlib
from collections.abc import Generator
from unittest.mock import MagicMock, patch


@contextlib.contextmanager
def patch_session_with_rows(rows: list) -> Generator[MagicMock, None, None]:
    """Patch get_session() to yield a mock session with the given query rows."""
    mock_session = MagicMock()
    mock_session.exec.return_value.all.return_value = rows
    with patch("ergon_core.core.persistence.shared.db.get_session") as mock_get:
        mock_get.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_session
```

(Adjust the patch target to match the actual import path found in step 1.)

- [ ] **Step 3: Replace the inline definitions**

In each file identified in step 1, remove the local `_patch_session_with_rows` definition and import the shared one:

```python
from tests.unit.runtime.conftest import patch_session_with_rows
```

- [ ] **Step 4: Run tests to verify nothing broke**

```bash
uv run pytest tests/unit/runtime/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/runtime/
git commit -m "test(runtime): extract _patch_session_with_rows to shared conftest"
```

---

### Task 2: Extract shared smoke_base fixtures to conftest

**Files:**
- Create: `tests/unit/smoke_base/conftest.py`
- Modify: `tests/unit/smoke_base/test_smoke_criterion_shape.py`
- Modify: `tests/unit/smoke_base/test_smoke_criterion_completed.py`
- Modify: `tests/unit/smoke_base/test_smoke_criterion_probe.py`

- [ ] **Step 1: Read the three files and identify the duplicated code**

```bash
rg "_FakeNode|class _Crit" tests/unit/smoke_base/ -l
```

Read each file to extract the exact `_FakeNode` dataclass and `_Crit` subclass definitions.

- [ ] **Step 2: Write the shared conftest**

Create `tests/unit/smoke_base/conftest.py` with the shared `_FakeNode` dataclass and `_Crit` base subclass (copy the canonical version from one of the three files).

- [ ] **Step 3: Remove local definitions and import from conftest**

In each of the three test files, delete the local `_FakeNode` / `_Crit` definitions and replace with imports. Pytest automatically discovers `conftest.py` in the same directory, so no explicit import of fixtures is needed — but for plain helper classes, use a direct import:

```python
from tests.unit.smoke_base.conftest import _FakeNode, _Crit
```

- [ ] **Step 4: Run and verify**

```bash
uv run pytest tests/unit/smoke_base/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/smoke_base/
git commit -m "test(smoke_base): move shared _FakeNode and _Crit to conftest"
```

---

### Task 3: Deduplicate `_mock_runtime()` / `_ctx()` between swebench tests

**Files:**
- Create: `tests/integration/swebench_verified/conftest.py`
- Modify: `tests/integration/swebench_verified/test_criterion.py`
- Modify: `tests/unit/test_swebench_criterion_no_sandbox.py` (or wherever the unit-side copy lives — verify with `rg "_mock_runtime|def _ctx" tests/`)

- [ ] **Step 1: Confirm both definitions are identical**

```bash
rg -A 20 "def _mock_runtime\|def _ctx" tests/integration/swebench_verified/test_criterion.py
rg -A 20 "def _mock_runtime\|def _ctx" tests/unit/
```

If they differ, note the differences and produce a single merged version that satisfies both.

- [ ] **Step 2: Extract to integration conftest**

Create `tests/integration/swebench_verified/conftest.py`:

```python
# Shared helpers for swebench criterion tests.
# Also used by tests/unit/test_swebench_criterion_no_sandbox.py via direct import.
```

Move the canonical `_mock_runtime()` factory and `_ctx()` helper into this file.

- [ ] **Step 3: Update importers**

In both test files, remove the local definitions and import:

```python
from tests.integration.swebench_verified.conftest import _mock_runtime, _ctx
```

- [ ] **Step 4: Run both test files**

```bash
uv run pytest tests/integration/swebench_verified/test_criterion.py tests/unit/test_swebench_criterion_no_sandbox.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test(swebench): extract _mock_runtime/_ctx to shared conftest"
```

---

### Task 4: Move CLI test helpers to `tests/unit/cli/conftest.py`

**Files:**
- Create: `tests/unit/cli/conftest.py`
- Modify: `tests/unit/cli/test_benchmark_setup.py`

- [ ] **Step 1: Read the current helpers**

Read `tests/unit/cli/test_benchmark_setup.py` lines 12-59 to extract `_FakeBuildInfo` and `_patch_sdk()`.

- [ ] **Step 2: Create conftest with the helpers**

```python
# tests/unit/cli/conftest.py
import pytest
from unittest.mock import patch
# ... move _FakeBuildInfo and _patch_sdk() here verbatim
```

- [ ] **Step 3: Update the test file**

Remove the local definitions and import from conftest.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/cli/ -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/unit/cli/
git commit -m "test(cli): move _FakeBuildInfo and _patch_sdk to conftest"
```

---

## Category 2: Code Quality

### Task 5: Deduplicate `_Resp` mock class in `test_openrouter_budget.py`

**Files:**
- Modify: `tests/unit/test_openrouter_budget.py`

- [ ] **Step 1: Read the file and identify both `_Resp` definitions**

```bash
rg -n "_Resp\|_make_mock_response" tests/unit/test_openrouter_budget.py
```

- [ ] **Step 2: Replace with a module-level factory**

Remove the two inline class definitions and add at the top of the file:

```python
def _make_mock_response(exit_code: int, usage: dict | None = None):
    class _Resp:
        def __init__(self):
            self.exit_code = exit_code
            self.usage = usage or {}
    return _Resp()
```

Update each test function to call `_make_mock_response(exit_code=0)` etc.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/test_openrouter_budget.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_openrouter_budget.py
git commit -m "test(openrouter): extract _Resp to module-level factory"
```

---

### Task 6: Narrow bare `except Exception` in `tests/integration/conftest.py`

**Files:**
- Modify: `tests/integration/conftest.py`

- [ ] **Step 1: Read the current except clause (~line 62)**

Read `tests/integration/conftest.py` to find the broad except in `_reset_inngest_http_client`.

- [ ] **Step 2: Replace with specific exceptions**

Identify what can actually be raised when tearing down the HTTP client (e.g. `RuntimeError`, `asyncio.CancelledError`). Replace:

```python
except Exception:
    pass
```

with something like:

```python
except (RuntimeError, asyncio.CancelledError):
    pass  # client already closed or event loop torn down
```

Add an inline comment explaining why these are tolerated.

- [ ] **Step 3: Run integration tests (with infra available) or just run check:be**

```bash
pnpm run check:be
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/conftest.py
git commit -m "test(integration): narrow broad except in inngest client teardown"
```

---

### Task 7: Add missing `@pytest.mark.asyncio` in `test_worker_execute_factory_call.py`

**Files:**
- Modify: `tests/unit/runtime/test_worker_execute_factory_call.py`

- [ ] **Step 1: Read the file**

```bash
cat -n tests/unit/runtime/test_worker_execute_factory_call.py
```

- [ ] **Step 2: Add marker**

Add `@pytest.mark.asyncio` above any async test function missing it, or confirm the test is actually synchronous and clean up any async-looking patterns.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/runtime/test_worker_execute_factory_call.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/runtime/test_worker_execute_factory_call.py
git commit -m "test(runtime): add missing asyncio marker on worker execute test"
```

---

### Task 8: Fix fragile string matching in swebench integration criterion test

**Files:**
- Modify: `tests/integration/swebench_verified/test_criterion.py`

- [ ] **Step 1: Read the `_dispatch` inner function (~lines 60-68)**

Find where it does `"git diff HEAD" in cmd` or similar string matching.

- [ ] **Step 2: Replace with shlex-based argument parsing**

```python
import shlex

def _dispatch(cmd: str, **kwargs):
    parts = shlex.split(cmd)
    if parts[:3] == ["git", "diff", "HEAD"]:
        return _fake_diff_output()
    ...
```

This is robust to extra whitespace and argument order variations.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/integration/swebench_verified/test_criterion.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/swebench_verified/test_criterion.py
git commit -m "test(swebench): use shlex for robust command matching in _dispatch"
```

---

### Task 9: Fix mutable sequence state in `test_event_schema_phase0.py`

**Files:**
- Modify: `tests/unit/state/test_event_schema_phase0.py`

- [ ] **Step 1: Read the `_make_event()` function (~line 43)**

Identify the class-level `sequence` counter or mutable default that tests rely on.

- [ ] **Step 2: Make sequence a required positional argument**

```python
def _make_event(sequence: int, **kwargs):
    ...
```

Update all call sites to pass an explicit sequence integer.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_event_schema_phase0.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_event_schema_phase0.py
git commit -m "test(state): make sequence a required arg in _make_event to remove mutable default"
```

---

### Task 10: Clarify misleading docstring in `test_context_assembly.py`

**Files:**
- Modify: `tests/unit/state/test_context_assembly.py`

- [ ] **Step 1: Read lines 204-214**

Find the test that asserts `len(messages) == 0` with a comment about "not flushed because no response event".

- [ ] **Step 2: Rename and re-document the test**

Rename the test to something like `test_request_only_produces_no_assembled_messages` and update the docstring/comment to say the empty result is intentional behaviour (a request without a paired response yields no complete message).

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_context_assembly.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_context_assembly.py
git commit -m "test(state): clarify intent of zero-message assertion in context assembly"
```

---

## Category 3: Coverage Gaps

### Task 11: Add test for harness-enabled + missing secret header → 401

**Files:**
- Modify: `tests/unit/test_test_harness.py`

- [ ] **Step 1: Read the existing harness tests**

```bash
cat -n tests/unit/test_test_harness.py
```

Understand the existing 401 test to model the new one.

- [ ] **Step 2: Write the failing test first**

```python
def test_seed_requires_secret_when_harness_enabled(client_with_harness):
    """Requests without the secret header should be rejected 401 when harness is on."""
    resp = client_with_harness.post("/harness/seed", json={})
    assert resp.status_code == 401
```

Run it:

```bash
uv run pytest tests/unit/test_test_harness.py::test_seed_requires_secret_when_harness_enabled -v
```

Expected: FAIL (test not yet wired).

- [ ] **Step 3: Verify production code handles this case**

Check the harness route handler. If the 401 is already raised, the test will pass immediately — which means it was just missing coverage. If not, fix the route handler.

- [ ] **Step 4: Run the full file**

```bash
uv run pytest tests/unit/test_test_harness.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_test_harness.py
git commit -m "test(harness): add coverage for missing secret header when harness is enabled"
```

---

### Task 12: Add happy-path tests to `test_subtask_lifecycle_toolkit.py`

**Files:**
- Modify: `tests/unit/state/test_subtask_lifecycle_toolkit.py`

- [ ] **Step 1: Read the existing test file**

```bash
cat -n tests/unit/state/test_subtask_lifecycle_toolkit.py
```

Note which tools are tested (only error paths currently) and what the mock structure looks like.

- [ ] **Step 2: Write failing happy-path tests**

```python
async def test_add_subtask_succeeds_with_valid_args(mock_session):
    tool = build_subtask_lifecycle_tools(run_id=..., parent_node_id=..., sandbox_id=...)[0]
    result = await tool(
        task_slug="subq-1",
        description="Do the thing",
        assigned_worker_slug="researchrubrics-researcher",
    )
    assert result["success"] is True
    assert "node_id" in result


async def test_cancel_subtask_succeeds(mock_session):
    ...


async def test_refine_subtask_succeeds(mock_session):
    ...
```

(Adapt to the actual tool surface; read the toolkit to understand what `mock_session` needs to return.)

- [ ] **Step 3: Run tests to confirm they fail first, then pass after fixing mocks**

```bash
uv run pytest tests/unit/state/test_subtask_lifecycle_toolkit.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_subtask_lifecycle_toolkit.py
git commit -m "test(subtask-lifecycle): add happy-path coverage for add/cancel/refine"
```

---

### Task 13: Add test for cached sandbox early-return path

**Files:**
- Modify: `tests/unit/sandbox/test_ensure_sandbox_idempotence.py`

- [ ] **Step 1: Read the existing tests (~lines 59-104)**

Understand the mock structure for `get_sandbox()` and `create()`.

- [ ] **Step 2: Write failing test**

```python
def test_create_returns_cached_sandbox_without_install(monkeypatch):
    """If get_sandbox() already returns a sandbox, create() must not call install."""
    manager = SomeSandboxManager()
    fake_sandbox = object()
    monkeypatch.setattr(manager, "get_sandbox", lambda task_id: fake_sandbox)
    install_calls = []
    monkeypatch.setattr(manager, "_install", lambda *a, **kw: install_calls.append(1))

    result = manager.create(task_id=some_uuid)

    assert result is fake_sandbox
    assert install_calls == [], "install must not be called when sandbox already exists"
```

Run it, expect FAIL, then verify against the production code path.

- [ ] **Step 3: Run the full sandbox test suite**

```bash
uv run pytest tests/unit/sandbox/ -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/sandbox/test_ensure_sandbox_idempotence.py
git commit -m "test(sandbox): add coverage for cached sandbox early-return in create()"
```

---

### Task 14: Add evaluation-row assertion to `test_full_lifecycle.py`

**Files:**
- Modify: `tests/integration/test_full_lifecycle.py`

- [ ] **Step 1: Read the test (~lines 41-121)**

Find where it asserts run/task status and understand the DB session fixture.

- [ ] **Step 2: Add evaluation assertion**

After the existing completion assertions, add:

```python
from ergon_core.core.persistence.models import RunTaskEvaluation

evals = session.exec(
    select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run.id)
).all()
assert len(evals) > 0, "expected at least one evaluation row after full lifecycle"
```

- [ ] **Step 3: Run the integration test (requires running stack)**

```bash
uv run pytest tests/integration/test_full_lifecycle.py -v
```

If the stack is not available, add the assertion anyway and note it for CI.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_full_lifecycle.py
git commit -m "test(integration): assert evaluation rows exist after full lifecycle"
```

---

### Task 15: Add exit-code-127 variant to swebench criterion patch test

**Files:**
- Modify: `tests/unit/benchmarks/test_swebench_criterion_patch_source.py`

- [ ] **Step 1: Read the file and the `_fake_run()` helper (~lines 21-29)**

Understand what the current fake run does and how exit codes map to criterion outcomes.

- [ ] **Step 2: Write the failing test**

```python
def test_install_failure_exit_127_fails_criterion():
    """Install script exiting 127 (command not found) should fail the criterion."""
    def _fake_run_127(cmd: str, **kwargs):
        if "install" in cmd:
            return FakeRunResult(exit_code=127, stdout="", stderr="bash: command not found")
        return FakeRunResult(exit_code=0, stdout="", stderr="")

    criterion = SWEBenchCriterion(...)
    result = criterion.evaluate(..., run_command=_fake_run_127)
    assert result.passed is False
    assert "127" in result.message or "not found" in result.message.lower()
```

Adapt to the actual API from reading the file.

- [ ] **Step 3: Run test**

```bash
uv run pytest tests/unit/benchmarks/test_swebench_criterion_patch_source.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/benchmarks/test_swebench_criterion_patch_source.py
git commit -m "test(swebench-criterion): add coverage for install script exit 127"
```

---

## Category 4: Assertion Strength

### Task 16: Strengthen `test_type_invariants.py` status assertion

**Files:**
- Modify: `tests/unit/state/test_type_invariants.py`

- [ ] **Step 1: Read lines 29-40**

Find the test asserting `record.status == RunStatus.PENDING`.

- [ ] **Step 2: Split into two assertions**

```python
# Assert the field was set by the constructor, not a default
record = RunRecord(status=RunStatus.PENDING, ...)
assert record.status == RunStatus.PENDING  # explicitly set

# Assert the field survives a round-trip (not just an in-memory default)
roundtripped = RunRecord.model_validate(record.model_dump())
assert roundtripped.status == RunStatus.PENDING
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_type_invariants.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_type_invariants.py
git commit -m "test(state): strengthen RunRecord status assertion with explicit construction + round-trip check"
```

---

### Task 17: Add round-trip assertion in `test_event_schema_phase0.py`

**Files:**
- Modify: `tests/unit/state/test_event_schema_phase0.py`

- [ ] **Step 1: Read lines 20-35**

Find the tests that set and check `node_id`.

- [ ] **Step 2: Add `model_validate()` round-trip verification**

```python
raw = evt.model_dump()
roundtripped = EventSchema.model_validate(raw)
assert roundtripped.node_id == nid, "node_id must survive model_dump/model_validate round-trip"
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_event_schema_phase0.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_event_schema_phase0.py
git commit -m "test(state): add round-trip assertion for node_id in event schema test"
```

---

### Task 18: Assert on `type_slug` in `test_research_rubrics_benchmark.py`

**Files:**
- Modify: `tests/unit/state/test_research_rubrics_benchmark.py`

- [ ] **Step 1: Read lines 9-23**

Find the test checking `cls.__name__`.

- [ ] **Step 2: Replace `__name__` check with `type_slug` check**

```python
# Before:
assert cls.__name__ == "ResearchRubricsBenchmark"

# After:
assert "researchrubrics-ablated" in BENCHMARKS
assert BENCHMARKS["researchrubrics-ablated"] is ResearchRubricsBenchmark
```

This is more intent-revealing: we care that the slug resolves to the right class, not what Python named the class.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_research_rubrics_benchmark.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_research_rubrics_benchmark.py
git commit -m "test(registry): assert registry maps to correct class, not class __name__"
```

---

### Task 19: Assert build not called in `test_idempotent_skip()`

**Files:**
- Modify: `tests/unit/cli/test_benchmark_setup.py`

- [ ] **Step 1: Read lines 102-113**

Find `test_idempotent_skip()`.

- [ ] **Step 2: Add negative assertion**

After the `assert rc == 0`:

```python
fake.build.assert_not_called()
# OR if the mock structure is different:
assert mock_build.call_count == 0, "build must not be triggered on idempotent skip"
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/cli/test_benchmark_setup.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/cli/test_benchmark_setup.py
git commit -m "test(cli): assert build is not triggered on idempotent skip"
```

---

## Category 5: Performance

### Task 20: Guard smoke harness reset fixture against skipped tests

**Files:**
- Modify: `tests/integration/smokes/test_smoke_harness.py`

- [ ] **Step 1: Read the `_reset_before_each()` fixture (~lines 74-92)**

Understand what the HTTP reset call does and when it's skipped.

- [ ] **Step 2: Add a guard**

```python
@pytest.fixture(autouse=True)
def _reset_before_each(request):
    if request.node.get_closest_marker("skip"):
        return
    # ... existing HTTP reset logic
```

Alternatively, change `autouse=True` to explicit usage in tests that actually need the reset.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/integration/smokes/test_smoke_harness.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/smokes/test_smoke_harness.py
git commit -m "test(smoke-harness): skip DB reset fixture on skipped tests"
```

---

### Task 21: Promote message factories to module-scoped fixtures in `test_generation_turn_build.py`

**Files:**
- Modify: `tests/unit/state/test_generation_turn_build.py`

- [ ] **Step 1: Read lines 34-90**

Identify `_make_messages_text_only()` and `_make_messages_with_tool_call()` and whether any test mutates the returned objects.

- [ ] **Step 2: Convert to module-scoped fixtures if safe**

```python
@pytest.fixture(scope="module")
def messages_text_only():
    return _make_messages_text_only()


@pytest.fixture(scope="module")
def messages_with_tool_call():
    return _make_messages_with_tool_call()
```

Update test signatures to accept the fixtures. If any test mutates the list/objects, copy them first: `msgs = list(messages_text_only)`.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_generation_turn_build.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_generation_turn_build.py
git commit -m "test(state): promote message factories to module-scoped fixtures"
```

---

### Task 22: Parametrize slug-variant tests in `test_smoke_criterion_shape.py`

**Files:**
- Modify: `tests/unit/smoke_base/test_smoke_criterion_shape.py`

- [ ] **Step 1: Read lines 35-60**

Find the four test functions for missing/extra/renamed slug variants (e.g. `test_missing_slug_fails`, `test_extra_slug_fails`, `test_renamed_slug_fails`, `test_correct_slugs_pass`).

- [ ] **Step 2: Rewrite as parametrized test**

```python
@pytest.mark.parametrize("mutation,expected_pass", [
    (lambda slugs: slugs[:-1],          False),   # missing one slug
    (lambda slugs: slugs + ["extra"],   False),   # extra slug
    (lambda slugs: slugs[:1] + ["renamed"] + slugs[2:], False),  # renamed slug
    (lambda slugs: slugs,               True),    # correct — all slugs present
])
def test_smoke_criterion_slug_shape(mutation, expected_pass, fake_criterion):
    slugs = mutation(list(EXPECTED_SUBTASK_SLUGS))
    result = fake_criterion.evaluate(build_graph_with_slugs(slugs))
    assert result.passed is expected_pass
```

Adapt to the actual API from reading the file.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/smoke_base/test_smoke_criterion_shape.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/smoke_base/test_smoke_criterion_shape.py
git commit -m "test(smoke_base): parametrize slug shape tests to eliminate four-function repetition"
```

---

## Category 6: Isolation

### Task 23: Fix singleton state mutation race in `test_ensure_sandbox_idempotence.py`

**Files:**
- Modify: `tests/unit/sandbox/test_ensure_sandbox_idempotence.py`

- [ ] **Step 1: Read lines 35-56**

Find `_reset_sandbox_singleton()` with `autouse=True` and see which class attributes it mutates on `BaseSandboxManager` / `_ProbeManager`.

- [ ] **Step 2: Replace with `monkeypatch` per-test**

Remove the `autouse` fixture entirely. In each test that needs clean state, use `monkeypatch` to reset the class attribute:

```python
def test_create_is_idempotent(monkeypatch):
    monkeypatch.setattr(BaseSandboxManager, "_cache", {})
    monkeypatch.setattr(_ProbeManager, "_instance", None)
    # ... rest of test
```

`monkeypatch` is function-scoped by default and xdist-safe.

- [ ] **Step 3: Run with parallelism to verify no flakiness**

```bash
uv run pytest tests/unit/sandbox/ -n 4 -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/sandbox/test_ensure_sandbox_idempotence.py
git commit -m "test(sandbox): replace autouse singleton reset with per-test monkeypatch to fix xdist race"
```

---

### Task 24: Add missing `@pytest.mark.asyncio` in `test_subtask_lifecycle_toolkit.py`

**Files:**
- Modify: `tests/unit/state/test_subtask_lifecycle_toolkit.py`

- [ ] **Step 1: Read lines 30-60**

Identify all `async def test_*` functions missing the `@pytest.mark.asyncio` marker. (With `asyncio_mode = "auto"` in pyproject.toml this may be a no-op — verify the config first.)

```bash
grep "asyncio_mode" pyproject.toml
```

If `asyncio_mode = "auto"` is set, the marker is implicit and this task is already resolved — skip to commit with a note.

- [ ] **Step 2: Add explicit markers if not using auto mode**

```python
@pytest.mark.asyncio
async def test_cancel_with_invalid_uuid_returns_error():
    ...
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/state/test_subtask_lifecycle_toolkit.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/state/test_subtask_lifecycle_toolkit.py
git commit -m "test(subtask-lifecycle): add explicit asyncio markers (belt-and-suspenders with asyncio_mode=auto)"
```

---

### Task 25: Add run-level namespacing to `test_full_lifecycle_with_eval.py` DB polling

**Files:**
- Modify: `tests/integration/test_full_lifecycle_with_eval.py`

- [ ] **Step 1: Read lines 84-105**

Find the polling loop and the DB query that could race with `test_full_lifecycle.py`.

- [ ] **Step 2: Add a unique cohort or run_id prefix**

If the existing integration test fixtures don't already namespace by run, generate a unique `cohort` slug per test invocation:

```python
import uuid

@pytest.fixture
def unique_cohort():
    return f"test-{uuid.uuid4().hex[:8]}"
```

Use this cohort in all queries and run submissions within the test so results from parallel runs don't bleed across.

- [ ] **Step 3: Run both lifecycle tests together to verify no races**

```bash
uv run pytest tests/integration/test_full_lifecycle.py tests/integration/test_full_lifecycle_with_eval.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_full_lifecycle_with_eval.py
git commit -m "test(integration): namespace lifecycle-with-eval DB queries by unique cohort to prevent parallel-run races"
```
