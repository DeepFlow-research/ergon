# Structural Correctness Checks

## Beyond the Nine Flows: Additional Bulletproofing Categories

The nine control flows are about *runtime correctness* — does the system reach the right Postgres state after events settle? The categories below protect a different surface: *structural correctness* — does the codebase wire things up consistently in the first place? Some of these are best placed in the unit tier (no infra required), but they belong in the same TDD mandate.

---

### 10. Event Pub→Sub Call Graph (static analysis — unit tier)

**Problem:** A simple "every event name has a handler" check is one-directional. It catches orphaned event types (defined but nothing subscribes), but misses two equally dangerous failure modes:

1. **Dead handlers** — a handler is registered in `ALL_FUNCTIONS` but nothing in the codebase ever emits the event it listens for. The handler is live but unreachable.
2. **Missing fan-out** — an event should trigger multiple handlers (Inngest supports N subscribers per event), but one is missing from `ALL_FUNCTIONS`. Publisher and one subscriber are fine; the second subscriber is silently absent.

The fix is a bidirectional call graph: map every event to its expected publishers and expected subscribers, then assert both sides.

**How to build the graph:**

The subscriber side is trivially introspectable — `ALL_FUNCTIONS` is the source of truth:

```python
from ergon_core.core.runtime.inngest_registry import ALL_FUNCTIONS

def build_subscriber_map() -> dict[str, list[str]]:
    """event_name → [handler_id, ...]"""
    result: dict[str, list[str]] = {}
    for fn in ALL_FUNCTIONS:
        event = fn.trigger.event
        result.setdefault(event, []).append(fn.id)
    return result
```

The publisher side cannot be introspected automatically without AST analysis, so it is declared explicitly as a canonical fixture. This has a secondary benefit: the fixture **is the architecture document** for the event graph. Anyone reading it can trace the full flow.

```python
# tests/unit/state/test_event_call_graph.py

# Canonical pub→sub map. Each entry states:
#   publishers: which Inngest function IDs emit this event (or "external" for CLI/API entrypoints)
#   subscribers: which Inngest function IDs must handle it
EXPECTED_CALL_GRAPH: dict[str, dict[str, list[str]]] = {
    "benchmark/run-request": {
        "publishers": ["external:cli"],
        "subscribers": ["benchmark-run-start"],
    },
    "workflow/started": {
        "publishers": ["benchmark-run-start"],
        "subscribers": ["start-workflow"],
    },
    "task/ready": {
        # emitted by start-workflow (initial roots), by propagate-execution (after
        # dep satisfied), and by execute-task (when plan_subtasks inserts new roots)
        "publishers": ["start-workflow", "propagate-execution", "execute-task"],
        "subscribers": ["execute-task"],
    },
    "task/completed": {
        "publishers": ["execute-task"],
        "subscribers": ["propagate-execution"],
    },
    "task/failed": {
        "publishers": ["execute-task"],
        "subscribers": ["propagate-execution"],
    },
    "task/cancelled": {
        "publishers": ["propagate-execution", "cancel-orphans"],
        "subscribers": ["cancel-orphans"],
    },
    "workflow/completed": {
        "publishers": ["propagate-execution"],
        "subscribers": ["complete-workflow"],
    },
    "workflow/failed": {
        "publishers": ["propagate-execution"],
        "subscribers": ["fail-workflow"],
    },
    "run/cancelled": {
        "publishers": ["external:api"],
        "subscribers": ["cancel-run"],
    },
    "run/cleanup": {
        "publishers": ["complete-workflow", "fail-workflow"],
        "subscribers": ["cleanup-run"],
    },
    # criterion/evaluate: publishers unknown, subscribers MISSING — this is the live bug
    # this entry must be completed and a handler added before this test can pass
    "criterion/evaluate": {
        "publishers": [],   # TODO: identify where this is emitted
        "subscribers": [],  # BUG: no handler registered in ALL_FUNCTIONS
    },
}
```

**Three assertions from one fixture:**

