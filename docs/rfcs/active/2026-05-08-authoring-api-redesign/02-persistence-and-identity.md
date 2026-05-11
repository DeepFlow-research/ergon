# 02 — Persistence and identity

> How the typed objects from [`01-api-surface.md`](01-api-surface.md) move
> between Python and Postgres, how the runtime reconstructs them, and the
> two-table identity model that underpins both static tasks and dynamic
> spawning. See [`03-runtime.md`](03-runtime.md) for what the rollout
> container does with the result and
> [`04-walkthrough.md`](04-walkthrough.md) for the concrete trace.

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

class Worker(BaseModel, ABC):
    @classmethod
    def from_definition(cls, worker_json: dict[str, Any]) -> "Worker":
        """Reconstruct a concrete Worker subclass from its persisted JSON.
        Discovers the subclass via the `_type` discriminator."""
        WorkerCls = import_component_string(worker_json["_type"])
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
        task_json: dict[str, Any],
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
        """
        TaskCls = import_component_string(task_json["_type"])
        instance = TaskCls.model_validate(task_json)
        # PrivateAttr on a non-frozen BaseModel is settable directly;
        # object.__setattr__ kept for symmetry with frozen-Sandbox patterns.
        object.__setattr__(instance, "_task_id", task_id)
        return instance

class Sandbox(BaseModel, ABC):
    @classmethod
    def from_definition(cls, sandbox_json: dict[str, Any]) -> "Sandbox":
        SandboxCls = import_component_string(sandbox_json["_type"])
        return SandboxCls.model_validate(sandbox_json)

# Same shape on Criterion, Rubric, Benchmark.
```

`from_definition` takes a `dict` (the JSON from the row), **not** the
typed row itself — that would create an `api → persistence` dependency
in the wrong direction. It should not take a worker/evaluator pool:
those objects are part of `Task` itself now. The guideline: after
`from_definition`, no field on the returned object should still be a
"go look this up over there" reference.

There is **no `_materialize` classmethod** on `Task` (or any other
class). `from_definition` is the single framework-internal entry
point that goes from "raw JSON + resolution context" to "fully usable
runtime instance." This avoids the two-step `model_validate` →
`_materialize` shape an earlier draft had, where it was unclear which
method owned identity binding.

The job body shouldn't see a `dict[str, Any]` though — the repo is the
bridge, and it returns *fully inflated typed objects*, never raw JSON.
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
`dict[str, Any]` parameter is honest about being the typing boundary
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
