# 05 — Migration

> **Single PR, no backward compatibility.** Ergon has no external
> contributors yet; we ship the redesign as one cohesive break rather
> than a phased rollout with deprecation windows. The phase structure
> below is **work-order within the PR** (Phase 1 unblocks Phase 2's
> assumptions, etc.), not a release sequence. Each step links into the
> reference docs ([`01-api-surface.md`](01-api-surface.md),
> [`02-persistence-and-identity.md`](02-persistence-and-identity.md),
> [`03-runtime.md`](03-runtime.md)) for the design it implements;
> [`04-walkthrough.md`](04-walkthrough.md) describes the end state.

The PR lands all four phases together. No `WorkerSpec`-shim release, no
`Worker.__init__(tools=...)` deprecation warning, no transitional
`Sandbox | None` parameter — the cliff is intentional. This is only safe
because:

1. There are no external benchmark contributors to break (every consumer
   lives in this repo and is updated in the same PR).
2. Local PG carries no production data, so all schema changes are
   drop-and-recreate rather than data migrations.
3. The phases are ordered so the codebase compiles and tests pass
   at the end of each phase, even if no in-between commits would.

Within the PR, organise commits by phase for review-ability — the
reviewer reads Phase 1's worker serialization first, then Phase 2's
sandbox subclassing on top of that, etc. — but no commit is intended
to be shippable in isolation.

## Core deduplication audit

