# PR 11 — Deletion And Final Schema

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Delete all transition bridges and replace additive migrations with
one final v2 initial schema.

**Architecture:** This is cleanup only. No new behavior lands here except
guards that prevent deleted symbols from returning.

**Tech Stack:** source deletion, SQLModel final schema, Alembic reset,
architecture tests.

> **Note: PR 6.5 (and the post-PR-6.5 cleanup) already deleted several
> things this plan used to claim.** Anything in the list below is **not**
> in PR 11's deletion list anymore:
> - The public `Experiment` class (`ergon_core.api.experiment.Experiment`) — already gone (PR 6.5).
> - `ExperimentRecord` SQLModel + `experiments` table — already renamed
>   to `BenchmarkDefinitionRecord` / `benchmark_definitions` (PR 6.5).
>   **PR 11 KEEPS `BenchmarkDefinitionRecord`** — the rename made it the
>   canonical v2 telemetry row for unstarted/launched experiments.
> - `persist_definition` top-level function — already renamed to
>   `persist_benchmark` (PR 6.5).
> - `ExperimentDefineRequest`, `define_benchmark_experiment`,
>   `BUILTIN_EXPERIMENT_FACTORIES` — already deleted (PR 6.5 Phase 2).
> - CLI authoring commands (`ergon experiment define`, `ergon experiment run`) — already deleted (PR 6.5).
> - Top-level `ergon_builtins/sandboxes/` and `toolkits/` dirs — already deleted (PR 6.5).
> - `ExperimentService` class — already deleted (post-PR-6.5 cleanup); replaced by module-level `run_experiment` in `application/experiments/service.py`.
> - Unused `name`/`description`/`created_by` kwargs on `persist_benchmark` — already dropped (post-PR-6.5 cleanup).
>
> What PR 11 still owns:
> - The **domain** `Experiment` class (different class — see below),
>   `TaskSpec`, the per-benchmark `sandbox_manager.py` files, the
>   per-benchmark `_legacy_workers.py` files (created by PR 6.5 / 10a /
>   10b / 10c specifically as PR 11 deletion targets), the legacy
>   worker fallback chain.
> - The **symmetric** legacy evaluator fallback: `_legacy_evaluator_bridge.py`
>   was restored after PR 5's premature retirement; PR 11 deletes it
>   alongside `_legacy_worker_bridge.py` (same deletion gate: every
>   benchmark — production + smoke fixture — on object-bound `Task`).
> - The PR 1 task-snapshot bridge helpers: `_definition_task_snapshot`
>   and `_dynamic_task_snapshot` in `core/application/graph/repository.py`
>   (docstrings already mark them for PR 11 deletion), plus the
>   `task_json=task.task_json or _definition_task_snapshot(...)` fallback
>   in `initialize_from_definition`.
> - The v1 `_ExperimentDefinitionWriter` class in `definition_writer.py`
>   (docstring already marks it for PR 11 deletion).
> - The `terminate_sandbox_by_id` helper — but PR 4 moved its caller out
>   of `execute_task.py` into a sibling Inngest function at
>   `core/application/jobs/sandbox_cleanup.py` (triggered by
>   `task/completed` / `task/failed`). PR 11 either keeps the sandbox
>   cleanup function (if external sandboxes are still in scope) or
>   deletes it alongside the legacy bridges.
> - The final schema/identity collapse.

---

## Files To Delete

```text
ergon_core/ergon_core/api/registry.py
ergon_core/ergon_core/core/domain/experiments/                       # whole package: Experiment, WorkerSpec, validation
ergon_core/ergon_core/core/application/components/catalog.py         # ComponentCatalogService (audit first)
ergon_core/ergon_core/core/application/components/                   # whole package once catalog.py is gone
ergon_core/ergon_core/core/application/experiments/repository.py     # DefinitionRepository (after prepare_run inlines its one remaining caller)
ergon_core/ergon_core/core/persistence/saved_specs/
ergon_core/ergon_core/core/application/evaluation/executors.py
ergon_core/ergon_core/core/application/evaluation/inngest_executor.py
ergon_core/ergon_core/core/application/jobs/check_evaluators.py
ergon_core/ergon_core/core/application/jobs/_legacy_worker_bridge.py
ergon_core/ergon_core/core/application/jobs/_legacy_evaluator_bridge.py
ergon_builtins/ergon_builtins/registry.py
ergon_builtins/ergon_builtins/registry_core.py
ergon_builtins/ergon_builtins/registry_data.py
```

**Note (post-reconciliation):** earlier drafts of this plan listed
`execute_task.py`, `sandbox_setup.py`, and `persist_outputs.py` as
deletion targets on the theory that PR 4 would collapse them into
`worker_execute`'s body. **That collapse did not happen.** PR 4 kept
the four-function orchestration (`execute_task` → `sandbox_setup` →
`worker_execute` → `persist_outputs` + per-evaluator `evaluate_task_run`
fanout) and added `sandbox_cleanup` as a sibling triggered by
`task/completed` / `task/failed`. Those four files are part of the
final v2 shape, not deletion targets.

The two legacy bridge files (`_legacy_worker_bridge.py`,
`_legacy_evaluator_bridge.py`) ARE deletion targets once every benchmark
(production + smoke fixture) migrates to object-bound `Task`. The
deletion gate is "no benchmark still produces `TaskSpec`" — PR 6
migrated minif2f, PR 10a/b/c migrate swebench/researchrubrics/gdpeval
plus their matching smoke fixtures. PR 11 verifies the call sets are
empty, then `git rm`s both files and deletes the matching
`if worker is None:` / `if not task.evaluators:` branches in
`worker_execute.py` / `evaluate_task_run.py`.

**Audit-before-delete:**

- `ComponentCatalogService` and the `components/` package — PR 5 forbids
  `worker_execute` from importing it; after PR 10c every builtin uses
  object-bound `Task`. Confirm zero production callers remain before the
  `git rm`. If a dashboard or CLI listing still uses it, decide whether
  to migrate or keep the package.
- `DefinitionRepository` — PR 3 removes its `worker_execute` caller; PR 4
  removes its `evaluate_task_run` caller. The remaining call site
  (`prepare_run` copying definition→run-tier) should inline the one
  method it needs and delete the repository class.

**Do NOT delete:**