```python
def test_every_declared_subscriber_is_registered():
    """All expected subscribers exist in ALL_FUNCTIONS."""
    registered = {fn.id for fn in ALL_FUNCTIONS}
    for event, graph in EXPECTED_CALL_GRAPH.items():
        for expected_sub in graph["subscribers"]:
            assert expected_sub in registered, (
                f"Event '{event}' expects handler '{expected_sub}' "
                f"but it is not in ALL_FUNCTIONS"
            )

def test_no_registered_handler_is_absent_from_call_graph():
    """Every handler in ALL_FUNCTIONS appears as a subscriber somewhere in the graph.
    A handler that appears in no event's subscriber list is unreachable dead code."""
    declared_subs = {s for g in EXPECTED_CALL_GRAPH.values() for s in g["subscribers"]}
    for fn in ALL_FUNCTIONS:
        assert fn.id in declared_subs, (
            f"Handler '{fn.id}' is registered in ALL_FUNCTIONS but does not appear "
            f"in EXPECTED_CALL_GRAPH — either add it or remove the handler"
        )

def test_every_declared_event_type_has_a_model_class():
    """Every event slug in the call graph has a corresponding Pydantic event model.
    Catches typos in the fixture and models that were deleted without updating the graph."""
    from ergon_core.core.runtime.events import all_event_models  # hypothetical collector
    known_slugs = {m.model_fields["name"].default for m in all_event_models()}
    for event in EXPECTED_CALL_GRAPH:
        assert event in known_slugs, (
            f"Event '{event}' in call graph has no corresponding event model class"
        )
```

**What this catches that the original one-liner missed:**

| Failure mode | Simple slug check | Call graph |
|---|---|---|
| Event defined, no handler | ✅ | ✅ |
| Handler registered, nothing emits to it | ❌ | ✅ |
| Event should fan out to N handlers, only N-1 registered | ❌ | ✅ |
| Event slug in graph but no Pydantic model class | ❌ | ✅ |
| Handler slug typo in `ALL_FUNCTIONS` | ❌ | ✅ |

**Concrete live example — `criterion/evaluate`:** The fixture above documents the bug explicitly. The test `test_every_declared_subscriber_is_registered` will fail on the `criterion/evaluate` entry the moment a subscriber is declared in the fixture but absent from `ALL_FUNCTIONS`. Until the fixture entry has a non-empty `subscribers` list AND a matching registered handler, the bug is recorded but the test doesn't crash the suite — which is the right behaviour during a fix. Add the handler, update the fixture, the test goes green.

---

### 11. Inngest Function Catalog Integrity (static analysis — unit tier)

**Problem:** `ALL_FUNCTIONS` could have duplicate slugs (two functions with the same name) or functions with no trigger at all. Inngest silently accepts duplicate registrations and last-write-wins, meaning one handler silently shadows another.

**What to test:**

```python
def test_no_duplicate_inngest_slugs():
    slugs = [fn.id for fn in inngest_registry.ALL_FUNCTIONS]
    assert len(slugs) == len(set(slugs)), f"Duplicate slugs: {[s for s in slugs if slugs.count(s) > 1]}"

def test_all_inngest_functions_have_event_trigger():
    for fn in inngest_registry.ALL_FUNCTIONS:
        assert hasattr(fn.trigger, "event"), f"{fn.id} has no event trigger"
```

---

### 12. Registry Integrity (static analysis — unit tier)

**Problem:** A slug can be registered in `BENCHMARKS`, `WORKERS`, `EVALUATORS`, or `CRITERIA` that points to a class that cannot be instantiated — wrong base class, missing required class vars, or import error at collection time.