Promoting logic from `ergon_core/core/...` to `ergon_core.api/...` only
pays off if the core counterparts are **deleted, thinned, or visibly
re-purposed in the same PR**. Otherwise we ship the public surface and
keep the parallel internal implementation, doubling our maintenance
surface area for no benefit. The audit below pairs every public
addition with its core counterpart and labels the action to take.
Per-step descriptions in Phases 1–4 reference these pair numbers as
`(audit #N)`; the [Deletion checklist](#deletion-checklist-reviewer)
at the end gives the `git grep` invocations that verify each pair has
been resolved.

| # | Public addition | Today's core counterpart | Action | Lands in |
|---|---|---|---|---|
| 1 | `Sandbox` (ABC, in `api/sandbox/`) + concrete subclasses (in `ergon_builtins/sandboxes/`) | `core/infrastructure/sandbox/manager.py`: `BaseSandboxManager`, `DefaultSandboxManager`; `core/infrastructure/sandbox/lifecycle.py: terminate_sandbox_by_id` | **DELETE** `BaseSandboxManager` / `DefaultSandboxManager`. **REPURPOSE** `lifecycle.py` to host `SandboxLifecycleHub` (acquire / release / terminate_all). Per-kind provisioning logic moves into per-kind `Sandbox` subclasses; the singleton state (`_sandboxes`, `_creation_locks`, `_file_registries`) collapses into `SandboxLifecycleHub`. | Phase 2 (steps 7–11) |
| 2 | `Worker` (serializable Pydantic + `from_definition`) | `core/domain/experiments/worker_spec.py`: `WorkerSpec` (slug+name+model, registry-validated); `api/registry.py`: `ComponentRegistry`, `register_builtins`, `registry.publish`; `ComponentCatalogService.build_worker(...)` | **DELETE** `WorkerSpec` and the entire `ComponentRegistry` machinery. `Task.worker` becomes the direct serializable `Worker` object; validation becomes "this `Worker` is pydantic-constructible" + "its sandbox requirement matches `Task.sandbox`", not "the slug is in `registry`". | Phase 1 (steps 3–6) |
| 3 | `Task.from_definition` + `Task.worker`, `Task.sandbox`, `Task.evaluators` direct object bindings | Ad-hoc `import_component_string + model_validate` in `core/application/jobs/worker_execute.py`; `TaskSpec`; `experiment_definition_task_assignments`; experiment-level worker/evaluator pools | **DELETE** `TaskSpec`. **DELETE** assignment/pool indirection for workers/evaluators. **THIN** `worker_execute.py` — the job body becomes `task = node.task; worker = task.worker` (no parsing or binding lookup in the job). The repo (step 12a) is the single materialization path. | Phase 3 (steps 12–15) |
| 4 | `Evaluator.from_definition` | `core/application/evaluation/service.py`: `EvaluationService.prepare_dispatch`; `core/application/evaluation/models.py`: `PreparedSingleEvaluator`, `CriterionSpec` (KEEP) | **THIN** `prepare_dispatch` to drop inline assembly (the `from_definition` call replaces it). **KEEP** `CriterionSpec` — still useful as a wrapper bundling a `Criterion` with its weight inside a dispatch batch. | Phase 1 (step 5) |
| 5 | `Criterion.evaluate(..., sandbox: Sandbox)` | `core/application/evaluation/criterion_runtime.py`: `DefaultCriterionRuntime`, `CriterionRuntimeOptions` (only consumer of `BaseSandboxManager` from criterion code) | **DELETE** `DefaultCriterionRuntime` and `CriterionRuntimeOptions`. Criterion code now calls `sandbox.run_command(...)` directly through the public `Sandbox` IO methods; the runtime indirection has no purpose once `Sandbox` is the public contract. | Phase 4 (step 17) |
| 6 | `Experiment` (Pydantic `BaseModel` + `requires_sandbox` `@model_validator`, in `api/experiment.py`) | `core/domain/experiments/experiment.py`: `class Experiment` (plain Python class, `__init__`-based, with a `validate()` method that delegates to `ExperimentValidationService`) | **DELETE** `core/domain/experiments/experiment.py` and **MOVE** the class definition into `api/experiment.py`. Drop the `Experiment` re-export from `core/domain/experiments/__init__.py`. Internal callsites flip to `from ergon_core.api import Experiment`. `ExperimentValidationService` and `DefinitionHandle` stay in `core/domain/experiments/` — they operate on the public `Experiment` but aren't part of the authoring contract. | Phase 1 (step 4) |

**Not in this audit on purpose.** An earlier draft included three more
audit pairs covering a layered public runtime API
(`GraphMutator` / `GraphInspector` / `ResourceInspector` in
`ergon_core.api`, plus an enforced boundary on
`ergon_builtins → core.application` and the consequent Command-DTO /
`SubtaskInfo` / `RunResourceView` cleanup). All of that was rolled
back as scope creep — see the
["What's deferred"](#whats-deferred-not-phase-5--not-v1) section
below. `TaskManagementService` / `TaskInspectionService` /
`RunResourceRepository` (and their associated DTOs) stay as they are
today; `WorkerContext` is the public runtime surface, and toolkits /
the CLI keep their existing core.application imports until a real
consumer demands the boundary.

**Incidental cleanups** the audit surfaced (folded into the relevant
existing step rather than spawning new ones):

- **`core/domain/experiments/validation.py`** —
  `ExperimentValidationService` keeps the cross-component rules engine
  but **THINS** to drop validations now done by
  `Worker.from_definition` / `Evaluator.from_definition` (folded into
  step 5).
- **`core/infrastructure/sandbox/lifecycle.py`** — currently a one-function
  delegating wrapper around
  `BaseSandboxManager.terminate_by_sandbox_id`. **REPURPOSE** the file
  to host `SandboxLifecycleHub`; the file path stays, the contents
  change wholesale (folded into step 9).

## Phase 1: Worker becomes serializable (`WorkerSpec` dies)

1. **Move `tools` out of `Worker.__init__`; add `sandbox: Sandbox`
   parameter to `execute()` (non-optional from day one).** Touch every
   worker subclass in `ergon_builtins/workers/` and
   `benchmarks/*/worker_factory.py`. The base `Worker` interface no
   longer mentions `tools`. Because Phase 2 lands in the same PR, we
   skip the previously-planned transitional `Sandbox | None` step —
   `Sandbox` exists as a real type by the time this code is exercised.
   See
   [`01-api-surface.md#foundational-change-a-worker-becomes-serializable`](01-api-surface.md#foundational-change-a--worker-becomes-serializable).
2. **Reshape `ReActWorker` to take `_toolkit: _Toolkit` as a field; delete
   per-benchmark `*ReactWorker` subclasses.** `_Toolkit` is module-private
   to `ergon_builtins.workers.baselines.react_worker` (not exposed in
   `ergon_core.api` — the framework stays tool-agnostic). Migrate the
   existing `MiniF2FToolkit`, `SWEBenchToolkit`, `GDPEvalToolkit` to
   subclass `_Toolkit` and become pydantic-serializable; their
   `__init__(sandbox=...)` collapses into a `build_tools(sandbox, task)`
   method. Each benchmark's `worker_factory.py` returns
   `ReActWorker(toolkit=BenchmarkToolkit(...), name=..., model=...,
   system_prompt=..., max_iterations=...)` instead of constructing a
   custom Worker subclass. `MiniF2FReactWorker`, `SWEBenchReActWorker`,
   `GDPEvalReActWorker` delete. No behavior change for the runtime.
3. **Make `Worker` a pydantic `BaseModel`.** Subclasses become declared
   fields (no `__init__` overrides). `WorkerSpec` is still alive but is
   now constructible from `Worker.model_dump()`. Per-benchmark subclasses
   now serialize round-trip cleanly (their config-fields persist, the
   live tool objects are rebuilt from `sandbox` on each `execute`).
4. **Replace `WorkerSpec` with direct `Task.worker` object bindings**
   *(audit #2/#3)*. `_type`-discriminator JSON serialization means the
   concrete worker object lives inside each `Task.model_dump()`.
   `Experiment` no longer has `workers`, `evaluators`, or `assignments`
   pools. Update `ExperimentDefineRequest` and persistence rows. Deletes
   the `WorkerSpec` class itself
   (`core/domain/experiments/worker_spec.py`) and the
   `worker_slug ∈ registry.workers` validation that lived on it.
   Sub-task: **lift `Experiment` into `ergon_core.api`** *(audit #6)*.
   Move the class definition from
   `ergon_core/core/domain/experiments/experiment.py` into a new
   `ergon_core/api/experiment.py`, **delete** the old file, and update
   `ergon_core/core/domain/experiments/__init__.py` to drop the
   `Experiment` re-export (and the `WorkerSpec` re-export, which is
   dying anyway under audit #2).    The lifted class becomes a Pydantic
   `BaseModel` so it can host the `requires_sandbox`
   `@model_validator(mode="after")` (see
   [`01-api-surface.md`](01-api-surface.md#foundational-change-c--experiment-lifts-into-the-public-api)
   for the class sketch and
   [`06-decisions-log.md`](06-decisions-log.md) "Worker → Sandbox
   compatibility checking" for why the validator lives here); the
   runtime-only `_persisted` reference becomes a `PrivateAttr` rather
   than a plain attribute. `DefinitionHandle` and `ExperimentValidationService`
   stay in `core/domain/experiments/` (handles is purely internal;
   the validation service operates on the public `Experiment`
   instance from `definition_writer`). Add `Experiment` to
   `ergon_core/api/__init__.py`'s re-exports. Internal callsites that
   import `Experiment` flip from
   `from ergon_core.core.domain.experiments import Experiment`
   to `from ergon_core.api import Experiment`:
   - `ergon_cli/ergon_cli/composition/__init__.py`
   - `ergon_core/ergon_core/core/application/experiments/launch.py`
   - `ergon_core/ergon_core/core/application/experiments/service.py` (TYPE_CHECKING block)
   - `ergon_core/ergon_core/core/application/experiments/definition_writer.py` (TYPE_CHECKING block)
   - `ergon_core/ergon_core/core/domain/experiments/validation.py` (TYPE_CHECKING block)
   - any benchmark constructor in `ergon_builtins/benchmarks/*` that
     happens to reach into `core.domain.experiments` for the type
     (most go through `ergon_core.api` already; sweep `git grep` to
     confirm).

   Update the boundary tests
   (`tests/unit/api/test_public_api_imports.py`,
   `tests/unit/architecture/test_public_api_boundaries.py`) to treat
   `Experiment`, `WeightedCriterion`, and `Sandbox` as part of the
   public surface, and add a target-structure assertion that
   `ergon_core.core.domain.experiments.experiment` no longer exists
   (catches accidental re-introduction of the old path).
5. **Add `from_definition` classmethod to each authoring base class**
   *(audit #4 for `Evaluator`)* — `Worker.from_definition(json) ->
   Worker`, `Benchmark.from_definition(json) -> Benchmark`,
   `Evaluator.from_definition(json) -> Evaluator`,
   `Criterion.from_definition(json) -> Criterion`. Each does the
   `_type`-discriminator lookup + `model_validate` internally so that
   `worker_execute.py` (and any future job that loads these from PG)
   never has to. Same shape gets added to `Task` (with the extra
   `task_id` arg for identity binding — see step 12 + the
   `Task.from_definition` block in
   [`02-persistence-and-identity.md`](02-persistence-and-identity.md))
   and `Sandbox` in Phase 2/3. See
   [`02-persistence-and-identity.md#persistence-typed-repos-at-the-boundary-from_definition-on-the-class`](02-persistence-and-identity.md#persistence-typed-repos-at-the-boundary-from_definition-on-the-class).
   Sub-tasks: thin
   `core/application/evaluation/service.py: EvaluationService.prepare_dispatch`
   to drop its inline `_type`-lookup + `model_validate` (now
   `Evaluator.from_definition` does it); thin
   `core/domain/experiments/validation.py: ExperimentValidationService`
   to drop validations now done at construction time on the public
   models.
6. **Delete `ComponentRegistry`, `register_builtins`, `registry.publish`,
   `ComponentCatalogEntry` table** *(audit #2)* (drop and recreate; no
   data migration). There is no replacement worker-binding lookup:
   `worker_execute.py` reads `node.task.worker` after
   `WorkflowGraphRepository.node(...)` inflates `task_json`. Same for
   evaluators (`node.task.evaluators`). Job body never touches
   `session.get` or `import_component_string` directly.

## Phase 2: Sandbox subclass-per-kind (`SandboxSpec`/`SandboxManager` die)

7. **Add `Sandbox(BaseModel, ABC)` with `_runtime` PrivateAttr, abstract
   `provision()` / overridable `terminate()`, inherited proxy methods**
   (`run_command`, `write_file`, `read_file`, `list_files`, …), **and a
   `from_definition` classmethod** matching the convention from step 5.
   The proxy methods follow the same pattern `CriterionRuntime` uses
   today. See
   [`01-api-surface.md#foundational-change-b-sandbox-becomes-a-typed-sandbox-subclass-per-kind`](01-api-surface.md#foundational-change-b--sandbox-becomes-a-typed-sandbox-subclass-per-kind).
8. **Replace each per-benchmark `*SandboxManager` with a `Sandbox`
   subclass.** `MiniF2FSandboxManager` → `LeanSandbox(Sandbox)`,
   `SWEBenchSandboxManager` → `SWEBenchSandbox(Sandbox)`,
   `ResearchRubricsSandboxManager` → `ResearchE2BSandbox(Sandbox)`,
   `GDPEvalSandboxManager` → `GDPEvalSandbox(Sandbox)`. Each subclass's
   `provision()` reads the same credentials from `settings`/env that its
   manager did, calls the same E2B/Docker create logic, and runs the
   same install scripts. Pure relocation — no behavior change. Per-kind
   config (lean version, repo url, image name) becomes typed pydantic
   fields on the subclass; secrets stay in `settings`/env, never as
   fields. Add a `_E2BBackedSandbox` shared parent in `ergon_builtins`
   for the four E2B-backed kinds to avoid copy-paste of E2B client
   construction.
9. **Add `SandboxLifecycleHub` for process-wide tracking** *(audit #1)*.
   Tiny class: `acquire(sandbox)` calls `sandbox.provision()` (or
   reattaches by `sandbox_id` for retries); `release(sandbox)` calls
   `sandbox.terminate()`; `terminate_all()` for shutdown. Lands by
   **repurposing** `core/infrastructure/sandbox/lifecycle.py` (the
   file path is preserved; the existing `terminate_sandbox_by_id`
   one-function shim is replaced wholesale by the new class). Stays
   internal to `ergon_core` (not in the public API — only the rollout
   container uses it). Replaces the singleton
   `_sandboxes`/`_creation_locks` registry on `BaseSandboxManager`. See
   [`03-runtime.md#sandboxlifecyclehub-the-small-thing-that-survives`](03-runtime.md#sandboxlifecyclehub--the-small-thing-that-survives).
10. **Add `Task.sandbox: Sandbox` field** (non-optional). Drop and
    recreate `experiment_definition_tasks` with the new column shape
    (no data migration; local PG has no production data to preserve).
    Each in-tree benchmark already declares a real sandbox, so the
    redefined schema is satisfiable from the existing benchmark code
    without a synthetic fallback.
11. **Delete `BaseSandboxManager` and `DefaultSandboxManager`** *(audit #1)*.
    All callsites (`worker_execute.py`, sandbox setup Inngest handler,
    `SandboxResourcePublisher`) now go through the `Sandbox` subclass +
    `SandboxLifecycleHub` instead. Also delete the singleton-per-subclass
    machinery (`__new__` override, `_sandbox_manager_classes`,
    `_creation_locks`, `_sandboxes`, `_file_registries`,
    `_created_files_registry`, `_run_ids`, `_display_task_ids`) — its
    surviving responsibilities are split between per-instance
    `Sandbox._runtime` (PrivateAttr) and process-wide
    `SandboxLifecycleHub`.

## Phase 3: Task unification + two-table identity model

12. **Add `_task_id` `PrivateAttr` to `Task`, direct object-bound
    fields (`worker: Worker`, `evaluators: tuple[Evaluator, ...]`),
    and a single `Task.from_definition(task_json, *, task_id)
    classmethod`** that combines `_type` lookup + `model_validate` +
    identity binding (`_task_id`) atomically. There is **no separate
    `_materialize`**: `from_definition` is the one framework-internal
    entry point. Author code constructs `Task(...)` directly; `_task_id`
    defaults to `None` (and `task.task_id` raises
    `TaskNotMaterializedError`). Only the graph repo (step 12a) calls
    `from_definition`. Update downstream iteration sites to read
    `task.worker` and `task.evaluators` directly from the inflated
    task — no binding-key lookup.

12a. **Repo returns inflated typed objects, never raw JSON.** Add a
    `RunGraphNodeView` (frozen `BaseModel`; typed view of one
    `run_graph_nodes` row + its inflated `Task`) and change
    `graph_repo.node(...)` to call `Task.from_definition` internally
    and return `RunGraphNodeView`. Update
    `worker_execute.py` (and the dynamic-subtask read path) to consume
    `node.task` directly — no `Task.from_definition` call, no
    `dict[str, Any]` ever crossing the repo boundary into the job body.
    The job body resolves `worker = node.task.worker`; evaluators are
    already on `node.task.evaluators`.
13. **Delete `TaskSpec`, rename `Benchmark.build_instances()` to return
    `Mapping[str, Sequence[Task]]`** *(audit #3)*. Definition-time Tasks
    have no `_task_id`; the `task_id` property raises
    `TaskNotMaterializedError` if accessed. Update callsites.
14. **Schema redesign for the two-table identity model — drop and recreate
    `run_graph_nodes` and downstream tables.** No data migration; local
    PG has no production data to preserve. See
    [`02-persistence-and-identity.md#identifier-model-two-tables-one-identity`](02-persistence-and-identity.md#identifier-model-two-tables-one-identity).

    The current schema is *not* yet a clean "definitions → copy → runs"
    model — `run_graph_nodes` carries selective columns (`description`,
    `task_slug`, `instance_key`, `assigned_worker_slug`) plus an FK
    back via `definition_task_id`, and the runtime walks
    `node → assignment → worker_pool → registry` to resolve a worker.
    This step deletes that walk entirely: `node.task.worker` is the
    worker.
    This step makes the snapshot semantics literal: at run-launch we do
    one `INSERT … SELECT` from defs into runs, and the runs row is
    fully self-contained thereafter.

    **Definition-side changes:**

    - Add `task_json: JSON` column to `experiment_definition_tasks`.
      Holds the full pydantic `Task.model_dump()` (including `_type`
      discriminator, `worker`, `sandbox`, `evaluators`, `task_payload`).
      The current discrete columns
      (`task_type`, `description`, `task_payload_json`) become
      redundant — drop them, or keep one or two as denormalized indexes
      with the explicit understanding they must stay in sync with
      `task_json`. **Recommendation: drop them all; index the JSON
      where queries need it.**
    - **DROP** `experiment_definition_task_assignments`. Worker assignment
      is no longer a side table; the directly bound `Task.worker` object
      lives inside `task_json`.
    - **DROP** `experiment_definition_workers` and
      `experiment_definition_evaluators`. Workers and evaluators live
      inside each task's JSON; keeping definition-level pools would
      preserve the indirection this redesign is deleting.

    **Run-side changes to `run_graph_nodes`:**

    - Change PK from `id` (single UUID) to **composite `(run_id,
      task_id)`**. `task_id` replaces both `id` and
      `definition_task_id`. For static tasks `task_id` is copied
      verbatim from `experiment_definition_tasks.id` at run-launch
      (NOT a fresh UUID); for dynamic tasks it's a fresh `uuid4()`
      allocated by `WorkerContext.spawn_task`.
    - **DROP** `definition_task_id` column. The task_id-equals-def-id
      property makes the back-reference implicit (a constraint can
      assert "for any static task, the same id exists in
      `experiment_definition_tasks`"; for dynamic tasks no such row
      exists).
    - **ADD** `task_json: JSON` column. Populated at run-launch by
      literal copy from `experiment_definition_tasks.task_json` for
      static tasks; written by `WorkerContext.spawn_task` for dynamic
      children.
    - **DROP** `assigned_worker_slug` entirely. Do not replace it with
      `worker_binding_key`: the worker object is inside `task_json.worker`
      for both static and dynamic tasks.
    - **DROP** `description`, `task_slug`, `instance_key` as separate
      columns — they live inside `task_json`. (Same trade-off note as
      the def-side: keep individual ones as denormalized indexes only
      if a query needs them.)
    - `parent_node_id` → `parent_task_id`, references composite
      `(run_id, parent_task_id)` rather than single-UUID `node_id`.
    - `level` column survives (or compute on insert) — useful for the
      dashboard and avoids N+1 depth queries.

    **Run-launch becomes a literal copy:**

    ```sql
    INSERT INTO run_graph_nodes (run_id, task_id, parent_task_id, task_json,
                                 status, level)
    SELECT :run_id, t.id, t.parent_task_id, t.task_json,
           'PENDING', /* derive */
    FROM experiment_definition_tasks t
    WHERE t.experiment_definition_id = :definition_id;
    ```

    No deserialization, no field-by-field assembly, no second read of
    the def table during the run. After this insert the runtime never
    reads `experiment_definition_*` again; everything it needs is on
    `run_graph_nodes.task_json`.

    **Composite-FK fanout, Inngest payloads, and internal DTOs** are
    each non-trivial enough to deserve concrete schemas — see the
    "[Schema and contract reference](#schema-and-contract-reference-for-step-14)"
    section below for the exact target shape of every affected table,
    every Inngest payload, and every internal DTO. **Treat that
    section as the source of truth when implementing step 14**;
    each item here is a one-line summary of the change for context:

    - `run_graph_edges`: composite `(run_id, source_task_id, target_task_id)` natural key on top of synthetic `id` UUID; drop `definition_dependency_id`. → [§14.A.2](#14a2-run_graph_edges)
    - `run_graph_annotations` / `run_graph_mutations`: keep `(run_id, target_id, target_type)`; semantics of `target_id` change for `target_type='node'` (`task_id` instead of `node_id`). → [§14.A.3](#14a3-run_graph_annotations--run_graph_mutations)
    - `run_task_executions` (the "executions" table — current name): drop `node_id` and `definition_task_id`; add `task_id`; composite FK `(run_id, task_id) → run_graph_nodes`. → [§14.A.4](#14a4-run_task_executions-the-executions-table)
    - `run_task_evaluations`: same shape change. → [§14.A.5](#14a5-run_task_evaluations)
    - Inngest event payloads: 12 payload classes change; `node_id` is dropped and `task_id` is required (currently optional on most). → [§14.B](#14b--inngest-payloads)
    - Internal DTOs (`SubtaskInfo`, `AddSubtaskCommand`, `PlanSubtasksResult`, etc.): `node_id`/`parent_node_id` → `task_id`/`parent_task_id`; slug-based subtask path is replaced by `Task`-based path. → [§14.C](#14c--internal-dto-reshape)
    - `WorkflowGraphRepository.node(...)` returns an inflated `Task` that already contains its worker/evaluators — no definition worker/evaluator pool methods. → [§14.D](#14d--graph-repository-inflated-node-method)

    `node_id` is dropped from `WorkerContext`, every Inngest payload,
    every Inngest handler, every internal DTO, every replay tool.
    `task_id` (or `(run_id, task_id)` where the row identity matters)
    is the canonical identity throughout the codebase after step 14.

### Schema and contract reference (for step 14)

This section is the implementer's checklist for the schema rewrite.
Every shape here is the **target** state after step 14 has landed —
read it as "this is what a `psql \d run_graph_nodes` should print"
and "this is what `WorkerExecuteRequest` looks like in source." If
anything else in the codebase still has the pre-rewrite shape after
step 14, that's a bug.

#### 14.A — Tables

##### 14.A.1 `run_graph_nodes`

```python
class RunGraphNode(SQLModel, table=True):
    __tablename__ = "run_graph_nodes"
    __table_args__ = (
        sa.PrimaryKeyConstraint("run_id", "task_id"),
        sa.Index("ix_run_graph_nodes_parent",
                 "run_id", "parent_task_id"),
        sa.Index("ix_run_graph_nodes_status", "run_id", "status"),
    )

    run_id: UUID = Field(foreign_key="runs.id")
    task_id: UUID                                    # PK part 2; copied from def for static, fresh uuid4 for dynamic
    task_json: dict = Field(sa_column=Column(JSON))  # full Task.model_dump() — _type, worker, sandbox, evaluators, payload, ...
    parent_task_id: UUID | None = None               # composite FK → (run_id, parent_task_id); null for static roots
    status: str = Field(index=True)                  # free-form, owned by experiment layer
    level: int = Field(default=0)                    # depth in containment tree
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
```

Notable drops vs today: `id`, `definition_task_id`, `description`,
`task_slug`, `instance_key`, `assigned_worker_slug`, `parent_node_id`.
All of `description`, `task_slug`, `instance_key` are inside
`task_json` and accessed via `Task.from_definition(task_json,
...).description` etc. — no separate columns unless a query needs
the index. Worker and evaluator data are also inside `task_json`; there
is no replacement `worker_binding_key` column.

##### 14.A.2 `run_graph_edges`

```python
class RunGraphEdge(SQLModel, table=True):
    __tablename__ = "run_graph_edges"
    __table_args__ = (
        sa.UniqueConstraint("run_id", "source_task_id", "target_task_id",
                            name="uq_run_graph_edges_natural"),
        sa.ForeignKeyConstraint(
            ["run_id", "source_task_id"],
            ["run_graph_nodes.run_id", "run_graph_nodes.task_id"],
            name="fk_run_graph_edges_source",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "target_task_id"],
            ["run_graph_nodes.run_id", "run_graph_nodes.task_id"],
            name="fk_run_graph_edges_target",
        ),
        sa.Index("ix_run_graph_edges_target", "run_id", "target_task_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)   # synthetic — used by annotations/mutations to reference an edge
    run_id: UUID = Field(foreign_key="runs.id")
    source_task_id: UUID
    target_task_id: UUID
    status: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
```

Why keep a synthetic `id`: annotations and mutations reference targets
polymorphically (node-or-edge). Nodes use composite `(run_id,
task_id)`; edges use `(run_id, edge_id)`. With a synthetic edge `id`
the polymorphic reference shape is symmetric — `(run_id, target_id)
+ target_type` works for both. The `(run_id, source_task_id,
target_task_id)` natural key is enforced via `UniqueConstraint` so
duplicate edges still fail loudly. `definition_dependency_id` is
dropped (edges are snapshots too).

##### 14.A.3 `run_graph_annotations` / `run_graph_mutations`

Both keep their shape. The change is a **semantic re-interpretation
of `target_id`** — for `target_type='node'`, `target_id` is now a
`task_id` (from `run_graph_nodes.task_id`), not a node row id. For
`target_type='edge'`, `target_id` remains the edge's synthetic UUID.
The `(run_id, target_id, target_type)` triple still uniquely names a
target. Schema:

```python
class RunGraphAnnotation(SQLModel, table=True):
    __tablename__ = "run_graph_annotations"
    __table_args__ = (
        sa.Index("ix_annotation_lookup",
                 "run_id", "target_type", "target_id",
                 "namespace", "sequence"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id")
    target_type: str                                 # GraphTargetType: 'node' | 'edge'
    target_id: UUID                                  # task_id when target_type='node', edge.id when 'edge'
    namespace: str
    sequence: int = Field(index=True)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
```

Same shape applies to `run_graph_mutations` (with its existing
extra fields: `mutation_type`, `actor`, `old_value`, `new_value`,
`reason`, `triggered_by_mutation_id`, `batch_operation_id`). No FK
constraint on `target_id` — annotations/mutations were always
deliberately FK-free here so a target row can be deleted without
losing the audit trail.

Why this shape vs alternatives: a column-pair-per-target-type
schema (`node_run_id` + `node_task_id` nullable, `edge_id` nullable,
`target_type` discriminator) gives you FK enforcement but pollutes
every query with NULL handling and breaks the "annotations index by
sequence" pattern. JSON-blob targets lose the sequence index. The
synthetic-edge-`id` approach (chosen) keeps the existing single
`target_id` column working with one semantic change.

##### 14.A.4 `run_task_executions` (the "executions" table)

```python
class RunTaskExecution(SQLModel, table=True):
    __tablename__ = "run_task_executions"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["run_id", "task_id"],
            ["run_graph_nodes.run_id", "run_graph_nodes.task_id"],
            name="fk_run_task_executions_node",
        ),
        sa.Index("ix_run_task_executions_node", "run_id", "task_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)   # one row per attempt; this is the execution_id
    run_id: UUID = Field(foreign_key="runs.id")
    task_id: UUID                                              # composite FK → run_graph_nodes
    attempt_number: int = 1
    status: TaskExecutionStatus = Field(index=True)
    started_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    completed_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    final_assistant_message: str | None = None
    output_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    error_json: dict | None = Field(default=None, sa_column=Column(JSON))
```

Notable drops vs today: `node_id` (replaced by `task_id`),
`definition_task_id` (no longer needed — `(run_id, task_id)`
back-references the node, which carries `task_json` with all the def
info inline). `validate_identity()` and the
"`definition_task_id` OR `node_id`" branching disappear — every row
has `(run_id, task_id)`, full stop.

##### 14.A.5 `run_task_evaluations`

```python
class RunTaskEvaluation(SQLModel, table=True):
    __tablename__ = "run_task_evaluations"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["run_id", "task_id"],
            ["run_graph_nodes.run_id", "run_graph_nodes.task_id"],
            name="fk_run_task_evaluations_node",
        ),
        sa.Index("ix_run_task_evaluations_node", "run_id", "task_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id")
    task_id: UUID                                              # composite FK → run_graph_nodes
    task_execution_id: UUID = Field(foreign_key="run_task_executions.id")
    evaluator_index: int                                      # index into task.evaluators for this execution
    evaluator_name: str | None = None                         # denormalized display/debug value, if present
    score: float | None = None
    passed: bool | None = None
    feedback: str | None = None
    summary_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
```

Drops `node_id`, `definition_task_id`, and `definition_evaluator_id`.
Evaluators are no longer normalized in a definition table; the canonical
definition lives in `task_json.evaluators`. `evaluator_index` identifies
which directly bound evaluator produced the row for this execution, and
`evaluator_name` is optional denormalized display/debug data.

#### 14.B — Inngest payloads

Source files:
`ergon_core/core/application/jobs/models.py` and
`ergon_core/core/application/events/task_events.py`. Every payload
that today carries `node_id` (or both `node_id` and `task_id`) is
collapsed onto **`task_id` only**. `task_id` becomes required (drop
the `| None` annotations and the `_has_static_or_dynamic_identity`
validator). `definition_task_id` mentions in payloads also disappear
(payloads may carry `definition_id` for logging/lookup, but worker and
evaluator resolution no longer needs it; the task snapshot in
`run_graph_nodes.task_json` is self-contained).

| Payload | File | Change |
|---|---|---|
| `WorkerExecuteRequest` | jobs/models.py | drop `node_id`, drop `task_slug`/`task_description`/`assigned_worker_slug`/`worker_type`/`benchmark_type`/`model_target` (all derivable from `task_json` on the node row), keep `run_id`/`definition_id`/`task_id`/`execution_id`/`sandbox_id`. Drop `_has_static_or_dynamic_identity` validator. |
| `SandboxSetupRequest` | jobs/models.py | already has `task_id`; drop `benchmark_type`/`sandbox_slug` (read from `task.sandbox`). |
| `PersistOutputsRequest` | jobs/models.py | already has `task_id`; drop `benchmark_type`/`sandbox_slug`. |
| `EvaluateTaskRunRequest` | jobs/models.py | drop `node_id`, make `task_id` required. Replace evaluator binding fields with `evaluator_index: int` (and optional `evaluator_name` for display/debug) because evaluators are inline on `task.evaluators`. Drop `evaluator_type` (derivable from the inflated evaluator object). |
| `TaskReadyEvent` | events/task_events.py | drop `node_id`, make `task_id` required. |
| `TaskStartedEvent` | events/task_events.py | already has `task_id`; make required (drop `\| None`). |
| `TaskCompletedEvent` | events/task_events.py | drop `node_id`, make `task_id` required. |
| `TaskFailedEvent` | events/task_events.py | drop `node_id`, make `task_id` required. Keep `sandbox_id: str \| None` (failure can predate sandbox setup). |
| `TaskCancelledEvent` | events/task_events.py | drop `node_id`, add `task_id` (required). Other fields unchanged. |
| `WorkflowStartedEvent` / `WorkflowCompletedEvent` / `WorkflowFailedEvent` | events/task_events.py | unchanged — they carry `run_id`/`definition_id` only. |
| `EvaluatorsResult` (result class) | jobs/models.py | already keys by `task_id`; make required. |
| `TaskExecuteResult` / `TaskPropagateResult` | jobs/models.py | already keyed by `task_id`; make required. |

Implementation note: every Inngest **handler** in
`ergon_core/core/infrastructure/inngest/handlers/*.py` reads
`event.data` into one of these payloads and then passes
`(run_id, task_id)` (or `(run_id, node_id)` today) into the
application services. Handler bodies follow the payload change
mechanically — each handler grep `node_id` and replace with
`task_id`. Affected handlers (13 files):

`worker_execute.py`, `persist_outputs.py`, `evaluate_task_run.py`,
`cleanup_cancelled_task.py`, `cancel_orphan_subtasks.py`,
`start_workflow.py`, `sandbox_setup.py`, `run_cleanup.py`,
`propagate_execution.py`, `fail_workflow.py`, `execute_task.py`,
`complete_workflow.py`, `check_evaluators.py`. None require structural
change beyond the field rename + payload-type adjustments.

#### 14.C — Internal DTO reshape

Source file: `ergon_core/core/application/tasks/models.py`. The whole
file is shaped around `node_id` and slug-based subtask creation
today; v1 reshapes it around `task_id` and `Task`-based subtask
creation. Concretely:

| DTO | Today | After |
|---|---|---|
| `AddSubtaskCommand` | `{run_id, parent_node_id, task_slug, description, assigned_worker_slug, depends_on: list[NodeId]}` | `{run_id, parent_task_id, task: Task, depends_on: list[UUID]}` — slug/description/payload/worker/evaluators all live inside the `Task` object now. |
| `AddSubtaskResult` | `{node_id, task_slug, status}` | `{task_id: UUID, status: str}` — caller pulls `task_slug` from the Task it just submitted. |
| `SubtaskSpec` (internal, batch entry) | `{task_slug, description, assigned_worker_slug, depends_on: list[TaskSlug]}` | `{task: Task, depends_on: list[TaskSlug]}` — batch construction keeps slug-based dependency references between the new tasks, but the executable/evaluable/sandbox config is object-bound on `task`. |
| `PlanSubtasksCommand` | `{run_id, parent_node_id, subtasks: list[SubtaskSpec]}` | `{run_id, parent_task_id, subtasks: list[SubtaskSpec]}` — `SubtaskSpec.task` carries the Task; `SubtaskSpec.depends_on` remains task-slug references within the submitted batch. |
| `PlanSubtasksResult` | `{nodes: dict[TaskSlug, NodeId], roots: list[TaskSlug]}` | `{tasks: dict[TaskSlug, UUID], roots: list[TaskSlug]}` — `UUID` is `task_id`. |
| `CancelTaskCommand` / `Result` | `{run_id, node_id}` / `{node_id, old_status, cascaded_count}` | `{run_id, task_id}` / `{task_id, old_status, cascaded_count}` |
| `RefineTaskCommand` / `Result` | `{run_id, node_id, new_description}` / `{node_id, old_description, new_description}` | `{run_id, task_id, new_description}` / `{task_id, old_description, new_description}` |
| `RestartTaskCommand` / `Result` | `{run_id, node_id}` / `{node_id, old_status, invalidated_node_ids: list[NodeId]}` | `{run_id, task_id}` / `{task_id, old_status, invalidated_task_ids: list[UUID]}` |
| `CancelOrphansResult` | `{parent_node_id, cancelled_node_ids: list[NodeId], events_to_emit: list[TaskCancelledEvent]}` | `{parent_task_id, cancelled_task_ids: list[UUID], events_to_emit: list[TaskCancelledEvent]}` |
| `SubtaskInfo` | `{node_id, task_slug, description, status, depends_on: list[NodeId], output, error}` | `{task_id: UUID, task_slug: str, description: str, status: NodeStatus, depends_on: list[UUID], output: str \| None, error: str \| None}` |
| `CleanupResult` | `{run_id, node_id, execution_id, sandbox_released, execution_row_updated}` | `{run_id, task_id, execution_id, sandbox_released, execution_row_updated}` |

Also delete `core/persistence/shared/types.py:NodeId` (the type
alias) and replace every import site with `UUID`. `TaskSlug`,
`RunId` survives. `AssignedWorkerSlug` dies with the assignment tables
and slug-based worker resolution.

`RunResourceView` (in `core/application/resources/models.py`) does
**not** carry `node_id` today — it keys off `task_execution_id`. No
shape change there; it's listed in the audit only because the user
asked for the full DTO sweep. Its `from_row` continues to work
unchanged (it reads from `RunResource`, which doesn't change shape).

**Implications and where this hurts:**

1. **`SubtaskInfo.depends_on` semantics change.** Today, `depends_on`
   contains `node_id`s of source nodes, looked up via
   `RunGraphEdge.source_node_id`. After: `task_id`s, looked up via
   `RunGraphEdge.source_task_id`. Inspection-service queries become
   `select(RunGraphEdge.source_task_id).where(RunGraphEdge.target_task_id
   == node.task_id, RunGraphEdge.run_id == node.run_id)` — composite
   key on the where clause. Mechanical change once the edges table
   is reshaped (§14.A.2).
2. **Slug-based subtask construction disappears, including the batch
   path.** Today's `AddSubtaskCommand{task_slug, description,
   assigned_worker_slug}` and `SubtaskSpec{task_slug, description,
   assigned_worker_slug}` are construction recipes. After this redesign,
   both single and batch paths receive fully-bound `Task` objects. Batch
   planning still uses slug references for dependencies between the newly
   submitted tasks (`depends_on: list[TaskSlug]`), but those slugs point
   at `spec.task.task_slug`; they do not resolve workers. Existing
   CLI/workflow callers must construct `Task(...)` first and submit that.
3. **`AddSubtaskCommand` carries a `Task` object, not a JSON dict.**
   The service's first job is `task.model_dump()` on the way to the
   row insert; the public API gives the service a typed Task and
   the service handles serialization. Avoids the surface-API leak
   of "JSON dict construction" into worker code.
4. **Test fixtures that build `SubtaskInfo` / `AddSubtaskResult` /
   etc. by hand all need the field rename.** Grep tests for
   `node_id=` in the `tasks/` test directory — expect ~10-30
   mechanical replacements per test file.

#### 14.D — Graph repository inflated-node method

The **graph** repository changes shape (this is step 12a, restated here
for completeness):

```python
class WorkflowGraphRepository:
    ...

    def node(
        self, session: Session, *,
        run_id: UUID, task_id: UUID,
    ) -> RunGraphNodeView:
        """Read one (run_id, task_id) row + inflate task_json into a
        Task via Task.from_definition(task_json, task_id=task_id).
        Returns a frozen
        RunGraphNodeView that wraps the inflated Task plus row
        metadata (status, level, parent_task_id, timestamps). The repo
        never returns raw JSON across the boundary.
        """
```

Today's `graph_repo.get_node(...)` returns a `RunGraphNode` ORM row —
the new method returns a `RunGraphNodeView` (defined in
[`02-persistence-and-identity.md`](02-persistence-and-identity.md)).
Keep the ORM-row method around as a private helper for cases where
the runtime really wants the raw row (status update writes); rename
it `_node_row` to make the intent clear.
15. **Refactor `worker_execute.py` to read the runs row only.** Stops
    calling `DefinitionRepository.task(...)` entirely; reads
    `RunGraphNodeView` from `graph_repo.node(...)`, then uses
    `task = node.task` and `worker = task.worker`. Evaluators are
    `task.evaluators`. Same shape for static and dynamic tasks (this is
    the pay-off — no static/dynamic branching or binding lookup in the
    job body).
16. **Add `WorkerContext.spawn_task` backed by `TaskManagementService`.**
    Signature is `spawn_task(task: Task, *, depends_on=())
    -> SpawnedTaskHandle` (fire-and-forget; `await_completion=True`
    deferred — see [`06-decisions-log.md#future-work`](06-decisions-log.md#future-work)).
    The child `Task` must already carry its concrete `worker`, `sandbox`,
    and `evaluators`; `TaskManagementService.add_subtask` writes its
    `task_json` directly to `run_graph_nodes`. Drop slug-based registry
    resolution. Add validator: reject static-on-dynamic dependency
    edges at experiment-define and at runtime edge insertion. See
    [`03-runtime.md#dynamic-spawning-what-changes-almost-nothing`](03-runtime.md#dynamic-spawning-what-changes-almost-nothing).
    `WorkerContext.spawn_task` calls `TaskManagementService.add_subtask`
    (single-target case) directly — no public service tier between
    them. The internal service stays public-when-imported-from-core
    today (no boundary enforcement); workers that need batch ops
    (`plan_subtasks`, `cancel_all_*`) import the service themselves.

16a. **Add the rest of the WorkerContext curated facade methods.** Once
    `spawn_task` is in place and the schema rewrite (step 14) has
    landed, add the remaining 7 single-target methods to
    `WorkerContext`, each delegating directly to
    `TaskManagementService` / `TaskInspectionService` /
    `RunResourceRepository`:

    | Method | Backing impl |
    |---|---|
    | `cancel_task(task_id)` | `TaskManagementService.cancel_task` |
    | `refine_task(task_id, *, description)` | `TaskManagementService.refine_task` |
    | `restart_task(task_id)` | `TaskManagementService.restart_task` |
    | `subtasks() -> Iterable[SubtaskInfo]` | `TaskInspectionService.list_subtasks` |
    | `descendants(*, max_depth=3)` | `TaskInspectionService.descendants` |
    | `get_task(task_id)` | `TaskInspectionService.get_subtask` |
    | `resources(*, scope='own')` | `RunResourceRepository.list_by_run` / `list_by_execution` (selecting the right repo method per scope) |

    Containment check (the target task is a descendant of
    `self.task_id`) lives on each `WorkerContext` mutation method —
    raises `ContainmentViolation` before delegating. Curation rule
    (single-target + high-frequency only) keeps batch / predicate /
    advanced ops off the facade; workers that need them import the
    internal service. The internal services are public-when-imported
    today; whether to enforce a boundary later is a follow-up.

## Phase 4: Criterion cleanup

17. **Drop `CriterionContext` proxy methods** *(audit #5)*.
    `Criterion.evaluate` takes `sandbox: Sandbox` directly.
    `CriterionContext` becomes pure data. Also delete
    `core/application/evaluation/criterion_runtime.py` entirely
    (`DefaultCriterionRuntime`, `CriterionRuntimeOptions`,
    `SandboxExpiredError` re-exports) — the runtime indirection has no
    purpose once `Sandbox` is the public contract that criteria call
    directly. Update `EvaluationService` /
    `InngestCriterionExecutor` to pass the public `Sandbox` (already
    in scope via the task) to `criterion.evaluate(...)` instead of
    constructing a `CriterionRuntime`.
18. **Move `Criterion.weight` / `score_spec` to a Rubric-level
    `WeightedCriterion` wrapper.** Free criteria from aggregation knowledge.

## What's deferred (not Phase 5 — not v1)

An earlier draft of this plan included a *Phase 5* that promoted three
new public service classes (`GraphMutator`, `GraphInspector`,
`ResourceInspector`) into `ergon_core.api`, enforced an
`ergon_builtins → core.application` import boundary, and migrated the
three in-tree consumers (`subtask_lifecycle_toolkit.py`,
`graph_toolkit.py`, workflow CLI) onto the new public surface. **Rolled
back as scope creep for v1.** The justification was "build the layer
before someone needs it"; we don't have an external consumer asking
for it, and adding it costs ~6 migration steps + 3 new classes + a
boundary test for purely speculative benefit. `WorkerContext` is the
public runtime surface; toolkits and the CLI keep their existing
`from ergon_core.core.application import …` lines untouched. When a
real third-party consumer arrives — or when an in-tree refactor
genuinely needs the boundary — promote then. See
[`06-decisions-log.md`](06-decisions-log.md) under
"Alternatives considered" for the rejected design.

External-run import (`ergon_ingestion/writers/external_run_writer.py`) is
also untouched — it already writes runs straight to the persistence
layer and doesn't go through the public API.

## Deletion checklist (reviewer)

The audit's deletions are easy to forget — they're things that work fine
if left in place, just as redundant parallel implementations of what's
now in `ergon_core.api`. Every grep below should return zero hits after
the PR lands. They're mechanical enough that a manual `git grep` pass
at review time catches anything that slipped through the per-step
descriptions.

```bash
# Audit #1 — Sandbox manager dies
git grep "BaseSandboxManager\|DefaultSandboxManager"
git grep "_sandbox_manager_classes\|_creation_locks\|_sandboxes\b"
git grep "terminate_sandbox_by_id"     # → only the new SandboxLifecycleHub callers
test ! -e ergon_core/ergon_core/core/infrastructure/sandbox/manager.py

# Audit #2 — WorkerSpec / ComponentRegistry die
git grep "class WorkerSpec\b"
git grep "ComponentRegistry\|register_builtins\|registry\.publish"
git grep "ComponentCatalogService\|ComponentCatalogEntry"
test ! -e ergon_core/ergon_core/api/registry.py
test ! -e ergon_core/ergon_core/core/domain/experiments/worker_spec.py

# Audit #3 — TaskSpec dies
git grep "class TaskSpec\b"
git grep "import_component_string"     # → only inside ergon_core/api/*/from_definition
git grep "evaluator_binding_keys\|worker_binding_key\|experiment_definition_task_assignments"
git grep "experiment_definition_workers\|experiment_definition_evaluators"
# → all should return zero hits in the authoring/runtime path; Task JSON now
#   owns worker/evaluator objects directly.

# Audit #5 — DefaultCriterionRuntime / CriterionRuntimeOptions die
git grep "DefaultCriterionRuntime\|CriterionRuntimeOptions"
test ! -e ergon_core/ergon_core/core/application/evaluation/criterion_runtime.py

# Audit #6 — Experiment lifts into ergon_core.api
test ! -e ergon_core/ergon_core/core/domain/experiments/experiment.py
git grep "from ergon_core\.core\.domain\.experiments import Experiment"
git grep "from ergon_core\.core\.domain\.experiments\.experiment import"
# → both should return zero hits; the canonical import is
#   `from ergon_core.api import Experiment`.
```

(Audit #4 — `Evaluator.from_definition` thinning `EvaluationService.prepare_dispatch`
— is a "did the inline assembly get removed" review check, not a deletion grep.
The `EvaluationService` class itself stays.)

If any of these return hits, the redesign has shipped a parallel
implementation of something already promoted into `ergon_core.api` —
fix before merge. The audit table above gives the public counterpart
each deletion pairs with.

## On acceptance

When this redesign moves from `active/` to `accepted/`, also:

- Confirm the [Deletion checklist](#deletion-checklist-reviewer)
  passes (every grep returns zero hits, every "should not exist" file
  is gone). If anything's left, it's a parallel implementation of
  something now in `ergon_core.api` and needs to be cleaned up before
  graduation.
- Update [`docs/architecture/01_public_api.md`](../../../architecture/01_public_api.md)
  sections **core abstractions**, **invariants**, **extension points**,
  **anti-patterns** to reflect the new surface.
- Update [`docs/architecture/cross_cutting/sandbox_lifecycle.md`](../../../architecture/cross_cutting/sandbox_lifecycle.md)
  to formalize per-task sandbox-from-spec.
- Add an implementation plan in `docs/superpowers/plans/` covering the
  18-step migration above.
- Close any related bug files in `docs/bugs/open/` (the
  [`2026-04-23-inngest-function-failures.md`](../../../bugs/open/2026-04-23-inngest-function-failures.md)
  `task_id`/`node_id` resolution is subsumed by step 15).
- Graduate the reference docs (`01-api-surface.md`,
  `02-persistence-and-identity.md`, `03-runtime.md`) into
  `docs/architecture/` proper. Move this folder to a
  `decided/` or `accepted/` archive sibling.