- `ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py` —
  reshaped by PR 4 to the thin id-only payload + `graph_repo.node`
  loader. The file, the Inngest function, the slug, and the
  registration all survive. Only the v1 body was removed (in PR 4),
  not the file itself.

Delete old sandbox manager files only after each benchmark has a typed sandbox subclass:

```text
ergon_builtins/ergon_builtins/benchmarks/minif2f/sandbox_manager.py
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_manager.py
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_manager_support.py
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/sandbox_manager.py
ergon_builtins/ergon_builtins/benchmarks/gdpeval/sandbox_manager.py     # PR 10c renamed from sandbox.py
ergon_builtins/ergon_builtins/benchmarks/gdpeval/sandbox_utils.py
```

Delete per-benchmark `_legacy_workers.py` files (created by PR 6.5 / 10a / 10b / 10c specifically as PR 11 deletion targets — they hold the legacy worker classes that the v1 registry strings still resolve to):

```text
ergon_builtins/ergon_builtins/benchmarks/minif2f/_legacy_workers.py
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/_legacy_workers.py    # if PR 10a created one
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/_legacy_workers.py      # if PR 10b created one
ergon_builtins/ergon_builtins/benchmarks/gdpeval/_legacy_workers.py              # if PR 10c created one
```

(Some verticals may not have a `_legacy_workers.py` if their legacy worker block was already minimal.  Check before `git rm`.)

## Required Code Deletions

**Public API and v1 abstractions:**

- Remove `TaskSpec` from `ergon_core/ergon_core/api/benchmark/task.py`.
- Remove `Worker.from_buffer` (replaced by nothing — had no callers).
- Remove `Worker.validate()`. PR 5 renamed it to `validate_runtime_deps`;
  grep-confirm the old name is gone from these callsites:
  `ergon_core.api.rubric.rubric.Rubric.validate`,
  `ergon_core.core.domain.experiments.validation`,
  `ergon_core.core.application.experiments.definition_writer.persist_benchmark`  # renamed by PR 6.5,
  `ergon_core.core.application.experiments.launch.launch_run`,
  `ergon_builtins.benchmarks.gdpeval.rubric`.
- Remove the **domain** `Experiment` (`ergon_core.core.domain.experiments.Experiment`).  PR 6.5 deleted the public `Experiment` class; PR 11 deletes the remaining domain-layer class.  After PR 11, **there is no `Experiment` class anywhere** — the word survives only as a `str | None` column on `BenchmarkDefinitionRecord` (the "experiment tag" introduced by PR 6.5).
- Remove `EvaluateTaskRunRequest` (the v1 multi-field payload). The
  replacement is `TaskEvaluateRequest` (id-only), already in use since
  PR 4.
- Remove `_task_to_definition_json` support for `TaskSpec` (the function
  itself is the `_legacy` branch; PR 11 deletes the function).
- Remove `_definition_task_snapshot` and `_dynamic_task_snapshot` from
  `core/application/graph/repository.py` (PR 1 bridge helpers; their
  docstrings already mark them as PR 11 deletion targets). Then narrow
  `initialize_from_definition` from
  `task_json=task.task_json or _definition_task_snapshot(...)` to just
  `task_json=task.task_json`.
- Remove the v1 `_ExperimentDefinitionWriter` class from
  `definition_writer.py` (its docstring already marks it for PR 11
  deletion). The class is the leftover v1 launch path; the canonical
  v2 path is the module-level `persist_benchmark` function.
- Remove `terminate_sandbox_by_id`. **PR 4 moved this out of
  `execute_task.py`'s deleted `try/finally`** — it now lives in the
  sibling Inngest job at
  `ergon_core/core/application/jobs/sandbox_cleanup.py` (plus the
  matching handler at
  `core/infrastructure/inngest/handlers/sandbox_cleanup.py`). If the
  final v2 still terminates external sandboxes after each task, keep
  the `sandbox_cleanup.py` job and only delete the helper if a more
  direct API replaces it; otherwise delete the helper, the job, AND
  the handler.

**Runtime identity and DTOs:**

- Remove `node_id` as runtime identity from event payloads and DTOs.
- Remove `PreparedTaskExecution.node_id`, `.definition_task_id`,
  `.worker_type`, `.assigned_worker_slug`, `.model_target`. PR 3 carried
  these as a bridge; after PR 5 makes `task.worker` canonical and PR 11
  collapses identity, they're dead. The DTO simplifies to
  `run_id, definition_id, task_id, task_slug, task_description, benchmark_type, execution_id`.
- Remove `_prepare_legacy_definition` from `TaskExecutionService`.
- Retire the legacy worker fallback chain. PR 5 retired the *in-body*
  `_worker_from_payload_bridge` but kept a narrow legacy fallback at
  `core/application/jobs/_legacy_worker_bridge.py` for unmigrated
  benchmarks. PR 6 / PR 10a / PR 10b / PR 10c migrate the four builtins
  (minif2f, swebench, researchrubrics, gdpeval) **plus the matching
  smoke fixtures in `tests/fixtures/smoke_components/benchmarks.py`** —
  after PR 10c, no benchmark (production or fixture) still produces
  `TaskSpec`. PR 11 performs the final deletion (see Task 1.5 below).
  The grep for `_worker_from_payload_bridge` must come back empty.
- Retire the **symmetric** legacy evaluator fallback chain. Post-PR-5
  cleanup restored `core/application/jobs/_legacy_evaluator_bridge.py`
  (which PR 5 had prematurely deleted) as the eval-side counterpart to
  `_legacy_worker_bridge.py`. Same deletion gate, same migration
  sequence: PR 6 / 10a / 10b / 10c remove each benchmark from the call
  set. PR 11 `git rm`s the file and deletes the
  `if not task.evaluators:` fallback branch in
  `evaluate_task_run.py`. Add the eval-side `git rm` to Task 1.5
  alongside the worker-side `git rm`.

**Schema (run-tier collapse — composite PK `(run_id, task_id)`):**

- Drop `run_graph_nodes.id` column. New composite PK is
  `(run_id, task_id)` per `02-persistence-layer.md` §2.