**What to test:** For each registry (`CORE_BENCHMARKS`, `WORKERS`, etc.), assert that every value is a class, that it is a subclass of the correct ABC, and that it can be constructed with minimal arguments (or at least that `__init__` doesn't immediately raise on a no-arg call where no args are required). The `onboarding_deps` benchmark contract in `test_benchmark_contract.py` is a partial model for this; extend the pattern to all registries.

```python
@pytest.mark.parametrize("slug,cls", list(CORE_BENCHMARKS.items()))
def test_benchmark_registry_entries_are_valid_subclasses(slug, cls):
    assert issubclass(cls, Benchmark), f"{slug} is not a Benchmark subclass"
    assert hasattr(cls, "type_slug"), f"{slug} missing type_slug"
```

---

### 13. Event Payload Round-Trips (static analysis — unit tier)

**Problem:** All Inngest events are Pydantic models. A broken `model_dump()` / `model_validate()` cycle (e.g. a UUID field that serialises to a non-string in one environment) means events cannot be deserialized by the Inngest dev server or the handler.

**What to test:** For every concrete event class defined in `task_events.py`, `evaluation_events.py`, and `infrastructure_events.py`, construct a minimal valid instance, round-trip it through `model_dump()` + `model_validate()`, and assert equality. Use `mode="json"` on `model_dump` to catch UUID/datetime serialisation issues that only surface over the wire.

```python
@pytest.mark.parametrize("event_cls,kwargs", [
    (TaskReadyEvent, {"run_id": uuid4(), "node_id": uuid4(), ...}),
    ...
])
def test_event_round_trips(event_cls, kwargs):
    original = event_cls(**kwargs)
    payload = original.model_dump(mode="json")
    restored = event_cls.model_validate(payload)
    assert original == restored
```

---

### 14. Toolkit Tool Name Uniqueness (static analysis — unit tier)

**Problem:** The Inngest worker toolkit is assembled by combining tool lists from different providers. If two providers define a tool with the same `__name__`, the second silently shadows the first at the model-context level — the LLM sees duplicate names and the worker may call the wrong function.

**What to test:** For each registered worker class, instantiate its toolkit (with a mock sandbox/runtime) and assert that all tool `__name__` values within that toolkit are unique.

```python
def test_swebench_toolkit_tool_names_are_unique():
    tools = build_swebench_toolkit(sandbox=MockSandbox(), runtime=MockRuntime())
    names = [t.__name__ for t in tools]
    assert len(names) == len(set(names)), f"Duplicate tool names: {set(n for n in names if names.count(n) > 1)}"
```

---

### 15. Worker / Benchmark / Evaluator ABC Compliance (static analysis — unit tier)

**Problem:** Every concrete worker, benchmark, and evaluator must implement specific abstract methods. Python's ABC machinery only raises at *instantiation time*, not at import/collection time. A class that forgets to implement `execute()` passes all static checks until someone tries to run it.

**What to test:** Attempt instantiation of every registered concrete class (with minimal stub arguments) and assert no `TypeError` is raised for missing abstract methods. This goes one step beyond the subclass check in category 12.

```python
@pytest.mark.parametrize("slug,cls", list(WORKERS.items()))
def test_worker_is_fully_concrete(slug, cls):
    # Should not raise TypeError: Can't instantiate abstract class
    try:
        instance = cls.__new__(cls)
    except TypeError as e:
        pytest.fail(f"Worker '{slug}' is not fully concrete: {e}")
```

---

### 16. DB Schema Reflection (Postgres only — integration tier, no Inngest)

**Problem:** SQLModel generates table DDL from Python models. If a migration is applied in the wrong order or skipped, the live Postgres schema diverges from the models. This silently breaks writes to new columns or reads of renamed columns.

**What to test:** Connect to the Postgres instance, reflect every table that `SQLModel.metadata` knows about, and assert that every column on every model exists in the reflected schema with the correct type and nullability. This test needs Postgres but not Inngest, so it should be gated separately from the event-flow tests.

```python
def test_db_schema_matches_models(postgres_engine):
    from sqlalchemy import inspect
    inspector = inspect(postgres_engine)
    for table_name, table in SQLModel.metadata.tables.items():
        reflected_cols = {c["name"] for c in inspector.get_columns(table_name)}
        model_cols = {c.name for c in table.columns}
        assert model_cols <= reflected_cols, (
            f"Table '{table_name}' missing columns: {model_cols - reflected_cols}"
        )
```

---

### 17. Sandbox Container Builds (Docker — slow tier)

**Problem:** Each benchmark sandbox is built from a `Dockerfile` in the repo. A broken base image pin, a removed system package, or a pip install that fails silently produces a container that appears to build but crashes at runtime. This is only caught when someone actually tries to run a benchmark.

**Two Dockerfiles to test:**
- `ergon_builtins/benchmarks/minif2f/Dockerfile` (Lean4 toolchain)
- `ergon_builtins/benchmarks/swebench_verified/Dockerfile` (Python dev environment)

**What to test:** A `docker build` that must exit zero. These are slow (minutes each) and should be gated behind a `pytest.mark.docker_build` marker so they run in CI nightly but not on every PR push. A basic smoke: build succeeds, `docker run --rm <image> echo ok` exits zero.

```python
@pytest.mark.docker_build
@pytest.mark.parametrize("dockerfile_path,context_dir", [
    ("ergon_builtins/benchmarks/minif2f/Dockerfile", "ergon_builtins/benchmarks/minif2f/"),
    ("ergon_builtins/benchmarks/swebench_verified/Dockerfile", "ergon_builtins/benchmarks/swebench_verified/"),
])
def test_sandbox_container_builds(dockerfile_path, context_dir, tmp_path):
    result = subprocess.run(
        ["docker", "build", "-f", dockerfile_path, "-t", f"ergon-test-{tmp_path.name}", context_dir],
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, f"Docker build failed:\n{result.stderr}"
```

---

### 18. Concurrency Race: `only_if_not_terminal` Under Concurrent Cancellation (full-stack integration)

**Problem:** The `only_if_not_terminal` guard is the single mechanism preventing double-writes on a terminal node. If two `task/cancelled` events race to update the same node (which happens in diamond DAG failure cascades where multiple parents can independently trigger cancellation), one write must win and the other must be silently discarded. If the guard has a bug, the WAL gets a spurious second mutation and downstream assertions about node count and status are corrupted.

This is the hardest test to write and the one most likely to catch real bugs. It requires the full Inngest + Postgres stack.

**What to test:** Construct a DAG where a single leaf node has two parents, and both parents fail at approximately the same time. The leaf should receive two independent `task/cancelled` events nearly simultaneously. Assert:

- The leaf has exactly one `CANCELLED` `RunGraphNode` row
- The WAL for the leaf has exactly one `CANCELLED` mutation (no duplicate entries)
- The `RunRecord` reaches `FAILED` (not stuck)
- The `RunTaskExecution` for the leaf (if any was started) has a single terminal row

This test should be marked `pytest.mark.slow` and `pytest.mark.flaky_risk` with a note that it is exercising a race condition — it should be run with `--count=5` (using `pytest-repeat`) in CI to increase the chance of hitting the race.

---

## Priority Order

The current `tests/integration/` has one real integration test that checks HTTP response codes on a narrow happy path. The nine critical control flows above — propagation, failure cascade, subtask spawning, cancellation, restart, communication — have never had their Postgres state asserted at any tier.

The Postgres state after any interesting event sequence is the system's ground truth. That is what the integration tier should be testing.

The nine additional categories above protect structural correctness: events that are defined but never handled, duplicate tool names, schema drift, and concurrency races. Several of these (categories 10–15) are pure static analysis and belong in the unit tier — they require no running infrastructure and can fail fast in CI. Category 16 needs Postgres but not Inngest. Category 17 needs Docker and should run nightly. Category 18 needs the full stack and should run on every feature branch.

**Priority order for implementation:**

| Priority | Category | Tier | Value |
|----------|----------|------|-------|
| 1 | Fix 3 uncollected tests (`testresolve_*`) | Integration | Critical bug — tests have never run |
| 2 | Event subscriber coverage | Unit | Catches live `criterion/evaluate` orphan |
| 3 | Nine control flows | Integration | Core runtime correctness, zero coverage today |
| 4 | Inngest catalog + registry integrity | Unit | Cheap, high signal |
| 5 | DB schema reflection | Integration | Catches migration drift |
| 6 | Event payload round-trips | Unit | Catches serialisation bugs before they hit wire |
| 7 | Toolkit tool name uniqueness | Unit | Prevents silent shadowing |
| 8 | ABC compliance | Unit | Catches broken registrations at test time |
| 9 | Concurrency race | Full-stack | Validates the system's critical idempotency guard |
| 10 | Container builds | Docker/nightly | Catches broken sandbox images before E2E |
