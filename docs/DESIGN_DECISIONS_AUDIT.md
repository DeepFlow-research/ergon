# Design Decisions: Where to Add "Why" Comments

Target: ~15-25% comment density. Comments only where a future reader could break correctness, security, or cross-system coupling by "fixing" the code. No narration.

## Architectural comments (add once at origin, not per-file)

These decisions appear across many files. Document each ONCE at the pattern's origin.

### `api/benchmark.py` module docstring — add:
```
# Public API uses ABCs (not Protocols) for discoverability via isinstance,
# template-method helpers, and the HuggingFace "real classes" authoring feel.
# type_slug is ClassVar because it identifies the CLASS for registry lookup
# and definition persistence -- not a per-instance property.
```

### `runtime/events/base.py` on model_config — add:
```
# extra="allow" because Inngest injects _inngest metadata into event
# payloads. Without this, Pydantic rejects events at parse time.
```

### `arcane_builtins/registry.py` module docstring — add:
```
# Explicit dicts, no decorators or scanning. Adding a built-in =
# one import + one dict entry. Keeps registration discoverable
# and prevents action-at-a-distance via decorators.
```

### `api/evaluation_context.py` class docstring — add:
```
# Thin by design. Criteria own their data-pulling -- they connect
# to the sandbox via sandbox_id and pull what they need. The old
# pattern pre-collected resources, which broke agentic evaluators
# that need to explore freely.
```

## Inngest function comments (add per-function where values differ)

### `retries=0` on task-execute, worker-execute:
```
# retries=0: side effects (sandbox creation, model API calls, DB writes)
# would duplicate on retry. Failure propagates via TaskFailedEvent.
```

### `retries=1` on sandbox-setup, workflow-start:
```
# retries=1: idempotent operations (sandbox create is keyed, table init is IF NOT EXISTS).
```

### `Concurrency(limit=15)` on task-execute:
```
# Bounded by E2B sandbox quota and Postgres connection pool.
# 15 is conservative for local dev; production may increase.
```

### Deferred imports in execute_task.py (add ONCE, not per-import):
```
# Deferred: child function modules register with Inngest at import time.
# Eager cross-imports between registered modules cause circular imports.
```

## Persistence comments (add once per pattern)

### `definitions/models.py` above first JSON accessor — add:
```
# JSON accessor pattern: parsed_*() returns typed model, _parse_*()
# classmethod for reuse, @model_validator for fail-fast at row load time.
# Core code never reads raw dict from a JSON column.
```

### `persistence/shared/enums.py` — add:
```
# StrEnum: DB columns store string literals. StrEnum gives both
# Python type safety and Postgres VARCHAR/JSON compatibility.
```

### `experiment_persistence_service.py` on persist_definition — add:
```
# Identity-not-serialization: rows store type slugs + model_target,
# not serialized Python constructor state. Runtime reconstructs
# fresh objects from registry + identity fields. snapshot_json is
# write-once audit data -- nothing reconstructs from it.
```

## Runtime comments (add where future "fix" would break things)

### `sandbox_setup.py` on SANDBOX_MANAGERS.get():
```
# Resolved on demand from registry by benchmark_type (already in
# payload and definition row). No pre-registration, no new column.
# Benchmarks not in SANDBOX_MANAGERS get DefaultSandboxManager.
```

### `inngest_client.py` on PydanticSerializer:
```
# PydanticSerializer enables typed output_type on create_function.
# Without it, Inngest can't serialize/deserialize Pydantic BaseModel
# returns from step.run/step.invoke, causing "unserializable" errors.
```

### `api/experiment.py` on deferred persist/run imports:
```
# Deferred: api/ should not depend on core/ at module level.
# These are the only api->core imports. Extracting to a composition
# layer is flagged for v2.
```

## Bugs to fix (found during audit)

1. **`workflow_initialization_service.py`**: `total_leaf_tasks` counts tasks with `parent_task_id is None` — these are ROOTS not leaves. Rename to `total_root_tasks` or fix the logic.

2. **`api/handles.py`**: Uses `datetime.utcnow` (deprecated in Python 3.12+). Replace with `h_arcane.core.utils.utcnow` for consistency.

3. **`persistence/shared/db.py`**: Verify `get_engine()` is cached (lru_cache or module-level singleton). Creating a new engine per call exhausts connection pools.

## What NOT to comment

- `model_config = {"frozen": True}` — established Pydantic pattern, self-explanatory after the first occurrence
- `Field(default_factory=list)` — standard Pydantic
- `ClassVar[str]` after the first explanation on `Benchmark`
- `async def execute(...)` — the signature IS the documentation
- Any comment that restates the next line of code