- Drop `run_graph_nodes.definition_task_id`. Identity is `task_id` only.
- Drop `run_graph_nodes.parent_node_id`. Rename to `parent_task_id`
  (per PR 9 § "In the current schema this maps to ... PR 11 renames
  columns").
- Rename `run_graph_edges.source_node_id` → `source_task_id` and
  `target_node_id` → `target_task_id`.
- Drop `run_graph_edges.definition_dependency_id` (mirror of
  `definition_task_id` for edges).
- Drop `RunTaskExecution.node_id`; rename to `task_id`. Drop
  `RunTaskExecution.definition_task_id`.
- Drop the matching columns on `RunTaskEvaluation`
  (`node_id`, `definition_task_id`).
- ~~Remove `ExperimentRecord` from telemetry models~~ — **already done by PR 6.5** (renamed to `BenchmarkDefinitionRecord`).  Task 2's schema reset uses the renamed model.

**Inngest events:**

- Audit whether `task/completed` still has a real consumer after PR 4.
  Current consumer chain in tree:
  `ergon_core.core.application.jobs.propagate_execution` listens to
  `task/completed` for graph propagation — that's still load-bearing in
  v2, so the event survives. The audit is to grep for stale listeners
  and confirm `propagate_execution` is the only one.

## Final Schema Shape

`RunGraphNode` final identity:

```python
class RunGraphNode(SQLModel, table=True):
    __tablename__ = "run_graph_nodes"

    run_id: UUID = Field(foreign_key="runs.id", primary_key=True)
    task_id: UUID = Field(primary_key=True)
    parent_task_id: UUID | None = Field(default=None, index=True)
    # NOT NULL with no default — task_json is the single source of truth
    # for what to execute. An insert without a snapshot is a programming
    # error; the DB rejects it. The PR 1 additive migration had a
    # `server_default='{}'` only for the additive backfill; PR 11 drops
    # it because every legitimate writer (definition copy in PR 1,
    # object-bound model_dump in PR 5, dynamic spawn in PR 9) sets it
    # explicitly.
    task_json: dict = Field(sa_column=Column(JSON, nullable=False))
    status: str = Field(index=True)
    level: int = 0
    is_dynamic: bool = False
    last_error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
```

`BenchmarkDefinitionRecord` final metadata (renamed from `ExperimentDefinition` by PR 6.5; PR 11 finalises field shape):

```python
class BenchmarkDefinitionRecord(SQLModel, table=True):
    __tablename__ = "benchmark_definitions"     # renamed by PR 6.5

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: str | None = None
    benchmark_type: str = Field(index=True)
    benchmark_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    experiment: str | None = Field(default=None, index=True)     # PR 6.5 added — the experiment-tag column
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_by: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
```

Notes for the schema reset:
- The `experiment_json` field from the v1 shape is gone — there is no `Experiment` class to persist.  All metadata lives in `metadata_json` or directly in `benchmark_json`.
- The `experiment: str | None` column is PR 6.5's tag for grouping related definitions (e.g. ablation studies).  It is **not** a foreign key — just an indexed string column.

## Task 1: Delete Symbols

- [ ] Remove files listed above with `git rm`.
- [ ] Remove exports from `__init__.py` files.
- [ ] Run `rg` for each final deleted symbol and remove remaining production
      hits.

Commands:

```bash
rg "TaskSpec|WorkerSpec|ComponentRegistry|saved_specs|ExperimentRecord|definition_task_id|EvaluateTaskRunRequest|CriterionExecutor|from_buffer|terminate_sandbox_by_id" ergon_core ergon_builtins ergon_cli
```

Note: `evaluate_task_run` is intentionally **not** in this grep — the
function name survives per Δ.4. Run a second grep to confirm
`evaluate_task_run` IS still present in production code:

```bash
rg "evaluate_task_run" ergon_core ergon_builtins ergon_cli
```

Expected: hits in `jobs/evaluate_task_run.py` (the reshaped body),
`infrastructure/inngest/registry.py` (the registration), and the
walkthrough/regression tests.

Expected: only docs and deleted-symbol tests contain hits.

## Task 1.3: Shrink `CriterionContext` To A Pure Data Carrier

**Deferred from PR 5.** The PR 5 plan specified removing the 12 runtime
proxy methods from `CriterionContext` alongside the `_runtime` PrivateAttr
and `sandbox_id` field. This was not done — criteria in PRs 6, 10a, 10b,
10c still call `context.run_command(...)` via the legacy proxy. PR 11
does the removal once every criterion body has been migrated to
`context.task.sandbox.run_command(...)`.

**Files:**

- Modify: `ergon_core/ergon_core/api/criterion/context.py`

- [ ] **Step 1: Confirm every criterion caller uses `context.task.sandbox` not `context.run_command`**

```bash
rg "context\.run_command\|context\.write_file\|context\.read_resource\|context\.upload_files\|context\.ensure_sandbox\|context\.execute_code\|context\.cleanup\|context\.list_resources\|context\.get_all_files" ergon_core ergon_builtins
```

Expected: zero production hits (only docs/tests).

- [ ] **Step 2: Remove proxy methods and legacy private attrs from `CriterionContext`**

Delete from `ergon_core/ergon_core/api/criterion/context.py`:
- `_runtime: CriterionRuntime | None` PrivateAttr and all blocks that set it
- `sandbox_id: str | None` field
- `with_runtime(...)` classmethod
- `has_runtime` property
- `runtime` property
- `_require_runtime()` method
- All proxy methods: `ensure_sandbox`, `upload_files`, `write_file`, `run_command`, `execute_code`, `cleanup`, `read_resource`, `read_resource_by_id`, `list_resources`, `get_all_files_for_task`, `list_output_files`

The resulting class is a pure data carrier:

```python
class CriterionContext(BaseModel):
    task: Task
    worker_result: WorkerOutput
    run_id: UUID
    execution_id: UUID
```

- [ ] **Step 3: Remove `CriterionRuntime` import from `context.py`**

After Step 2, `CriterionRuntime` has no callers in `context.py`. Remove the import.
Check it has no remaining callers in production:

```bash
rg "CriterionRuntime" ergon_core ergon_builtins ergon_cli
```

Expected: zero production hits.

## Task 1.4: Add `Criterion.from_definition` Classmethod

**Deferred from PR 5.** `Task.from_definition`'s object-bound evaluators
path routes rubric-shaped evaluator JSON through `Evaluator.from_definition`,
which handles `Rubric` subclasses fine (`criteria` are `exclude=True` so
they don't appear in the JSON and don't need deserialization). However,
bare `Criterion` subclasses that might be stored directly as evaluators
would have no `from_definition` entry point. Add it so the pattern is
complete and consistent before the PR 11 audit.

**Files:**

- Modify: `ergon_core/ergon_core/api/criterion/criterion.py`

- [ ] **Step 1: Add `from_definition` classmethod**

```python
@classmethod
def from_definition(cls, criterion_json: TaskDefinitionJson) -> "Criterion":
    """Reconstruct a Criterion subclass from ``_type``-discriminated JSON.

    Mirrors Worker.from_definition / Sandbox.from_definition. Called by
    Task.from_definition when an evaluator entry resolves to a bare
    Criterion subclass (not a Rubric).
    """
    criterion_type = criterion_json.get("_type")
    if not isinstance(criterion_type, str):
        raise ValueError(
            f"Criterion snapshot is missing the required `_type` discriminator "
            f"(got {type(criterion_type).__name__}). Every persisted criterion "
            f"must carry `_type`."
        )
    CriterionCls = import_component(criterion_type)
    return cast("Criterion", CriterionCls.model_validate(criterion_json))
```

Note: this requires `Criterion` to be a Pydantic `BaseModel`. If it isn't
yet at PR 11 time, defer to a dedicated "Criterion Pydantic migration" PR
and leave a `TODO(PR N)` comment here instead.

## Task 1.5: Retire The Legacy Worker And Evaluator Fallbacks

After PR 10c lands (production benchmarks migrated) AND each PR 10x has
migrated its matching smoke fixture in
`tests/fixtures/smoke_components/benchmarks.py`, no benchmark anywhere
still returns `TaskSpec`. Both `_legacy_worker_bridge` and
`_legacy_evaluator_bridge` are unreachable. PR 11 deletes both files
plus their matching fallback branches.

- [ ] **Step 1: Delete the bridge modules**

```bash
git rm ergon_core/ergon_core/core/application/jobs/_legacy_worker_bridge.py
git rm ergon_core/ergon_core/core/application/jobs/_legacy_evaluator_bridge.py
```

- [ ] **Step 2: Delete the `if worker is None:` fallback in `worker_execute.py`**

Remove the `if worker is None:` block in
`ergon_core/ergon_core/core/application/jobs/worker_execute.py` that
imports `legacy_worker_from_payload`. After PR 10c (incl. smoke
fixtures), `task.worker` is always non-None for every benchmark; the
branch is unreachable and the import is dead.

- [ ] **Step 3: Delete the `if not task.evaluators:` fallback in `evaluate_task_run.py`**

Symmetric to Step 2. Remove the `else` branch in
`ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py` that
imports `legacy_evaluator_from_binding` and
`legacy_inject_criterion_runtime`. After PR 10c (incl. smoke fixtures),
`task.evaluators` is always populated for every benchmark; the eval-side
fallback is unreachable.

- [ ] **Step 4: Drop the bridge entries from the dead-path audit `_XFAIL_BY_SYMBOL`**

In `ergon_core/tests/unit/architecture/test_dead_path_audit.py`, remove
any entries for `_worker_from_payload_bridge`, `_legacy_worker_bridge`,
`_evaluator_bridge`, or `_legacy_evaluator_bridge` from
`_XFAIL_BY_SYMBOL`. Folded into the "Empty `_XFAIL_BY_SYMBOL`" sweep in
Task 4 Step 2 — call it out here so the deletion isn't lost when the
dict is collapsed.

Verify:

```bash
rg "_worker_from_payload_bridge|_legacy_worker_bridge|legacy_worker_from_payload|_evaluator_bridge|_legacy_evaluator_bridge|legacy_evaluator_from_binding|legacy_inject_criterion_runtime" \
  ergon_core ergon_builtins ergon_cli tests
```

Expected: only docs hits remain.

## Task 2: Reset Migration Chain

This step **wipes every revision currently on disk** under
`ergon_core/migrations/versions/`. As of the time this plan was written
that's 27 revisions, including `5f01559f2bc3_initial_schema_v2.py` and every
additive migration introduced by PRs 1 and 7. The workshop decision was
"no prod data," so this is safe in production. It is **not** safe for
contributors' local databases without an explicit downgrade — see the
developer-facing instructions below.

### Revisions to be deleted

Run this once before the destructive step to capture an inventory in the PR
description (the list will be longer than the snapshot below by the time
this PR lands, but the snapshot establishes the lower bound):

```bash
ls ergon_core/migrations/versions/*.py | sort
```

Snapshot at the time of writing (delete all of these):

```text
0a1b2c3d4e5f_add_thread_summary.py
11f1497a53e8_add_batch_operation_id_to_run_graph_.py
307fcca3a621_drop_run_task_state_events.py
4a71a3dc2ef5_add_blocked_to_taskexecutionstatus_enum.py
5f01559f2bc3_initial_schema_v2.py
7c9661121a86_add_triggered_by_mutation_id_to_run_.py
84519b3f8431_add_cancelled_to_taskexecutionstatus_enum.py
925ff225d97e_add_sandbox_id_to_run_task_executions.py
a1b2c3d4e5f6_unique_thread_run_topic.py
a2b3c4d5e6f7_add_copied_from_resource_id.py
a66564b89aac_rename_output_text_to_final_assistant_.py
b1c2d3e4f5a6_add_experiment_records.py
b5b36e45e5e6_add_containment_and_cancelled.py
c1d2e3f4a5b6_add_sandbox_event_tables.py
c2d3e4f5a6b7_add_sandbox_dependency_fields.py
d1e2f3a4b5c6_add_component_catalog.py
d4f5a6b7c8d9_drop_run_generation_turns.py
e2f3a4b5c6d7_add_import_reducer_tables.py
e5f6a7b8c9d0_normalize_evaluation_summary_nulls.py
e89c6c427de4_drop_run_actions_add_turn_timing.py
e96c85469899_rename_task_key_to_task_slug_and_.py
f1a2b3c4d5e6_add_run_context_events.py
f6a7b8c9d0e1_key_task_evaluations_by_node.py
f9075c2ddbc9_run_resource_append_only_log.py
```

Plus the additive migrations introduced earlier in this program:

- `aabbccdd0001_add_run_graph_task_json.py` (PR 1)
- `aabbccdd0002_add_worker_output_json.py` (PR 4)
- `aabbccdd0003_add_definition_task_json.py` (PR 5)
- `aabbccdd0004_definition_metadata_and_launch.py` (PR 7)
- (any `aabbccdd0005+` additive migrations PR 10a/10b/10c may have added)

### Developer-facing downgrade step

Every contributor (including CI runners with persistent volumes) must
downgrade to `base` **before** pulling this PR, because the new initial
migration is not a descendant of any existing revision and Alembic will
refuse to apply it on top of a live history.

The PR description must include this exact block:

```text
## BREAKING: developer DB reset required

Before pulling this PR, run on every machine that has an Ergon dev DB:

    uv run alembic -c ergon_core/alembic.ini downgrade base
    docker compose down -v   # if you use the docker stack with named volumes

After pulling:

    uv run alembic -c ergon_core/alembic.ini upgrade head

There is no upgrade path from v1 data; the workshop decision was "no prod
data," and this PR enforces it.
```

Add the same notice as a comment at the top of the new initial migration so
`alembic history` readers can find it later.

### Steps

- [ ] **Step 1: Inventory existing revisions**

```bash
ls ergon_core/migrations/versions/*.py | sort > /tmp/v2_pre_reset_revisions.txt
wc -l /tmp/v2_pre_reset_revisions.txt
```

Expected: matches the snapshot above plus any later additions. Attach the
file to the PR description.

- [ ] **Step 2: Delete all existing revisions**

```bash
git rm ergon_core/migrations/versions/*.py
```

- [ ] **Step 3: Create the final initial migration**

Create `ergon_core/migrations/versions/00000000_initial_v2.py`:

```python
"""Initial v2 schema.

# BREAKING: this migration is not a descendant of any v1 or v2-transition
# revision. Contributors must run `alembic downgrade base` against any DB
# created before PR 11 lands. There is no data preservation path.
"""

revision = "00000000_initial_v2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Schema from 02-persistence-layer.md plus the RunGraphNode and
    # ExperimentDefinition final shapes defined in this PR. Generate this
    # body with `alembic revision --autogenerate` against a fresh DB after
    # all model deletions in Task 1 are applied, then hand-audit so that:
    #   - run_graph_nodes uses (run_id, task_id) as the composite PK
    #   - parent_task_id is the only parent reference (no parent_node_id)
    #   - task_json is NOT NULL with NO server_default (every insert must
    #     set it explicitly — the additive backfill default from PR 1 is
    #     gone)
    #   - no experiment_records table exists
    #   - no saved_specs table exists
    ...


def downgrade() -> None:
    raise NotImplementedError(
        "v2 initial migration intentionally has no downgrade. To roll back, "
        "restore from the snapshot taken in Task 2 Step 1."
    )
```

The PR author runs `alembic revision --autogenerate -m "initial v2"`
against a clean DB **after** Task 1 deletions, then renames the file to
`00000000_initial_v2.py` and reviews the body against the criteria above.

- [ ] **Step 4: Verify single head**

```bash
uv run alembic -c ergon_core/alembic.ini heads
```

Expected: exactly one head, `00000000_initial_v2`.

- [ ] **Step 5: Run Alembic upgrade against a fresh dev DB**

```bash
docker compose down -v
docker compose up -d postgres
uv run alembic -c ergon_core/alembic.ini upgrade head
```

Expected: schema creates with no references to deleted tables/columns; the
following grep is empty:

```bash
uv run python -c "
from sqlalchemy import create_engine, inspect
import os
engine = create_engine(os.environ['DATABASE_URL'])
inspector = inspect(engine)
forbidden = {'experiment_records', 'saved_specs', 'definition_task_id'}
present = set(inspector.get_table_names())
columns = {col['name'] for t in present for col in inspector.get_columns(t)}
assert not (forbidden & (present | columns)), forbidden & (present | columns)
print('clean')
"
```

### CI Invariant: Exactly One Alembic Head

**Files:**

- Create: `ergon_core/tests/unit/architecture/test_single_alembic_head.py`

```python
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]


def test_alembic_has_exactly_one_head() -> None:
    """Guards against migration chain forks introduced by stacked v2 PRs."""

    result = subprocess.run(
        [
            "uv",
            "run",
            "alembic",
            "-c",
            str(ROOT / "ergon_core" / "alembic.ini"),
            "heads",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    head_lines = [
        line for line in result.stdout.strip().splitlines() if line.strip()
    ]
    assert len(head_lines) == 1, (
        f"Expected exactly one Alembic head, got: {head_lines}"
    )
    assert head_lines[0].split()[0] == "00000000_initial_v2", (
        f"Unexpected head revision: {head_lines[0]!r}"
    )
```

Wire this guard into `pnpm run check:be` so a stacked PR that re-introduces
the additive migration chain fails fast.

## Task 3: Deleted Symbol Guard

**Files:**

- Create: `ergon_core/tests/unit/architecture/test_no_deleted_v2_symbols.py`

- [ ] **Step 1: Add guard**

```python
DELETED_SYMBOLS = (
    "TaskSpec",
    "WorkerSpec",
    "ComponentRegistry",
    "saved_specs",
    "ExperimentRecord",                 # PR 6.5 renamed to BenchmarkDefinitionRecord
    "ExperimentDefineRequest",          # PR 6.5 deleted
    "BUILTIN_EXPERIMENT_FACTORIES",     # PR 6.5 deleted
    "define_benchmark_experiment",      # PR 6.5 deleted
    "persist_definition",               # PR 6.5 renamed to persist_benchmark
    "class Experiment",                 # PR 6.5 deleted public; PR 11 deletes domain class
    "class ExperimentService",          # post-PR-6.5 cleanup deleted the facade
    "_evaluator_bridge",                # PR 5 retired; restored as _legacy_evaluator_bridge
    "_legacy_worker_bridge",            # PR 11 Task 1.5
    "_legacy_evaluator_bridge",         # PR 11 Task 1.5
    "_definition_task_snapshot",        # PR 1 bridge helper, PR 11 deletes
    "_dynamic_task_snapshot",           # PR 1 bridge helper, PR 11 deletes
    "_ExperimentDefinitionWriter",      # v1 leftover, docstring marks PR 11
    "definition_task_id",
    "EvaluateTaskRunRequest",
    "CriterionExecutor",
    "InngestCriterionExecutor",
    "from_buffer",
    "terminate_sandbox_by_id",
)
# evaluate_task_run is intentionally NOT in DELETED_SYMBOLS. Per Δ.4 it
# survives as the per-evaluator fanout target reshaped in PR 4.
# persist_benchmark, BenchmarkDefinitionRecord, and the experiment string
# column are also NOT deleted — they're PR 6.5's replacements.
KEPT_RESHAPED_SYMBOLS = (
    "evaluate_task_run",
    "TaskEvaluateRequest",
    "persist_benchmark",                # PR 6.5 introduced
    "BenchmarkDefinitionRecord",        # PR 6.5 introduced
)


def test_deleted_v2_symbols_do_not_exist_in_production_code() -> None:
    offenders = []
    for root in SEARCH_ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text()
            for symbol in DELETED_SYMBOLS:
                if symbol in text:
                    offenders.append(f"{path.relative_to(ROOT)} contains {symbol}")
    assert offenders == []
```

Allow this test file itself and docs.

## Task 4: Flip Remaining XFails And Verify Empty Ledgers

**Files:**

- Modify: `ergon_core/tests/unit/architecture/test_v2_final_state_ledger.py`
- Modify: `ergon_core/tests/unit/architecture/test_dead_path_audit.py`
- Modify: `ergon_core/tests/unit/architecture/test_no_type_circumventors.py`
- Modify: `ergon_core/tests/unit/architecture/test_repository_layer_conventions.py`
- Modify: `ergon_core/tests/unit/architecture/test_repository_companion_files.py`
- Modify: `ergon_core/tests/unit/architecture/test_no_dead_repository_methods.py`
- Modify: `ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py`

PR 11 is the deletion gate — by definition every remaining xfail in the
final-state ledger, dead-path audit, no-type-circumventors ledger,
repository ledgers, walkthrough smoketest, and identity invariants
flips green here.

- [ ] **Step 1: Empty `_XFAIL_BY_NAME`**

In `test_v2_final_state_ledger.py`, delete every remaining entry from
`_XFAIL_BY_NAME` so the dict is empty:

```python
_XFAIL_BY_NAME: dict[str, str] = {}
```

The entries removed in this PR are:

```python
"prepare_definition_helper_is_removed"
"criterion_executor_is_removed"
"saved_specs_package_is_removed"
"run_graph_node_has_no_definition_task_id_column"
"worker_from_buffer_is_removed"
"terminate_sandbox_by_id_is_removed"
```

- [ ] **Step 2: Empty `_XFAIL_BY_SYMBOL`**

In `test_dead_path_audit.py`, delete every remaining entry from
`_XFAIL_BY_SYMBOL` so the dict is empty:

```python
_XFAIL_BY_SYMBOL: dict[str, str] = {}
```

The entries removed in this PR are:

```python
"saved_specs"
"Worker.from_buffer"
"CriterionExecutor"
"InngestCriterionExecutor"
"_prepare_legacy_definition"
"terminate_sandbox_by_id"
```

- [ ] **Step 3: Flip remaining smoketest case**

In `test_walkthrough_smoketest.py`, remove the
`@pytest.mark.xfail(reason="PR 11: full v2 lifecycle ...")` from
`test_run_completion_releases_every_acquired_sandbox` and implement the
real body: drive a three-task run through the test Inngest driver,
assert one acquire and one release per task in
`run_resource_events` (or the equivalent sandbox-event table), with no
release coming from the per-run cleanup path.

- [ ] **Step 4: Add the "no xfails remain" architecture guard**

Append to `test_v2_final_state_ledger.py`:

```python
def test_no_v2_invariants_are_still_xfailed() -> None:
    """PR 11 completion bar: every invariant in FINAL_STATE_ASSERTIONS
    has landed. Empty `_XFAIL_BY_NAME` confirms the program is done."""

    assert _XFAIL_BY_NAME == {}, (
        f"v2 program incomplete — invariants still xfailed: "
        f"{sorted(_XFAIL_BY_NAME)}"
    )
```

Append to `test_dead_path_audit.py`:

```python
def test_no_dead_paths_are_still_xfailed() -> None:
    """PR 11 completion bar: every v1 dead path has been deleted."""

    assert _XFAIL_BY_SYMBOL == {}, (
        f"v2 program incomplete — dead paths still xfailed: "
        f"{sorted(_XFAIL_BY_SYMBOL)}"
    )
```

- [ ] **Step 2.5: Empty `_KNOWN_EXEMPTIONS`**

In `test_no_type_circumventors.py`, delete every remaining entry from
`_KNOWN_EXEMPTIONS` so the dict is empty:

```python
_KNOWN_EXEMPTIONS: dict[tuple[str, str], str] = {}
```

The only `getattr`/`hasattr` sites surviving past PR 11 are the
legitimate exemptions carrying a `# typing:` comment (the qualname
walks in `_import_component`, any external-SDK boundary). Every
formerly-violating production site has been fixed by an earlier PR per
the schedule in `00-program.md` "Ledger Files".

Append to `test_no_type_circumventors.py`:

```python
def test_no_known_type_circumventor_exemptions_remain() -> None:
    """PR 11 completion bar: every transitional getattr/hasattr in
    production code has either been replaced with typed access or
    annotated with a `# typing:` comment. The exemption dict is empty."""

    assert _KNOWN_EXEMPTIONS == {}, (
        f"v2 program incomplete — type-circumventor exemptions remain: "
        f"{sorted(_KNOWN_EXEMPTIONS)}"
    )
```

Also flip the repository-ledger completion bars (added by PR 0.5,
xfailed until now):

In `test_repository_layer_conventions.py` (or wherever
`_KNOWN_VIOLATORS` lives — single shared dict across the two repo
guard files), delete every remaining entry and remove the
`@pytest.mark.xfail` decorator from
`test_no_repository_violators_remain`:

```python
def test_no_repository_violators_remain() -> None:
    assert _KNOWN_VIOLATORS == {}, (
        f"Repository layer cleanup incomplete — violators remain: "
        f"{sorted(_KNOWN_VIOLATORS)}"
    )
```

In `test_no_dead_repository_methods.py`, empty
`_KNOWN_UNUSED_FOR_NOW` (every remaining method here must have its
deletion landed by this PR, per the structural simplification audit in
Task 5) and remove the xfail decorator from
`test_no_dead_repository_methods_remain`. The entries removed here are
the methods identified during PR 0.5's initial audit
(`TaskExecutionRepository.latest_for_definition_task`, etc.) — they
either gained a caller by PR 10 or are deleted in Task 1 of this PR.

These five assertions are the **machine-readable v2 completion bar**:
if the v2 implementation program is complete, all five dicts
(`_XFAIL_BY_NAME`, `_XFAIL_BY_SYMBOL`, `_KNOWN_EXEMPTIONS`,
`_KNOWN_VIOLATORS`, `_KNOWN_UNUSED_FOR_NOW`) are empty and all five
tests pass; if any still has entries, the program has not landed.

## Task 5: Structural Simplification Audit

The deletions from Tasks 1-4 leave several methods, services, and DTOs
*working* but possibly *no longer earning their existence*: indirection
layers whose original justification was the parallel old path, or
methods whose only branch is gone. Pytest cannot catch this class —
nothing about it is structurally wrong, the abstractions just stopped
paying for themselves.

This task is a **hand-checked review pass**, not a pytest assertion.
Either dispatch a `superpowers:code-reviewer` agent scoped to the
candidate sites below, or do the audit by hand. The deliverable is a
keep / rename / inline / split decision documented in the PR description
for each candidate.

The audit is intentionally bounded to this list — open-ended "look for
smells" reviews don't converge. Each candidate is named because
something concrete about the v2 deletions made it suspicious.

### Candidates

For each, ask: *does this still earn its name, its signature, its
existence?*

- [ ] **Step 1: `WorkflowGraphRepository.node`**

  The OR predicate `(RunGraphNode.id == task_id) | (RunGraphNode.definition_task_id == task_id)`
  from PR 2 collapses to `task_id == task_id` once `definition_task_id`
  and the separate `id` column are gone (Task 1 schema collapse). Does
  `node()` still earn its existence as a method, or does it shrink to
  `session.get(RunGraphNode, (run_id, task_id))` + `await Task.from_definition(...)`?
  If it stays, is "node" still the right name when the returned shape
  is a `RunGraphNodeView` carrying an inflated `Task`?

- [ ] **Step 2: `TaskExecutionService.prepare` / `_prepare_run_node`**

  PR 3 collapsed the static/dynamic branch into a single
  `_prepare_run_node`. After PR 11 deletes `_prepare_legacy_definition`,
  the service has one method. Does the service class still earn its
  existence, or does `_prepare_run_node`'s body inline into
  `worker_execute`?

- [ ] **Step 3: Sandbox lifecycle indirection**

  PR 4 made `worker_execute` the sole owner of `sandbox.acquire` and
  `sandbox.terminate` (via `lifecycle_hub` or whatever wrapper exists
  today). After Task 1 deletes `terminate_sandbox_by_id`, is the wrapper
  layer still earning anything, or is it now a thin pass-through to
  `Sandbox.provision()` and `Sandbox.terminate()`? If thin, inline it.

- [ ] **Step 4: `Sandbox.terminate` vs `Sandbox.detach` naming**

  Both survive PR 11 by design (lifecycle owner uses `terminate`, eval
  workers use `detach`). Run a final check: is the difference named
  clearly enough that a new reader doesn't have to read the docstring to
  know which to call? Grep for callsites and confirm the right one is
  used at each. If `detach` is ever wrong, consider renaming for clarity
  (e.g. `release_local_handle`).

- [ ] **Step 5: `RunGraphNodeView`**

  PR 2 introduced the view carrying both `node_id` and `task_id` during
  the transition. After Task 1 drops `node_id` and `definition_task_id`,
  the view collapses to `(run_id, task_id, parent_task_id, status, task, is_dynamic)`.
  Does it still earn a separate type, or does it become
  `RunGraphNode` + an inflated `Task` accessor on the row itself?

- [ ] **Step 6: `RunTaskExecution.attempt_number`**

  After PR 4 the canonical retry id is `execution_id`. Does
  `attempt_number` add anything `execution_id` ordering doesn't already
  carry, or is it duplicate state? If duplicate, drop in this PR (it's
  a small additional column drop).

- [ ] **Step 7: `EvaluationService.evaluate` / `persist_success` / `persist_failure` split**

  The split made sense when `CriterionExecutor` did the running and
  `EvaluationService` did the persisting. PR 4 deleted the executor;
  the reshaped `evaluate_task_run` calls `evaluator.evaluate(...)` and
  `EvaluationService.persist_*` directly. Is the persist/success/failure
  three-method shape still right, or does it collapse to one
  `persist(result_or_exc)` method?

- [ ] **Step 8: `WorkerContext` curated surface**

  PR 9 routed `spawn_task` through the graph-native path. Re-verify the
  curated method set in `01-api-surface.md` against the implementation:
  any methods that became no-ops, any methods now missing.

- [ ] **Step 9: `Worker.from_definition` vs `Worker(...)` author surface**

  PR 5 makes authors construct workers via `Worker(...)`. Is
  `from_definition` discoverable as framework-internal? Is there
  guidance / a docstring that prevents future authors from reaching for
  it the way the v1 audit found people doing with `from_buffer`?

- [ ] **Step 10: `PreparedTaskExecution` itself**

  After Task 1 drops `node_id`, `definition_task_id`, `worker_type`,
  `assigned_worker_slug`, `model_target`, the DTO is down to ~6 fields,
  all of which the caller already has. Does the DTO still earn
  marshaling, or does `TaskExecutionService.prepare` return a tuple or
  call directly into `worker_execute`?

- [ ] **Step 11: Single-use private helper sweep**

  The previous ten candidates are named ahead of time. This step is
  *generative*: run a one-shot audit script against the post-deletion
  tree and add each finding as a row in the decision table.

  The principle: a private helper (`_foo`) whose body is ≥ 6 lines and
  has exactly one call site, both in the same module, *may* be a
  premature abstraction left over from when the v2 cutovers were
  in-flight. The candidate is not guilty by default — many extractions
  are legitimate (testability, naming, branch isolation). The audit
  forces a decision rather than presuming one.

  **Run the audit:**

  ```bash
  uv run python scripts/single_use_helper_audit.py \
      --paths ergon_core/ergon_core ergon_builtins/ergon_builtins ergon_cli/ergon_cli \
      --min-body-lines 6 \
      --exclude-decorators inngest.function,pytest.fixture,property,classmethod,staticmethod,model_validator,field_validator,model_serializer \
      --output /tmp/single_use_helpers.csv
  ```

  The script lives at `scripts/single_use_helper_audit.py` and is
  committed as part of this PR's Task 5 work (small, self-contained,
  AST-based). Its output is `(function, defining_file:line, caller_file:line, body_size)`,
  one row per candidate.

  **What the script must skip** (avoid the false-positive categories
  the policy explicitly carves out):

  - Decorator-registered callables: `@inngest.function`, `@pytest.fixture`,
    `@pytest.mark.*`, `@property`, `@classmethod`, `@staticmethod`,
    `@model_validator`, `@field_validator`, `@model_serializer`,
    `@cached_property`, `@functools.cache`.
  - Test files (path-excluded under `tests/`).
  - Functions in `__init__.py` re-export modules.
  - Functions whose call site is `__all__ = [..., "_foo", ...]` (export
    list).

  **Triage:**

  For each surviving row, decide KEEP / INLINE / RENAME and add it to
  the audit decision table with the same shape as the named candidates:

  ```markdown
  | 11.a | `_compute_default_evaluator_index` (jobs/worker_execute.py:142) | INLINE | 8-line helper called once 30 lines below; inlining brings the constant next to its only user. |
  | 11.b | `_validate_definition_handle` (experiments/launch.py:88) | KEEP | Single use today but the validation rules are explicitly subject to unit tests in test_launch_validation.py. |
  | 11.c | `_persist_eval_payload` (telemetry/repository.py:156) | RENAME → `persist_evaluation` | Single use but the name is private-ish for no reason; promote and document. |
  ```

  **Authors can preempt the audit** by annotating helpers with a
  `# locality: <reason>` comment at the definition site (mirrors the
  `# typing:` exemption pattern from § 0.6). The script skips any
  function whose def-line or the line above carries `# locality:`. Use
  this for genuinely-single-use helpers that exist for testability,
  naming clarity, or other documented reasons.

  **Expected scale:** A first-run audit of the v1 tree surfaces
  perhaps 20–40 candidates. After this sweep, the count should stay
  near zero unless future PRs reintroduce premature abstractions.

