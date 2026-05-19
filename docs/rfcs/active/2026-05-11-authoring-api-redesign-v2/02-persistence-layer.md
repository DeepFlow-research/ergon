# 02 — Persistence and identity

> How the typed objects from [`01-api-surface.md`](01-api-surface.md) move
> between Python and Postgres, how the runtime reconstructs them, and the
> two-table identity model that underpins both static tasks and dynamic
> spawning. See [`03-runtime.md`](03-runtime.md) for what the rollout
> container does with the result and
> [`04-walkthrough.md`](04-walkthrough.md) for the concrete trace.

> **What v2 changed.** The §3–§5 sections (two-tier persistence layout,
> read boundary, dynamic-subtask shape) are new in v2 and lock in the
> audit findings from
> [`../2026-05-08-authoring-api-redesign/08-cleanup-audit.md`](../2026-05-08-authoring-api-redesign/08-cleanup-audit.md).
> §1 (`from_definition` convention) and §2 (two-table identity model)
> are carried forward unchanged. Sections marked `[v2: added]` are new;
> everything else is the v1 design intent that holds up.

## Persistence: typed repos at the boundary, `from_definition` on the class

The job body should never deserialize an authoring class directly. Two
project conventions converge on this:

1. **Reads from Postgres go through a typed repository.** That convention
   already exists in tree (`DefinitionRepository.task_with_instance`,
   etc.). The repository owns the SQLModel session, returns typed row
   objects, and is the only layer that touches `session.get`.
2. **Class reconstruction lives on the class.** The
   `import_component_string + model_validate` dance (which every
   serializable authoring class needs) is framework infrastructure, not
   job-body logic. Each authoring class exposes a `from_definition`
   classmethod that owns it.

```python
# In ergon_core.api — base classes carry the convention:

from pydantic import JsonValue


type TaskDefinitionJson = dict[str, JsonValue]
"""Serialized form of a Task/Worker/Sandbox/etc — `_type`-discriminated
JSON written to `run_graph_nodes.task_json` and the matching definition
columns. Field names are NOT enforced by the type (the discriminator
dispatch in `from_definition` does that). The value side IS typed via
pydantic's `JsonValue`, so sticking a `datetime` or `UUID` object into
the snapshot fails at typecheck time instead of at JSON-serialization
time. The alias is the named boundary every `from_definition`
classmethod accepts."""


class Worker(BaseModel, ABC):
    @classmethod
    def from_definition(cls, worker_json: TaskDefinitionJson) -> "Worker":
        """Reconstruct a concrete Worker subclass from its persisted JSON.
        Discovers the subclass via the `_type` discriminator. Raises
        `ValueError` if `_type` is missing or non-string — there is no
        soft-default to a base class, because doing so would silently
        produce the wrong Worker subclass at runtime."""
        worker_type = worker_json.get("_type")
        if not isinstance(worker_type, str):
            raise ValueError(
                f"Worker snapshot is missing the required `_type` "
                f"discriminator (got {type(worker_type).__name__})."
            )
        WorkerCls = import_component_string(worker_type)
        return WorkerCls.model_validate(worker_json)

class Task(BaseModel, Generic[PayloadT]):
    # Persisted direct bindings. Worker/evaluator/sandbox objects all
    # round-trip through their own `_type` discriminators inside task_json.
    worker: Worker
    sandbox: Sandbox
    evaluators: tuple[Evaluator, ...] = ()

    # Runtime-only state. Not in JSON; populated by `from_definition` below.
    # The public accessor (`task.task_id`) lives on the class itself and is
    # defined in 01-api-surface.md.
    _task_id: UUID | None = PrivateAttr(default=None)

    @classmethod
    def from_definition(
        cls,
        task_json: TaskDefinitionJson,
        *,
        task_id: UUID,
    ) -> "Task":
        """Reconstruct a Task fully inflated for runtime use. Combines
        the two concerns the framework never wants separately:

        1. Deserialize the persisted JSON via the `_type` discriminator.
        2. Bind the per-run identity (`_task_id`).

        Framework-internal: only the graph repository calls this (see
        `RunGraphNodeView` below). Author code constructs `Task(...)`
        directly and never touches `from_definition`.

        Raises `ValueError` if `_type` is missing or non-string — there
        is no soft-default to base `Task`, because doing so would
        silently drop the authored worker/sandbox/evaluator bindings.
        """
        task_type = task_json.get("_type")
        if not isinstance(task_type, str):
            raise ValueError(
                f"Task snapshot is missing the required `_type` "
                f"discriminator (got {type(task_type).__name__})."
            )
        TaskCls = import_component_string(task_type)
        instance = TaskCls.model_validate(task_json)
        # PrivateAttr on a non-frozen BaseModel is settable directly;
        # object.__setattr__ kept for symmetry with frozen-Sandbox patterns.
        object.__setattr__(instance, "_task_id", task_id)
        return instance

class Sandbox(BaseModel, ABC):
    @classmethod
    def from_definition(cls, sandbox_json: TaskDefinitionJson) -> "Sandbox":
        sandbox_type = sandbox_json.get("_type")
        if not isinstance(sandbox_type, str):
            raise ValueError(
                f"Sandbox snapshot is missing the required `_type` "
                f"discriminator (got {type(sandbox_type).__name__})."
            )
        SandboxCls = import_component_string(sandbox_type)
        return SandboxCls.model_validate(sandbox_json)

# Same shape on Criterion, Rubric, Benchmark.
```