### How to record the outcome

For each candidate above, the PR description **must** include a
Markdown decision table:

```markdown
## Structural Simplification Audit

| # | Candidate | Decision | Reason |
|---|---|---|---|
| 1 | `WorkflowGraphRepository.node` | KEEP | Still earns its existence after the OR-predicate collapses — typed view + inflated Task in one method. |
| 2 | `TaskExecutionService.prepare` / `_prepare_run_node` | INLINE | One method, one branch, no service-level concern; inlined into `worker_execute`. |
| 3 | Sandbox lifecycle indirection | KEEP | `lifecycle_hub` still owns the per-run cleanup backstop. |
| ... | ... | ... | ... |
```

Rules:

- **Every named candidate (1-10) and every Step 11 audit row must
  appear** in the table. No omissions; a missing row blocks merge. The
  Step 11 rows are numbered `11.a`, `11.b`, ... — one per surviving
  audit finding.
- **Decision must be one of: KEEP / RENAME / INLINE / SPLIT.** Use a
  single value — no "MAYBE", no "DEFER", no compound values.
- **Reason is one sentence.** Long rationale belongs in the commit
  message or a comment in the code; the table is the at-a-glance
  artifact.
- **INLINE / SPLIT / RENAME decisions ship in this PR.** A KEEP
  candidate stays unchanged (and Step 11 KEEP entries should gain a
  `# locality: <reason>` comment at the def site so future audits skip
  them).