`from_definition` takes a `TaskDefinitionJson` (the JSON from the row),
**not** the typed row itself — that would create an `api → persistence`
dependency in the wrong direction. It should not take a
worker/evaluator pool: those objects are part of `Task` itself now. The
guideline: after `from_definition`, no field on the returned object
should still be a "go look this up over there" reference.

The boundary type is `dict[str, JsonValue]`, not a Pydantic model and
not a `TypedDict`. The shape *after* discriminator dispatch lives on
the concrete subclass; mirroring it in a parallel typed structure
would duplicate the schema and rot. The boundary type asserts only
what's honest at the boundary: "JSON, value-side typed, shape TBD by
the discriminator."

There is **no `_materialize` classmethod** on `Task` (or any other
class). `from_definition` is the single framework-internal entry
point that goes from "raw JSON + resolution context" to "fully usable
runtime instance." This avoids the two-step `model_validate` →
`_materialize` shape an earlier draft had, where it was unclear which
method owned identity binding.

The job body shouldn't see a `TaskDefinitionJson` either — the repo is
the bridge, and it returns *fully inflated typed objects*, never raw JSON.
The graph repo returns a typed `RunGraphNodeView` with the `Task` already
inflated:

```python
class RunGraphNodeView(BaseModel):
    """Typed view of one run_graph_nodes row + its inflated Task."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    run_id: UUID
    task_id: UUID
    parent_task_id: UUID | None
    status: NodeStatus
    task: Task                              # already inflated by from_definition
    # ...other row fields
```