- **A deferred decision is not allowed** — the v2 program's exit
  criterion includes "no half-finished structural decisions."

The reviewer's job during merge: read the table, spot-check two or
three candidates against the code, and confirm the decision is the one
the table claims. For Step 11 rows, the reviewer can verify the audit
script's output matches the table by re-running the script.

A code-reviewer dispatch can do this in one pass:

```text
Dispatch: superpowers:code-reviewer
Scope: PR 11's structural simplification audit (see § Task 5)
Candidates: [paste the 10 candidates above]
Output: for each, KEEP / RENAME / INLINE / SPLIT with one-sentence reason
```

## Task 6: Run Verification

```bash
uv run pytest ergon_core/tests/unit/architecture -q
uv run pytest ergon_core/tests/unit/api -q
uv run pytest ergon_core/tests/unit/runtime -q
uv run pytest ergon_builtins/tests/unit -q
uv run pytest ergon_cli/tests -q
```

After PR 11 these expectations hold:

- `test_v2_final_state_ledger.py`: every parametrized case PASS; the
  "no xfails remain" guard PASS.
- `test_dead_path_audit.py`: every parametrized case PASS; the "no dead
  paths xfailed" guard PASS.
- `test_no_type_circumventors.py`: every production-code hit either
  carries a `# typing:` exemption or no hits remain; the
  `test_no_known_type_circumventor_exemptions_remain` guard PASS.
- `test_repository_layer_conventions.py`: every case PASS; the
  `test_no_repository_violators_remain` guard PASS.
- `test_repository_companion_files.py`: every case PASS.
- `test_no_dead_repository_methods.py`: every case PASS; the
  `test_no_dead_repository_methods_remain` guard PASS.
- `test_walkthrough_smoketest.py`: every case PASS, no XFAIL.
- `test_identity_invariants.py`: every case PASS, no XFAIL.
- `test_no_deleted_v2_symbols.py` (Task 3): PASS.
- `test_single_alembic_head.py` (Task 2): PASS.

If any of these still report XFAIL/XPASS, the deletion gate has not
truly closed and PR 11 is not ready to merge.

## PR Ledger

Invariant landed: all v2 transition bridges are gone; the run-tier read
boundary is structurally enforced (no fallback code exists); both
xfail-ledger dicts are empty; the structural simplification audit
recorded a keep/rename/inline/split decision for each of the 10
candidates.

Bridge code introduced: none.

Old path still intentionally alive: none.

Deletion gate: this PR is the deletion gate. Completion bar is the
"no xfails remain" assertions in `test_v2_final_state_ledger.py` and
`test_dead_path_audit.py`.

Tests added or updated: deleted-symbol guards, single-Alembic-head
guard, and the two completion-bar `test_no_*_are_still_xfailed`
assertions.

Modules owned by this PR: cleanup across all lanes.

PR description must include the structural-audit outcome table from
Task 5 — one line per candidate with the decision (KEEP / RENAME /
INLINE / SPLIT) and one-sentence reason. Reviewers can quickly verify
the audit was actually run by checking that table.