Pydantic (frozen) rather than `@dataclass(frozen=True)` for project
consistency: every typed object the repo emits is a `BaseModel`, including
the inflated `Task` it wraps. The view itself never round-trips through
JSON (it's a runtime read result, not a persisted shape), so the choice is
about uniform construction/validation ergonomics with its `Task` payload,
not serialization.

The job body becomes orchestration only — typed objects throughout, no
dicts visible:

```python
node = graph_repo.node(session, run_id=payload.run_id,
                                task_id=payload.task_id)

task = node.task
worker = task.worker
# task.evaluators is already a typed tuple because it lives in task_json.
```

`Task.from_definition` is called *once*, *inside* `graph_repo.node(...)`,
and never appears in the job body. It's a framework-internal classmethod
(authors construct via `Task(...)`, not via `from_definition`) — the
`TaskDefinitionJson` parameter is honest about being the typing boundary
between PG's untyped JSON column and the typed authoring hierarchy, and
that boundary lives entirely inside the repo. No `session.get` in sight;
no `import_component_string` in sight; no binding-key chase at the
iteration site (downstream code reads `node.task.worker` and
`node.task.evaluators` as typed objects); no static/dynamic branching.
The two infrastructure concerns —
*how do I fetch this from PG?* and *how do I rebuild this object from
JSON?* — each have one canonical home, and each authoring class is
reconstructed at most once per job.

## Identifier model: two tables, one identity

The runtime separates *what was authored* from *what is happening*, and
treats `task_id` as a single stable identity that flows from the first
table to the second.

### Two-table split

| Table | Mutability | Holds | Lifetime |
|---|---|---|---|
| `experiment_definition_tasks` | **immutable** after experiment-define | `task_json` (including task worker, sandbox, evaluators) + dependencies | written once at experiment-define; never mutated |
| `run_graph_nodes` | **mutable** during a run | per-run task state + inline `task_json` snapshot | populated by copy at run-launch; grown by the runtime as workers spawn dynamic children; settled as tasks complete |

**Definitions never change after the experiment is defined.** Runs are
independent snapshots, fully self-contained on `run_graph_nodes` after
launch — definition mutations (if we ever allowed any) cannot affect
in-flight runs because the run carries its own copy.

### Identity preservation: `task_id` is the single canonical id

`task_id` is born exactly once — at experiment-define time for static
tasks, at spawn time for dynamic tasks — and the same value flows
unchanged through the entire pipeline:

```
                    ┌─ static tasks ─────────────────────────────┐
                    │                                            │
ExperimentDefinitionTask.id   →   run_graph_nodes.task_id        │
                                  (literal copy at run-launch)   │
                                                                 │
                    ┌─ dynamic tasks ────────────────────────────┤
                    │                                            │
            uuid4() at spawn   →   run_graph_nodes.task_id       │
                                  (no definition row exists)     │
                                                                 │
            task.task_id (PrivateAttr) ─────────────────────────→┘
            (Same value, set by Task.from_definition.)
```

`(run_id, task_id)` is the **composite primary key** of
`run_graph_nodes`. Edges, executions, and any other rows that point at a
node use composite FKs into `(run_id, task_id)`. The same `task_id` value
recurs across N runs of the same definition — uniqued per row by `run_id`.

| Layer | Identifier | Born at | Cardinality |
|---|---|---|---|
| Experiment | `definition_id` (`experiment_definitions.id`) | experiment-define | 1 per defined experiment |
| Task | `task_id` | experiment-define (static) OR spawn (dynamic) | N per definition; reused once per run |
| Run | `run_id` (`runs.id`) | run-launch | 1 per invocation |
| Per-run task | `(run_id, task_id)` | run-launch (static) OR spawn (dynamic) | composite PK on `run_graph_nodes` |
| Per-attempt | `execution_id` | first attempt + each retry | N per `(run_id, task_id)` |

### What this kills

- **`definition_task_id` as a separate column.** It existed because
  `run_graph_nodes.id` was a freshly-generated UUID per row, distinct from
  the definition row's `id`. Now `task_id` *is* the definition's id (for
  static tasks); no separate FK column needed. The discriminator for
  "static vs. dynamic" is `parent_task_id IS NULL` *or* whether a row in
  `experiment_definition_tasks` exists with this id — both are O(1) checks.
- **`node_id`.** Was the runtime per-row UUID. The composite
  `(run_id, task_id)` does its job; nothing references it anymore.
- **The "definition vs. runtime task identity" mental model.** There's
  one task identity, full stop. It just lives in two places (the
  immutable definition row, and the mutable per-run row that copied it).

### Impact

- **Authors** never write any IDs.
- **Worker / criterion code** reads `task.task_id` (and `context.execution_id`
  for retries). The value is the *same* UUID the definition row has — no
  conceptual jump between layers.
- **Runtime / persistence code** uses `(run_id, task_id)` as the canonical
  row key. Cross-run analytics ("how did `<task_id>` perform across all
  runs?") is `WHERE task_id = X`; per-run lookup ("what's task X doing in
  run Y?") is `WHERE (run_id, task_id) = (Y, X)`. Both natural.

## §3 — Two-tier persistence layout `[v2: added]`

v1 carried three persistence tiers — `ExperimentRecord` (telemetry /
authoring metadata), `ExperimentDefinition` (immutable definition),
`RunGraphNode` (mutable run state). The audit
([`../2026-05-08-authoring-api-redesign/08-cleanup-audit.md`](../2026-05-08-authoring-api-redesign/08-cleanup-audit.md))
found `ExperimentRecord` was a thin wrapper around `ExperimentDefinition`
that duplicated authoring fields and added no behavior. v2 collapses it.

### The two tiers

| Tier | Tables | Lifetime | Mutability |
|---|---|---|---|
| **Definition tier** | `experiment_definitions`, `experiment_definition_tasks`, `experiment_definition_edges` | Born once at `persist_definition`; one row per defined experiment | Immutable after write |
| **Run tier** | `runs`, `run_graph_nodes`, `run_graph_edges`, `run_graph_annotations`, `run_graph_mutations`, `task_executions` | Born at `launch_run`; mutable for the lifetime of the run; settled when run completes | Mutable |

`run_graph_annotations` and `run_graph_mutations` together form the WAL
that keeps the live run-graph reconstructable from any point in time
(see v1's design discussion — unchanged).

### `experiment_definitions` columns (collapsed)

The columns formerly split across `ExperimentRecord` and
`ExperimentDefinition` collapse onto `experiment_definitions`:

```sql
CREATE TABLE experiment_definitions (
    id              UUID PRIMARY KEY,                    -- definition_id
    -- Authoring metadata (was ExperimentRecord) ↓
    name            TEXT NOT NULL,
    description     TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT,                                -- user / agent who defined
    -- Definition payload (was ExperimentDefinition) ↓
    benchmark_json  JSONB NOT NULL,                      -- _type-discriminated Benchmark
    experiment_json JSONB NOT NULL                       -- _type-discriminated Experiment frame
);
```

Authoring metadata moves directly onto `Experiment`:

```python
class Experiment(BaseModel):
    benchmark: Benchmark
    name: str | None = None
    description: str | None = None
    metadata: Mapping[str, Any] = Field(default_factory=dict)
    # ... validator unchanged from 01-api-surface.md
```

`name` / `description` / `metadata` round-trip through `experiment_json`
*and* are denormalized into dedicated columns for indexable lookup
(`SELECT id FROM experiment_definitions WHERE name = ...` should not
require JSON path queries).

### `runs` columns

```sql
CREATE TABLE runs (
    id              UUID PRIMARY KEY,                    -- run_id
    definition_id   UUID NOT NULL REFERENCES experiment_definitions(id),
    status          run_status NOT NULL,                 -- enum: pending, running, succeeded, failed, cancelled
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    -- Telemetry per run (was on ExperimentRecord, moves to run-scope) ↓
    triggered_by    TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb   -- per-run overrides, tags
);
```

Run-scoped telemetry (who triggered, when started, completion timestamp)
lives on `runs`, not on `experiment_definitions`. The collapse is only
about `ExperimentRecord` — `Run`-tier telemetry stays where it was.

### What this kills

In addition to the v1 deletions in §2 "What this kills":

- **`ExperimentRecord` table.** Folded into `experiment_definitions`.
- **`experiment_record_id` FKs anywhere they appeared.** Replaced by
  `definition_id`.
- **The `ExperimentService.create_experiment_record()` step in the
  authoring path.** Becomes a single `persist_definition(experiment)`.

### Why the collapse is safe

`ExperimentRecord` was only ever populated by `persist_definition`, only
ever read by `launch_run` and the dashboard list endpoint, and never
mutated after creation. It had a 1:1 relationship with
`ExperimentDefinition`. The audit confirmed there is no use case where
the two needed independent lifecycles — the second tier was
infrastructure overhead, not a domain distinction.

## §4 — Read boundary: runtime reads only run-tier tables `[v2: added]`

A class of v1 bugs ("the runtime is reading the definition row for the
sandbox subclass when it should be reading the snapshot in the run row")
is eliminated by a single rule:

> **After `prepare_run` copies the graph from definition into run-tier
> tables, all subsequent runtime code reads exclusively from run-tier
> tables.** No fall-through path may resolve a `Sandbox`, `Worker`,
> `Evaluator`, or `Task` payload by reading from `experiment_definitions`
> or `experiment_definition_tasks`.

### Code-level expression

The rule is encoded in three places:

1. **`graph_repo.node(session, run_id, task_id)`** is the only call site
   the runtime uses to fetch a Task during a run. It joins
   `run_graph_nodes` *only* — no join into `experiment_definition_tasks`
   even when the row is a static-task copy. The `task_json` it returns
   is the run-tier copy, end of story.
2. **`Task.from_definition(...)` is invoked exclusively by
   `graph_repo.node`** (and by the dynamic-subtask spawn path that
   writes a fresh `run_graph_nodes` row). Workers, evaluators, and
   `worker_execute` never call `from_definition` directly; they read
   typed `node.task` from the repo view.
3. **No method named `_prepare_definition` exists.** The `prepare_run`
   service copies definition rows into run rows once, at run-launch, and
   from that point forward `definition_*` tables are not read by any
   code under `core.application.*` except `definition_writer.py`
   (write-only, at experiment-define time).

### Architecture-guard test

The boundary is enforced by a guard test in
[`07-test-strategy.md`](07-test-strategy.md):

```python
def test_runtime_does_not_read_definition_tables() -> None:
    """Static check: no module under core/application/runtime imports
    DefinitionRepository, ExperimentDefinitionTask, or any other
    definition-tier ORM class."""
```

### Why the boundary matters

Without it, the runtime can silently disagree with itself:
`worker_execute` resolves the sandbox from the run-tier copy,
`prepare_subtask` resolves it from the definition-tier copy, and a
benign-looking edit to either tier produces drift only one path sees.
Forcing all reads through run-tier means the snapshot taken at run-launch
is the **only** truth the runtime knows about.

## §5 — Dynamic subtasks are graph-native `[v2: added]`

When a worker calls `context.spawn_task(...)` mid-run, the new task is
born into `run_graph_nodes` only — there is no synthesized
`experiment_definition_tasks` row.

### Schema implications

`experiment_definition_tasks` rows have `task_id UUID PRIMARY KEY`
(non-null, present for every static task). `run_graph_nodes` rows have
`task_id UUID` (always non-null, since identity exists for all tasks)
and an optional join target — the discriminator `static vs. dynamic` is:

```sql
-- A dynamic task is a run_graph_nodes row whose task_id has no matching
-- row in experiment_definition_tasks for the same definition_id.
SELECT n.run_id, n.task_id
FROM run_graph_nodes n
JOIN runs r ON r.id = n.run_id
LEFT JOIN experiment_definition_tasks d
       ON d.experiment_definition_id = r.definition_id
      AND d.task_id = n.task_id
WHERE d.task_id IS NULL;
```

For lookup performance, `run_graph_nodes` carries an `is_dynamic`
boolean column (denormalized at insert time) so this question doesn't
need a join.

### What the spawn path does

```python
# Inside WorkerContext.spawn_task — framework-internal:
new_task_id = uuid4()
graph_repo.insert_node(
    session,
    run_id=self.run_id,
    task_id=new_task_id,
    parent_task_id=self.task_id,
    task_json=spec.to_definition(),         # the spawned-task spec, _type-discriminated
    is_dynamic=True,
    status=NodeStatus.PENDING,
)
graph_repo.insert_edge(
    session,
    run_id=self.run_id,
    parent_task_id=self.task_id,
    child_task_id=new_task_id,
    kind=EdgeKind.PARENT_CHILD,
)
# No write to experiment_definition_tasks. None.
```

Subsequent reads of the spawned task go through the same
`graph_repo.node(...)` path as static tasks — by §4's rule, the runtime
doesn't know or care whether the row was originally copied from a
definition or born dynamically.

### What this kills

- The `materialize_dynamic_subtask_definition` path in v1, which wrote a
  synthetic row into `experiment_definition_tasks` so dynamic tasks
  could be looked up via the same definition-tier query as static ones.
  Replaced by: there's only one query path, and it goes through
  `run_graph_nodes`.
- The `_prepare_definition` runtime helper that hydrated `Task` from
  `experiment_definition_tasks` rows for *both* static-copy and
  dynamic-synthetic cases. Deleted.

### Identity is still preserved

A dynamic task's `task_id` is generated at spawn time (`uuid4()`) and
that same `task_id` is what `node.task.task_id` returns to worker code.
Cross-run analytics on dynamic tasks works the same way as for static
tasks — the only thing different is whether a row exists in
`experiment_definition_tasks` for the same `task_id`.

## §6 — Decisions locked at workshop `[v2: locked]`

The workshop resolved the open questions §3–§5 surfaced. For
provenance:

- **Indexed columns on `experiment_definitions`** — **locked: dedicated
  columns + JSONB.** Per §3, `name` and `description` are dedicated
  `TEXT` columns; `metadata` is `JSONB`. Dashboard queries hit indexed
  columns; ad-hoc tags live in `metadata`.
- **`is_dynamic` boolean denormalization** — **locked: carry the
  boolean.** Per §5, `run_graph_nodes.is_dynamic BOOLEAN NOT NULL`
  avoids a left-join on every node read. Cheap to maintain
  (denormalized at insert time, never updated).
- **Definition versioning** — **locked: stripped.** No `version` column
  on `experiment_definitions`. Each `persist_definition` call produces
  a fresh definition row with a new `definition_id`. Authors who want
  "v2 of a benchmark" create a new definition with a new `name` (or
  reuse the same `name` — `name` is not a unique key). The v1
  `(name, version)` compound key concept is gone.
- **Run-graph WAL retention** — **locked: keep forever (for v2
  launch).** `run_graph_mutations` and `run_graph_annotations` are
  retained without expiry. Storage is not the bottleneck at current
  scale; revisit if/when row counts get painful and tier into S3 or
  drop oldest. Tracked as a non-blocking follow-up.
