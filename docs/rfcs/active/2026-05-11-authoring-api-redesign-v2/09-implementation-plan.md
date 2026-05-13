# 09 — Implementation plan

> **For agentic workers and human reviewers:** this plan converts the v2 spec docs (`01`–`08`) into an executable, file-grounded task list. Each phase is a cluster of sub-commits on a single PR branch; sub-commits use checkbox (`- [ ]`) syntax for tracking. Read [`00-readme.md`](00-readme.md) first for the v2 reading order, then this doc.
>
> **For provenance:** the v1 migration doc still has reference value for individual symbol-rename details — see [`../2026-05-08-authoring-api-redesign/05-migration.md`](../2026-05-08-authoring-api-redesign/05-migration.md) §14.A "Schema and contract reference" — but the *order of work* below replaces v1's phased plan entirely.

**Goal.** Reimplement the authoring/runtime stack against the v2 spec on a single PR branch, in six logically-cohesive phases (~2,900 lines cumulative diff). Schema reset on phase 1; no production data; no compatibility shims.

**Architecture.** Two-tier persistence (`experiment_definitions` + run-tier graph), unified `worker_execute` with inline criteria and explicit sandbox lifecycle, four-axis failure semantics (spawn-children fail, dependency-dependents stay PENDING), graph-native dynamic subtasks, no `saved_specs`/`from_buffer`/`CriterionExecutor` Protocol, slimmer Inngest event surface.

**Tech stack.** Python 3.11+, Pydantic v2, SQLModel, Alembic, Inngest, pytest, Postgres (prod + walkthrough integration), SQLite (unit tests).

---

## Strategy

**One PR branch, internal phasing.** v2 ships in a single PR against `main`. Within the PR, the work is organised into six phases; each phase is a commit cluster of 3–6 sub-commits.

**Single reviewer (charlie) reviews the whole PR.** Phase boundaries inside the PR exist to make commit-by-commit review tractable, not to gate separate review rounds.

**The branch may be non-runnable mid-phase.** Each phase's *last* sub-commit lands the branch back to a green state; intermediate sub-commits within a phase may leave the branch with broken imports or failing tests. The PR-level DoD (§"Definition of done", below) is what guarantees green at merge. Sub-commit DoD entries call out non-runnable states explicitly with `[non-runnable: reason]`.

**No backward compatibility within v2 phases.** Once a phase commit lands on the branch, the previous phase's intermediate state is gone — no feature flags, no transition shims.

**Schema reset on phase 1.** Per [`08-decisions-log.md` Δ.6](08-decisions-log.md), v2 wipes v1's Alembic chain and generates one fresh initial migration. The audit found v1 is *already* in a broken half-state (forked Alembic chain with two heads `e2f3a4b5c6d7` and `aa11bb22cc33`; `migrations/env.py` imports a non-existent `components.models` module; ORM ↔ migration drift on `RunGraphNode`). Reset is mandatory, not optional.

**No production data.** Ergon is a local tool with no shipped deployments. The reset destroys dev databases only.

**Test strategy.** SQLite for unit-level tests (architecture guards, regression net, fast); Postgres test container for the walkthrough integration test (one run per CI invocation, ~2 min). See [`07-test-strategy.md`](07-test-strategy.md) for layer breakdown.

---

## Pre-flight (before phase 1)

### Environment setup

- [ ] **Step P.1: Verify v1 worktree is on its own branch and not `main`.**

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/worktrees/ergon/authoring-api-redesign
git status
git branch --show-current
```

Expected: branch is `authoring-api-redesign` (or similar), not `main`.

- [ ] **Step P.2: Create v2 branch from current `main` of the source repo.**

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
git status
git checkout main && git pull
git checkout -b v2/authoring-api-redesign
```

Expected: clean tree on `v2/authoring-api-redesign`.

- [ ] **Step P.3: Drop dev databases.**

```bash
# Adjust connection string per local setup
psql -U ergon -h localhost -c "DROP DATABASE IF EXISTS ergon_dev;"
psql -U ergon -h localhost -c "CREATE DATABASE ergon_dev;"
```

Expected: empty `ergon_dev`. (SQLite test DBs are file-based; deleted automatically by test suite.)

- [ ] **Step P.4: Verify Inngest dev server runs.**

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
make inngest-dev  # or whatever the project's Inngest dev target is
```

Expected: dev server boots, no errors. Stop it before continuing.

### Note on path conventions

All file paths in this plan are relative to `/Users/charliemasters/Desktop/synced_vm_002/ergon/` (the source repo, where v2 is built), not the v1 worktree. Where the audit cited paths from the v1 worktree, the equivalent paths in the v2 working tree are identical (the worktree was a fork from `main`).

---

## File disposition reference

These tables are derived from the pre-write audit and are the single source of truth for "what gets touched in which phase". Each later phase references back to these tables instead of re-listing files.

### A. Inngest jobs (`ergon_core/ergon_core/core/application/jobs/`)

12 files. v1 splits work across multiple parallel consumers; v2 consolidates.

| File | v1 role | v2 disposition | Phase |
|---|---|---|---|
| `start_workflow.py` | Consume `workflow/started`; init graph; fan out initial `task/ready` | **REWRITE** as `prepare_run` (per [06](06-inngest-event-contracts.md) `workflow/started`); pure prepare, no fan-out | 3 |
| `execute_task.py` | Consume `task/ready`; orchestrate prepare + invoke `worker_execute_fn` + finalize; emit `task/completed`/`task/failed` | **DELETE**; v2 sends `task/worker-execute` directly from `advance_run` | 3 |
| `worker_execute.py` | Consume `task/worker-execute`; acquire sandbox; run `Worker.execute`; release on error path only | **REWRITE** to inline criteria + own sandbox lifetime via `try/finally`; emit `task/completed`/`task/failed` itself | 3 |
| `evaluate_task_run.py` | Consume `task/evaluate` (only via `step.invoke`); run criteria via `InngestCriterionExecutor` | **DELETE**; criteria run inline in `worker_execute` | 3 |
| `check_evaluators.py` | Consume `task/completed`; `step.invoke` `evaluate_task_run`; terminate sandbox via `terminate_sandbox_by_id` | **DELETE**; evaluation is inline; sandbox release moves into `worker_execute` | 3 |
| `propagate_execution.py` | Consume `task/completed`/`task/failed`; propagate via `WorkflowService.propagate`; emit `task/ready`/`workflow/completed`/`workflow/failed` | **REWRITE** as `advance_run` (per [06](06-inngest-event-contracts.md) `task/completed` consumer); single source of truth for "what's next" | 3 |
| `cancel_orphan_subtasks.py` | Consume `task/failed` (parallel to `propagate_execution`); also `task/cancelled`; cascade containment | **REWRITE** and **MERGE_INTO** `advance_run`; the four-axis lock makes this a sub-step of `task/failed` consumption | 3 |
| `cleanup_cancelled_task.py` | Consume `task/cancelled`; mark execution CANCELLED in DB | **KEEP** with payload update for v2 cancellation event shape | 3 |
| `complete_workflow.py` | Consume `workflow/completed`; finalize `RunRecord`; send `run/cleanup` | **REWRITE** to consume v2's minimal `workflow/completed` payload (just `run_id` + `final_status`); fold `run_cleanup` send into the finalize body | 3 |
| `fail_workflow.py` | Consume `workflow/failed`; mark `RunRecord` FAILED; send `run/cleanup` | **DELETE**; v2 has only `workflow/completed` with `final_status` ∈ `{SUCCEEDED, FAILED}`. Failure-path finalization moves into `complete_workflow.py` | 3 |
| `run_cleanup.py` | Consume `run/cleanup`; sweep sandbox via `terminate_sandbox_by_id` from `RunRecord.summary_json["sandbox_id"]` | **KEEP** as best-effort backstop; `worker_execute` is the primary release path | 3 |
| `models.py` | Pydantic event payloads (`TaskWorkerExecutePayload`, `EvaluateTaskRunRequest`, etc.) | **REWRITE** to match [06](06-inngest-event-contracts.md) payload shapes; delete `EvaluateTaskRunRequest` | 3 |

**Inngest function registry**: `ergon_core/core/infrastructure/inngest/registry.py` `ALL_FUNCTIONS` list shrinks from 13 functions to 6: `prepare_run_fn`, `worker_execute_fn`, `advance_run_fn`, `complete_workflow_fn`, `cleanup_cancelled_task_fn`, `run_cleanup_fn`. Phase 3 sub-commit 3.10 updates this list.

### B. Workflows (`ergon_core/ergon_core/core/application/workflows/`)

| File | v2 disposition | Phase |
|---|---|---|
| `errors.py` | **KEEP** | — |
| `models.py` (read-model DTOs) | **KEEP**; minor field updates if Run shape changes | 1 |
| `orchestration.py` | **REWRITE** to remove `definition_task_id` from `PreparedTaskExecution` (the comment at lines 69–75 documents v1's hybrid; v2 deletes it) | 2 |
| `runs.py` (`create_run`/`cancel_run`) | **KEEP**; cancel path's `run/cleanup` send semantics unchanged | — |
| `service.py` (`WorkflowService`) | **REWRITE**: split `initialize` → `prepare_run` body (phase 3); merge `propagate` + `propagate_failure` into `advance_run` body; introduce `is_run_terminal` per [06](06-inngest-event-contracts.md) | 2, 3 |
| `__init__.py` | **KEEP** | — |

### C. Application services / runtime helpers (`ergon_core/ergon_core/core/application/`)

| Subdir | v2 disposition | Notes |
|---|---|---|
| `tasks/execution.py` | **REWRITE**: delete `_prepare_definition` (definition-tier read on every static task); collapse to graph-native only | Phase 2 |
| `tasks/management.py` | **KEEP** with verification: confirm `add_subtask`/`spawn_task` already write only to `RunGraphNode` (audit confirms no `materialize_dynamic_subtask_definition` exists) | Phase 4 |
| `tasks/inspection.py` | **KEEP** | — |
| `tasks/repository.py` | **REWRITE**: delete `task_payload_for_execution` (joins `ExperimentDefinitionTask`; zero callers per audit) | Phase 5 |
| `tasks/service.py`, `tasks/models.py`, `tasks/errors.py`, `tasks/cleanup.py`, `tasks/__init__.py` | **KEEP** | — |
| `experiments/service.py` (`ExperimentService.define_benchmark_experiment`, `persist_definition`, `run_experiment`) | **REWRITE**: keep `persist_definition` as the single authoring entry point; delete `define_benchmark_experiment` (CLI surface change in phase 5 makes it dead); fold `run_experiment` orchestration into `launch_run` per [05](05-cli-authoring-interface.md) | Phase 5 |
| `experiments/launch.py` | **REWRITE**: delete `_persist_single_sample_workflow_definition` *reference* (the function isn't defined; just remove the import alias and default-factory plumbing) | Phase 5 |
| `experiments/definition_writer.py`, `experiments/repository.py`, `experiments/models.py` | **KEEP** with field updates if `Experiment` Pydantic shape changes | Phase 1 |
| `evaluation/executors.py` (`CriterionExecutor` Protocol) | **DELETE** | Phase 5 |
| `evaluation/inngest_executor.py` (`InngestCriterionExecutor`) | **DELETE** | Phase 5 |
| `evaluation/service.py` (`EvaluationService`) | **REWRITE**: delete `prepare_dispatch` (no longer needed since dispatch is gone); keep `evaluate(...)` as the inline-criteria entry point called from `worker_execute` | Phase 3 |
| `evaluation/models.py`, `evaluation/scoring.py`, `evaluation/errors.py` | **KEEP** | — |
| `graph/repository.py` (`WorkflowGraphRepository`) | **REWRITE**: delete `initialize_from_definition`'s definition-tier reads; reads only from definition-tier in the *prepare* phase, never after | Phase 1, Phase 2 |
| `graph/propagation.py` (incl. `is_workflow_complete_v2`/`is_workflow_failed_v2`) | **REWRITE**: replace v1 helpers with `is_run_terminal` per [06](06-inngest-event-contracts.md) pseudocode; delete `get_initial_ready_tasks` (moves into `prepare_run` in `start_workflow.py`) | Phase 3 |
| `graph/traversal.py`, `graph/lookup.py`, `graph/models.py`, `graph/errors.py` | **KEEP**; `lookup.py`'s `definition_task_id → node_id` map becomes a no-op (everything is task-keyed in v2) and gets deleted in phase 5 | Phase 5 |
| `context/events.py` (`ContextEventService`) | **KEEP** | — |
| `context/output_extraction.py`, `context/__init__.py` | **KEEP** | — |
| `read_models/experiments.py`, `read_models/runs.py`, `read_models/cohorts.py` | **REWRITE**: drop joins through the dropped `ExperimentRecord` ORM; reads now come from the collapsed `ExperimentDefinition` | Phase 1 |
| `read_models/run_snapshot.py`, `read_models/resources.py`, `read_models/models.py`, `read_models/errors.py`, `read_models/__init__.py` | **KEEP** with field shape updates as needed | Phase 1 |
| `resources/repository.py`, `resources/models.py`, `resources/__init__.py` | **KEEP** | — |
| `communication/service.py`, `communication/models.py`, `communication/errors.py`, `communication/__init__.py` | **KEEP** | — |
| `events/task_events.py`, `events/infrastructure_events.py`, `events/base.py` | **REWRITE**: payload shapes per [06](06-inngest-event-contracts.md); delete `EvaluateTaskRunRequest` and unused event types | Phase 3 |

### D. Persistence (`ergon_core/ergon_core/core/persistence/`)

| Subdir | v2 disposition | Notes |
|---|---|---|
| `definitions/models.py` | **REWRITE**: collapse `ExperimentRecord` columns into `ExperimentDefinition` per [02 §3](02-persistence-layer.md); delete `ExperimentDefinitionTaskAssignment`/`ExperimentDefinitionTaskEvaluator`/`ExperimentDefinitionTaskDependency` *if* unreferenced after phase 2 (verify in phase 5) | Phase 1, Phase 5 |
| `telemetry/models.py` (`ExperimentRecord`, `RunRecord`, `RunTaskExecution`, `RunResource`, `RunTaskEvaluation`, etc.) | **REWRITE**: delete `ExperimentRecord` ORM; update `RunRecord` to drop `experiment_id` FK and reference `experiment_definition_id` (renamed from `workflow_definition_id`); update `RunTaskExecution` to drop `definition_task_id` (already nullable per audit) | Phase 1 |
| `telemetry/repositories.py`, `telemetry/evaluation_summary.py` | **KEEP** with FK shape updates | Phase 1 |
| `graph/models.py` (`RunGraphNode`/`RunGraphEdge`/etc.) | **REWRITE**: add `is_dynamic BOOLEAN NOT NULL DEFAULT FALSE` to `RunGraphNode`; verify composite PK `(run_id, task_id)`; verify no `definition_task_id` column survives | Phase 1 |
| `graph/status_conventions.py` | **KEEP** | — |
| `saved_specs/models.py` (4 ORM classes) | **DELETE** entire package | Phase 5 |
| `imports/models.py` (`RunReducer`/etc.) | **REWRITE**: align ORM `task_id` field with phase 1 schema (audit found drift between migration `node_id` and ORM `task_id`) | Phase 1 |
| `context/models.py`, `context/event_payloads.py` | **KEEP** | — |
| `shared/db.py`, `shared/enums.py`, `shared/ids.py`, `shared/types.py` | **KEEP** | — |

### E. Migrations (`ergon_core/migrations/versions/`)

25 files in v1 worktree (forked at `f9075c2ddbc9` into mainline `e2f3a4b5c6d7` and authoring `aa11bb22cc33`). All are deleted and replaced with **one** initial v2 migration in phase 1 sub-commit 1.1.

The previous `5f01559f2bc3_initial_schema_v2.py` (current root) is misleadingly named — it's not the v2 schema, just an early reset snapshot. It gets deleted along with the rest.

### F. Public API (`ergon_core/ergon_core/api/`)

27 names exported from `ergon_core.api.__init__`. v2 changes:

| Symbol | Change | Phase |
|---|---|---|
| `Experiment` (`experiment.py`) | Add fields `name: str`, `description: str | None`, `metadata: dict[str, Any] = Field(default_factory=dict)` | Phase 1 |
| `Sandbox` (`sandbox/sandbox.py`) | Add field `output_path: str = "/workspace/final_output/"` | Phase 1 (or wherever convenient — no blocker) |
| `Worker` (`worker/worker.py`) | Delete classmethod `from_buffer` (zero callers per audit) | Phase 5 |
| `Benchmark` | **KEEP** (the existing `name`/`description`/`metadata` fields stay; `Experiment` gets its own copies for run-level overrides) | — |
| Others (`Criterion`, `Rubric`, `Evaluator`, `WorkerContext`, `CriterionContext`, `Task`, `Sandbox*Errors`, etc.) | **KEEP** | — |

`api/__init__.py`'s `__all__` does not need changes; `from_buffer` was never exported.

### G. CLI (`ergon_cli/ergon_cli/`)

The actual CLI shape per audit is `ergon experiment define`/`ergon experiment run`, NOT `ergon define`/`ergon run`. v2 simplifies:

| Command | v2 disposition | Phase |
|---|---|---|
| `ergon experiment define <slug>` (`commands/experiment.py`) | **REWRITE** to call `persist_definition(experiment)` directly per [05](05-cli-authoring-interface.md). Delete the `ExperimentService.define_benchmark_experiment` route | Phase 5 |
| `ergon experiment run <definition-id>` | **REWRITE** to call `launch_run(definition_id, ...)` directly | Phase 5 |
| `ergon experiment show`/`list` | **KEEP** with FK shape updates | Phase 1 |
| `ergon benchmark *` | **KEEP** | — |
| `ergon run list`/`cancel` (run records, not launch) | **KEEP** | — |
| `ergon workflow *`, `ergon worker list`, `ergon evaluator list`, `ergon train *`, `ergon onboard`, `ergon doctor`, `ergon ingest *`, `ergon eval *` | **KEEP** | — |

### H. Tests

| Location | v2 disposition | Phase |
|---|---|---|
| `ergon_core/tests/unit/architecture/` (10 files) | **KEEP all 10** with assertion updates: `test_public_api_target_structure.py` already has `definition_task_id` in its forbidden list — extend with `experiment_records` and `saved_specs` table forbidden checks. `test_core_schema_sources.py` `ExperimentService` surface-listing updates per phase 5 | Phase 5, Phase 6 |
| `ergon_core/tests/unit/runtime/test_inngest_criterion_executor.py` | **DELETE** (whole file hinges on `InngestCriterionExecutor`) | Phase 3 |
| `ergon_core/tests/unit/runtime/test_child_function_payloads.py` | **DELETE** (asserts on `EvaluateTaskRunRequest`) | Phase 3 |
| `ergon_core/tests/unit/runtime/test_experiment_launch_service.py` | **REWRITE**: drop the `workflow_definition_factory` injection; assert on `persist_definition`+`launch_run` happy path | Phase 5 |
| `ergon_core/tests/unit/runtime/test_experiment_definition_service.py` | **REWRITE**: replace `define_benchmark_experiment` assertions with `persist_definition` assertions | Phase 5 |
| `ergon_core/tests/unit/runtime/test_worker_execute_sandbox_lifecycle.py` | **REWRITE** for v2 inline-criteria + try/finally release | Phase 3 |
| `ergon_core/tests/unit/runtime/test_failed_task_sandbox_cleanup.py` | **REWRITE** for four-axis failure semantics | Phase 3 |
| `ergon_core/tests/unit/runtime/test_propagation_contracts.py` | **REWRITE** as `advance_run` contract test | Phase 3 |
| `ergon_core/tests/unit/runtime/test_definition_task_payload_typing.py` | **DELETE** (definition-task payload typing for `_prepare_definition` path which gets deleted) | Phase 2 |
| `ergon_core/tests/unit/runtime/test_definition_lookup_boundaries.py` | **DELETE** (`definition_task_id → node_id` lookup which gets deleted in phase 5) | Phase 5 |
| `ergon_core/tests/unit/runtime/` other 22 files | **KEEP** with field/import updates | Phase 1, 3, 5 |
| `ergon_core/tests/unit/api/` 6 files | **KEEP** with field updates per `Experiment`/`Sandbox` changes | Phase 1 |
| `ergon_core/tests/unit/state/` 6 files, `unit/dashboard/` 3 files, `unit/persistence/` 1 file, `unit/scripts/` 1 file, `unit/` top-level 4 files | **KEEP** | — |
| `ergon_builtins/tests/unit/` 10 files | **KEEP** with import path updates | — |
| `ergon_cli/tests/` 10 files | **REWRITE** `test_experiment_cli.py` for new `persist_definition` call shape | Phase 5 |
| **NEW** `tests/integration/test_walkthrough.py` | **CREATE** in phase 6 with 4 variants (happy / failure cascade / dynamic spawn / restart) | Phase 6 |

---

## Phase 1 — Schema reset, persistence ORM, and authoring API fields

**Encodes:** [Δ.1](08-decisions-log.md) (`ExperimentRecord` collapse), [Δ.6](08-decisions-log.md) (schema reset), [Q28](01-api-surface.md) (`Sandbox.output_path`).

**Goal.** After this phase, the database has the v2 schema (single migration, no v1 chain remnants), the ORM models match the new tables, and the public `Experiment`/`Sandbox` Pydantic types carry the v2 authoring fields. Runtime code may still reference removed structures (e.g. `ExperimentRecord` ORM imports in `read_models/cohorts.py`) — those break in this phase and get fixed in phase 2.

**Files this phase touches (read in this order):**

1. `ergon_core/migrations/env.py` — current Alembic config (broken `components.models` import per audit)
2. `ergon_core/migrations/versions/*.py` — all 25 will be deleted
3. `ergon_core/ergon_core/core/persistence/definitions/models.py` — `ExperimentDefinition` ORM
4. `ergon_core/ergon_core/core/persistence/telemetry/models.py` — `ExperimentRecord` (delete) and `RunRecord` (rewrite)
5. `ergon_core/ergon_core/core/persistence/graph/models.py` — `RunGraphNode` (add `is_dynamic`)
6. `ergon_core/ergon_core/core/persistence/imports/models.py` — `RunReducer` ORM/migration drift (audit)
7. `ergon_core/ergon_core/api/experiment.py` — `Experiment` Pydantic
8. `ergon_core/ergon_core/api/sandbox/sandbox.py` — `Sandbox` Pydantic

### Sub-commit 1.1 — Reset Alembic chain and fix env.py imports

**Files:**
- Delete: `ergon_core/migrations/versions/*.py` (all 25 files)
- Modify: `ergon_core/migrations/env.py`

- [ ] **Step 1.1.1: Delete all migration version files.**

```bash
cd ergon_core/migrations/versions
git rm *.py
ls -1
```

Expected: directory is empty (or contains only `__init__.py` if one exists).

- [ ] **Step 1.1.2: Fix the `env.py` broken import.**

The audit found `migrations/env.py` imports `ergon_core.core.persistence.components.models` which doesn't exist. Open `migrations/env.py` and locate the import block. Replace the `components.models` import with explicit imports of the four model modules that actually exist:

```python
from ergon_core.core.persistence.definitions.models import *  # noqa: F401, F403
from ergon_core.core.persistence.telemetry.models import *    # noqa: F401, F403
from ergon_core.core.persistence.graph.models import *        # noqa: F401, F403
from ergon_core.core.persistence.imports.models import *      # noqa: F401, F403
from ergon_core.core.persistence.context.models import *      # noqa: F401, F403
```

The `*` imports + `__all__` discipline at the model-module level give Alembic autogenerate the table set without a synthetic aggregator module.

- [ ] **Step 1.1.3: Reset alembic state on dev DB.**

```bash
psql -U ergon -h localhost -d ergon_dev -c "DROP TABLE IF EXISTS alembic_version;"
```

Expected: `DROP TABLE` succeeds (or a "does not exist" notice if dev DB is fresh from pre-flight P.3).

- [ ] **Step 1.1.4: Commit.**

```bash
git add ergon_core/migrations/
git commit -m "v2 phase 1.1: reset alembic chain and fix env.py imports"
```

**DoD for 1.1:** `migrations/versions/` is empty (except `__init__.py`); `migrations/env.py` imports succeed (`python -c "from ergon_core.migrations import env"` from repo root). **`[non-runnable: migrations gone, no schema]`** — no `alembic upgrade head` works yet; comes in 1.2.

### Sub-commit 1.2 — Author the v2 initial migration

**Files:**
- Create: `ergon_core/migrations/versions/00000000_initial_v2.py`

- [ ] **Step 1.2.1: Generate empty migration scaffold.**

```bash
cd ergon_core
alembic revision -m "initial v2 schema"
```

This creates `migrations/versions/<rev>_initial_v2_schema.py`. Rename to `00000000_initial_v2.py` (rev "00000000") for clarity:

```bash
mv migrations/versions/<rev>_initial_v2_schema.py migrations/versions/00000000_initial_v2.py
```

Edit the file: set `revision = "00000000"`, `down_revision = None`, `branch_labels = None`, `depends_on = None`.

- [ ] **Step 1.2.2: Implement `upgrade()` body.**

The schema follows [02 §3](02-persistence-layer.md) with the additions from the workshop locks. Tables to create (full DDL in the file body — abridged here for plan brevity):

```python
def upgrade() -> None:
    op.create_table(
        "experiment_definitions",
        sa.Column("definition_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("benchmark_type", sa.Text, nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_experiment_definitions_name",
                    "experiment_definitions", ["name"])

    op.create_table(
        "experiment_definition_tasks",
        sa.Column("definition_task_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("definition_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("experiment_definitions.definition_id"), nullable=False),
        sa.Column("task_slug", sa.Text, nullable=False),
        sa.Column("instance_key", sa.Text, nullable=False),
        sa.Column("task_json", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "experiment_definition_edges",
        sa.Column("edge_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("definition_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("experiment_definitions.definition_id"), nullable=False),
        sa.Column("source_task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("experiment_definition_tasks.definition_task_id"), nullable=False),
        sa.Column("target_task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("experiment_definition_tasks.definition_task_id"), nullable=False),
    )

    op.create_table(
        "runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("experiment_definition_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("experiment_definitions.definition_id"), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("summary_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "run_graph_nodes",
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_json", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="'pending'"),
        sa.Column("parent_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_dynamic", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("run_id", "task_id"),
    )
    op.create_index("ix_run_graph_nodes_run_status",
                    "run_graph_nodes", ["run_id", "status"])
    op.create_index("ix_run_graph_nodes_run_parent",
                    "run_graph_nodes", ["run_id", "parent_task_id"])
    op.create_index("ix_run_graph_nodes_run_dynamic",
                    "run_graph_nodes", ["run_id", "is_dynamic"],
                    postgresql_where=sa.text("is_dynamic"))

    op.create_table(
        "run_graph_edges",
        sa.Column("edge_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("source_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["run_id", "source_task_id"],
            ["run_graph_nodes.run_id", "run_graph_nodes.task_id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "target_task_id"],
            ["run_graph_nodes.run_id", "run_graph_nodes.task_id"],
        ),
        sa.UniqueConstraint("run_id", "source_task_id", "target_task_id"),
    )

    op.create_table(
        "run_graph_annotations",
        sa.Column("annotation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("target_type", sa.Text, nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("namespace", sa.Text, nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_annotation_lookup", "run_graph_annotations",
                    ["run_id", "target_type", "target_id", "namespace", "sequence"])

    op.create_table(
        "run_graph_mutations",
        sa.Column("mutation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("mutation_type", sa.Text, nullable=False),
        sa.Column("target_type", sa.Text, nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("old_value", postgresql.JSONB, nullable=True),
        sa.Column("new_value", postgresql.JSONB, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("triggered_by_mutation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("run_graph_mutations.mutation_id"), nullable=True),
        sa.Column("batch_operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "task_executions",
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("final_assistant_message", sa.Text, nullable=True),
        sa.Column("output_json", postgresql.JSONB, nullable=True),
        sa.Column("error_json", postgresql.JSONB, nullable=True),
        sa.Column("sandbox_id", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id", "task_id"],
            ["run_graph_nodes.run_id", "run_graph_nodes.task_id"],
        ),
    )
    op.create_index("ix_task_executions_run_task",
                    "task_executions", ["run_id", "task_id"])

    op.create_table(
        "criterion_outcomes",
        sa.Column("outcome_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("task_executions.execution_id"), nullable=False),
        sa.Column("criterion_slug", sa.Text, nullable=False),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("passed", sa.Boolean, nullable=True),
        sa.Column("evidence_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # Resources, threads, training, etc. — kept from v1 but cleaned of FKs to dropped tables.
    # (Detailed DDL omitted here for plan length; included in the migration file.)
```

The full migration file is approximately **350 lines**. The `downgrade()` body is `op.drop_table(...)` for each in reverse FK order — write it but expect it to be exercised only in dev-wipe scenarios.

- [ ] **Step 1.2.3: Run the migration.**

```bash
alembic upgrade head
```

Expected output: ends with `Running upgrade  -> 00000000, initial v2 schema`. No errors.

- [ ] **Step 1.2.4: Verify schema.**

```bash
psql -U ergon -h localhost -d ergon_dev -c "\dt" | sort
```

Expected: tables `alembic_version`, `experiment_definitions`, `experiment_definition_tasks`, `experiment_definition_edges`, `runs`, `run_graph_nodes`, `run_graph_edges`, `run_graph_annotations`, `run_graph_mutations`, `task_executions`, `criterion_outcomes`, plus retained tables (resources/threads/training/etc.).

Crucially **NOT** present: `experiments` (was `ExperimentRecord`'s table), `saved_benchmark_specs`, `saved_worker_specs`, `saved_evaluator_specs`, `saved_experiment_templates`, `run_task_state_events`, `run_actions`, `run_generation_turns`, `run_task_executions` (renamed `task_executions`), `run_task_evaluations` (replaced by `criterion_outcomes`).

- [ ] **Step 1.2.5: Commit.**

```bash
git add ergon_core/migrations/versions/00000000_initial_v2.py
git commit -m "v2 phase 1.2: initial v2 schema migration"
```

**DoD for 1.2:** `alembic upgrade head` succeeds on a fresh DB; schema matches [02 §3](02-persistence-layer.md). **`[non-runnable: ORM still imports ExperimentRecord which no longer has a table]`**.

### Sub-commit 1.3 — Update ORM models to match the v2 schema

**Files:**
- Modify: `ergon_core/ergon_core/core/persistence/definitions/models.py`
- Modify: `ergon_core/ergon_core/core/persistence/telemetry/models.py`
- Modify: `ergon_core/ergon_core/core/persistence/graph/models.py`
- Modify: `ergon_core/ergon_core/core/persistence/imports/models.py`

- [ ] **Step 1.3.1: Update `ExperimentDefinition` ORM (collapsed columns).**

In `definitions/models.py`, replace the existing class body:

```python
class ExperimentDefinition(SQLModel, table=True):
    __tablename__ = "experiment_definitions"

    definition_id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: str | None = None
    benchmark_type: str
    metadata_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column("metadata", JSONB, nullable=False)
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

Delete `ExperimentDefinitionInstance`, `ExperimentDefinitionTaskAssignment`, `ExperimentDefinitionTaskEvaluator`, `ExperimentDefinitionTaskDependency` ORM classes. (Their tables don't exist in v2.) Keep `ExperimentDefinitionTask` and add an `ExperimentDefinitionEdge` ORM class matching the new `experiment_definition_edges` table.

- [ ] **Step 1.3.2: Delete `ExperimentRecord` ORM and rewrite `RunRecord`.**

In `telemetry/models.py`:

```python
# DELETE the ExperimentRecord class entirely.

class RunRecord(SQLModel, table=True):
    __tablename__ = "runs"

    run_id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_definition_id: UUID = Field(
        foreign_key="experiment_definitions.definition_id"
    )
    status: RunStatus = Field(sa_column=Column("status", String, nullable=False))
    error_message: str | None = None
    metadata_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column("metadata", JSONB, nullable=False)
    )
    summary_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
```

In the same file, rename `RunTaskExecution` → `TaskExecution` (table renamed), drop `definition_task_id` column. Drop `RunTaskEvaluation` entirely (replaced by `criterion_outcomes` ORM `CriterionOutcome` — add it).

- [ ] **Step 1.3.3: Update `RunGraphNode` (add `is_dynamic`, verify composite PK).**

In `graph/models.py`:

```python
class RunGraphNode(SQLModel, table=True):
    __tablename__ = "run_graph_nodes"

    run_id: UUID = Field(foreign_key="runs.run_id", primary_key=True)
    task_id: UUID = Field(default_factory=uuid4, primary_key=True)
    task_json: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    status: str = Field(default="pending")
    parent_task_id: UUID | None = Field(default=None, index=True)
    level: int = Field(default=0)
    is_dynamic: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default=sa.false()))
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

Verify: no `definition_task_id` column, no `task_slug`/`description`/`assigned_worker_slug` (those were dropped on the `aa11` branch and don't return in v2).

- [ ] **Step 1.3.4: Fix `RunReducer` ORM/migration drift.**

In `imports/models.py`, `RunReducer` was using `task_id` while the migration column is `node_id` per audit. Reconcile to `task_id` (v2 is task-keyed throughout):

```python
class RunReducer(SQLModel, table=True):
    __tablename__ = "run_reducers"

    reducer_id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.run_id")
    task_id: UUID = Field(index=True)
    execution_id: UUID | None = Field(default=None, foreign_key="task_executions.execution_id")
    # ... remaining fields unchanged
```

The `00000000_initial_v2.py` migration in 1.2 declares `task_id` in `run_reducers` (verify); if you wrote `node_id`, fix the migration.

- [ ] **Step 1.3.5: Run a quick smoke import.**

```bash
python -c "from ergon_core.core.persistence.definitions.models import ExperimentDefinition; \
           from ergon_core.core.persistence.telemetry.models import RunRecord; \
           from ergon_core.core.persistence.graph.models import RunGraphNode; \
           print(ExperimentDefinition.__table__.columns.keys()); \
           print(RunRecord.__table__.columns.keys()); \
           print(RunGraphNode.__table__.columns.keys())"
```

Expected: column names match what 1.2's migration produced.

- [ ] **Step 1.3.6: Commit.**

```bash
git add ergon_core/ergon_core/core/persistence/
git commit -m "v2 phase 1.3: ORM models match v2 schema"
```

**DoD for 1.3:** Smoke import succeeds; ORM column lists match migration column lists. **`[non-runnable: callers of deleted ORM classes (ExperimentRecord) still import them; fixed in 1.5]`**.

### Sub-commit 1.4 — Update public API: `Experiment` and `Sandbox` Pydantic

**Files:**
- Modify: `ergon_core/ergon_core/api/experiment.py`
- Modify: `ergon_core/ergon_core/api/sandbox/sandbox.py`
- Modify: `ergon_core/tests/unit/api/test_authoring_redesign_contract.py` (extend tests)

- [ ] **Step 1.4.1: Add authoring fields to `Experiment`.**

In `experiment.py`:

```python
class Experiment(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    benchmark: Benchmark
    name: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    _persisted: DefinitionHandle | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _validate_sandbox_compatibility(self) -> "Experiment":
        # carried forward from v1
        ...
        return self
```

Note: per [01-api-surface.md "Foundational change C"](01-api-surface.md#foundational-change-c--experiment-lifts-into-the-public-api), the `Experiment` carries its own `name`/`description`/`metadata` separate from `Benchmark`'s. `Benchmark.name` is the "shape" name; `Experiment.name` is the "this run series" name.

- [ ] **Step 1.4.2: Add `output_path` to `Sandbox`.**

In `sandbox/sandbox.py`, in the `Sandbox` class body, add:

```python
output_path: str = "/workspace/final_output/"
```

Place it near the other authoring fields (`env`, `timeout_seconds`, `requires_network`).

- [ ] **Step 1.4.3: Write tests asserting the new fields.**

In `ergon_core/tests/unit/api/test_authoring_redesign_contract.py`, append:

```python
def test_experiment_carries_name_and_metadata():
    exp = Experiment(
        benchmark=_make_test_benchmark(),
        name="my-run",
        description="testing",
        metadata={"owner": "charlie"},
    )
    assert exp.name == "my-run"
    assert exp.description == "testing"
    assert exp.metadata == {"owner": "charlie"}


def test_sandbox_has_output_path_default():
    sb = _make_test_sandbox()
    assert sb.output_path == "/workspace/final_output/"


def test_sandbox_output_path_overridable():
    sb = _make_test_sandbox(output_path="/tmp/out/")
    assert sb.output_path == "/tmp/out/"
```

- [ ] **Step 1.4.4: Run the new tests.**

```bash
pytest ergon_core/tests/unit/api/test_authoring_redesign_contract.py -v -k "carries_name or output_path"
```

Expected: 3 PASSED.

- [ ] **Step 1.4.5: Commit.**

```bash
git add ergon_core/ergon_core/api/experiment.py \
        ergon_core/ergon_core/api/sandbox/sandbox.py \
        ergon_core/tests/unit/api/test_authoring_redesign_contract.py
git commit -m "v2 phase 1.4: Experiment authoring fields + Sandbox.output_path"
```

**DoD for 1.4:** Three new contract tests pass; `Experiment` and `Sandbox` carry the v2 fields.

### Sub-commit 1.5 — Update read models and queries that referenced `ExperimentRecord`

**Files:**
- Modify: `ergon_core/ergon_core/core/application/read_models/experiments.py`
- Modify: `ergon_core/ergon_core/core/application/read_models/runs.py`
- Modify: `ergon_core/ergon_core/core/application/read_models/cohorts.py`
- Modify: `ergon_core/ergon_core/core/application/experiments/repository.py`
- Modify: `ergon_core/ergon_core/core/application/experiments/launch.py` (just imports — full rewrite is phase 5)

- [ ] **Step 1.5.1: Replace `ExperimentRecord` reads with `ExperimentDefinition` reads.**

For each of the four read-model files: search for `ExperimentRecord`, replace with `ExperimentDefinition`. The two share enough columns (`name`, `metadata`) that the read query shape is similar. Specific replacements:

- `read_models/experiments.py`: rename `list_experiments()` queries to read from `experiment_definitions` (new shape: `definition_id`, `name`, `description`, `metadata`, `benchmark_type`, `created_at`).
- `read_models/runs.py`: drop the `ExperimentRecord` join in run queries; the `runs.experiment_definition_id` FK directly points to `experiment_definitions`. Run-level queries get `name`/`description` by joining definitions.
- `read_models/cohorts.py`: cohort filtering used `ExperimentRecord.cohort_id` per audit. v2 has no cohort tier (cohorts are out of scope per workshop). **Either** delete this file entirely, **or** stub it to return empty lists. Decision: **delete**, and remove the import from `read_models/__init__.py`.

- [ ] **Step 1.5.2: Update `experiments/repository.py`.**

`DefinitionRepository.get(...)` returns the new `ExperimentDefinition` shape. Drop methods that query `ExperimentDefinitionInstance` (no longer exists). `task_with_instance` becomes `task(definition_id, task_id)` — no instance dimension.

- [ ] **Step 1.5.3: Stub-rewrite `experiments/launch.py`.**

Replace the imports of `_persist_single_sample_workflow_definition` and the `WorkflowDefinitionFactory` type alias with a no-op stub that raises `NotImplementedError("phase 5: rewritten")`. Phase 5 fills it in. Goal here: just make imports succeed.

```python
def launch_run_from_definition(definition_id: UUID, *, metadata: dict[str, Any] | None = None) -> RunHandle:
    """Phase-5 entry point. Stubbed in phase 1; implemented in phase 5."""
    raise NotImplementedError(
        "launch_run_from_definition is a phase 5 deliverable; phase 1 only fixes imports"
    )
```

- [ ] **Step 1.5.4: Run persistence-tier tests.**

```bash
pytest ergon_core/tests/unit/persistence/ -v
pytest ergon_core/tests/unit/api/ -v
```

Expected: all pass. (Failures here mean the ORM ↔ migration drift fixed in 1.3 didn't fully land.)

- [ ] **Step 1.5.5: Commit.**

```bash
git add ergon_core/ergon_core/core/application/read_models/ \
        ergon_core/ergon_core/core/application/experiments/repository.py \
        ergon_core/ergon_core/core/application/experiments/launch.py
git commit -m "v2 phase 1.5: read-models + repository updates for v2 schema"
```

**DoD for 1.5:** Persistence-tier and API-tier unit tests pass. **`[non-runnable: runtime callers of removed ExperimentRecord methods (e.g. ExperimentService.define_benchmark_experiment) still break; phase 5 fixes those]`**.

### Sub-commit 1.6 — Phase-1 schema introspection guards

**Files:**
- Create: `ergon_core/tests/unit/architecture/test_v2_schema.py`

- [ ] **Step 1.6.1: Write schema-shape architecture guards.**

```python
"""Architecture guards for v2 schema. These run against an in-memory SQLite
introspection of the v2 ORMs; they don't require Postgres."""

from sqlalchemy import inspect
from ergon_core.core.persistence.shared.db import metadata


def test_experiment_records_table_does_not_exist():
    """v1's ExperimentRecord (table 'experiments') is collapsed into ExperimentDefinition."""
    assert "experiments" not in metadata.tables, \
        "Found 'experiments' table — ExperimentRecord must be collapsed per Δ.1"


def test_definition_task_id_column_does_not_exist_on_run_graph_nodes():
    """v2 keys run-tier graph by (run_id, task_id) only; no FK to definition tier."""
    columns = {c.name for c in metadata.tables["run_graph_nodes"].columns}
    assert "definition_task_id" not in columns, \
        "run_graph_nodes must not have definition_task_id (Δ.2)"


def test_run_graph_nodes_has_is_dynamic():
    """v2 carries is_dynamic for graph-native dynamic subtask discrimination (Δ.3)."""
    columns = {c.name for c in metadata.tables["run_graph_nodes"].columns}
    assert "is_dynamic" in columns


def test_saved_specs_tables_do_not_exist():
    """v2 deletes the saved_specs package and its tables (Δ.7)."""
    forbidden = {"saved_benchmark_specs", "saved_worker_specs",
                 "saved_evaluator_specs", "saved_experiment_templates"}
    found = forbidden & set(metadata.tables.keys())
    assert not found, f"saved_specs tables still present: {found}"


def test_criterion_outcomes_table_exists():
    """v2 introduces criterion_outcomes for inline-criteria results (Δ.5)."""
    assert "criterion_outcomes" in metadata.tables


def test_runs_table_has_experiment_definition_id_not_experiment_id():
    """RunRecord.experiment_id is replaced by RunRecord.experiment_definition_id (Δ.1)."""
    columns = {c.name for c in metadata.tables["runs"].columns}
    assert "experiment_definition_id" in columns
    assert "experiment_id" not in columns
```

- [ ] **Step 1.6.2: Run the guards.**

```bash
pytest ergon_core/tests/unit/architecture/test_v2_schema.py -v
```

Expected: 6 PASSED.

- [ ] **Step 1.6.3: Run the broader unit test suite to see what's broken (expected: lots).**

```bash
pytest ergon_core/tests/unit/ -x --ignore=ergon_core/tests/unit/runtime/ 2>&1 | head -50
```

Expected: persistence + architecture + api tests pass; runtime tests fail with import errors. That's the documented half-state — phase 2 fixes runtime.

- [ ] **Step 1.6.4: Commit.**

```bash
git add ergon_core/tests/unit/architecture/test_v2_schema.py
git commit -m "v2 phase 1.6: schema introspection architecture guards"
```

**DoD for phase 1 overall:**

- `alembic upgrade head` succeeds on a fresh DB.
- All ORM imports succeed; ORM ↔ migration drift resolved.
- `Experiment` and `Sandbox` carry v2 authoring fields.
- 6 new architecture guards pass.
- `pytest ergon_core/tests/unit/persistence/ ergon_core/tests/unit/architecture/ ergon_core/tests/unit/api/` all pass.
- `pytest ergon_core/tests/unit/runtime/` is **expected to fail** — phase 2 unblocks it.

---

## Phase 2 — Runtime read boundary

**Encodes:** [Δ.2](08-decisions-log.md) (runtime reads exclusively from run-tier tables).

**Goal.** After this phase, no code path called from runtime jobs (`worker_execute`, `advance_run`, `task/ready` handlers) reads from `experiment_definitions`, `experiment_definition_tasks`, or `experiment_definition_edges`. Definition reads happen exactly once per run, inside `prepare_run` (which currently lives in `start_workflow.py` and gets renamed in phase 3).

**Files this phase touches:**

1. `ergon_core/ergon_core/core/application/tasks/execution.py` — delete `_prepare_definition`
2. `ergon_core/ergon_core/core/application/graph/propagation.py` — delete `get_initial_ready_tasks` (move into prepare path)
3. `ergon_core/ergon_core/core/application/graph/repository.py` — refactor `initialize_from_definition` to be the *only* definition-tier reader; rename to `WorkflowGraphRepository.populate_from_definition`
4. `ergon_core/ergon_core/core/application/tasks/repository.py` — delete `task_payload_for_execution`
5. `ergon_core/ergon_core/core/application/workflows/orchestration.py` — drop `definition_task_id` from `PreparedTaskExecution`
6. `ergon_core/ergon_core/core/application/jobs/start_workflow.py` — definition-tier read happens here; verify it's the only place

### Sub-commit 2.1 — Delete `_prepare_definition` and consolidate task execution prep

**Files:**
- Modify: `ergon_core/ergon_core/core/application/tasks/execution.py`

Per audit, `tasks/execution.py:182–207` contains `TaskExecutionService._prepare_definition` which loads `ExperimentDefinitionTask` + `ExperimentDefinitionTaskAssignment` on every static task execution. This is the v1 cross-tier read leak.

- [ ] **Step 2.1.1: Read the file in full.**

```bash
wc -l ergon_core/ergon_core/core/application/tasks/execution.py
```

Note the line count (likely ~250). Open the file and locate `_prepare_definition` (around line 182).

- [ ] **Step 2.1.2: Delete `_prepare_definition` and any caller branches.**

The method is called from `prepare(run_id, task_id, *, mode)` based on a `mode` argument that distinguishes "definition-tier task" vs "graph-native task". Delete the `mode` argument, delete the `_prepare_definition` method, keep `_prepare_graph_native` as the single path. Rename it to just `_prepare`:

```python
class TaskExecutionService:
    async def prepare(
        self,
        session: Session,
        *,
        run_id: UUID,
        task_id: UUID,
    ) -> PreparedTaskExecution:
        """Prepare a task execution from the run-tier graph node only."""
        node = self._graph_repo.node(session, run_id=run_id, task_id=task_id).require()
        task = Task.from_definition(node.task_json, task_id=task_id)
        return self._build_prepared_execution(node=node, task=task, ...)
```

The `_prepare_graph_native` body is the new single implementation; rename and inline.

- [ ] **Step 2.1.3: Update callers.**

The caller is `jobs/execute_task.py` (which gets deleted in phase 3 anyway, so updating it is throwaway work — but the update is needed to keep the branch importable). Open `jobs/execute_task.py`, find the `task_execution_service.prepare(...)` call, remove the `mode=` kwarg if present.

- [ ] **Step 2.1.4: Run targeted unit tests.**

```bash
pytest ergon_core/tests/unit/runtime/test_execute_task_job.py -v 2>&1 | head
```

Expected: errors about `mode=` arg if you missed a callsite, otherwise pass.

- [ ] **Step 2.1.5: Commit.**

```bash
git add ergon_core/ergon_core/core/application/tasks/execution.py \
        ergon_core/ergon_core/core/application/jobs/execute_task.py
git commit -m "v2 phase 2.1: delete _prepare_definition, single prepare path"
```

**DoD for 2.1:** No `mode=` parameter on `TaskExecutionService.prepare`. `_prepare_definition` symbol does not exist. Targeted runtime tests pass.

### Sub-commit 2.2 — Move definition reads into a single `populate_from_definition` callsite

**Files:**
- Modify: `ergon_core/ergon_core/core/application/graph/repository.py`
- Modify: `ergon_core/ergon_core/core/application/graph/propagation.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/start_workflow.py`

- [ ] **Step 2.2.1: Rename `WorkflowGraphRepository.initialize_from_definition` → `populate_from_definition`.**

Audit located this around line ~700 of `graph/repository.py`. The method reads `experiment_definition_tasks` + `experiment_definition_task_dependencies` and inserts `RunGraphNode` + `RunGraphEdge` rows. Rename + add a docstring stating the contract:

```python
async def populate_from_definition(
    self,
    session: Session,
    *,
    run_id: UUID,
    definition_id: UUID,
) -> None:
    """Read every definition-tier task + edge for this definition and insert
    matching run-tier graph rows. This is the ONE-AND-ONLY definition-tier
    read in the runtime hot path. After this method returns, no runtime code
    may read from experiment_definition_tasks or experiment_definition_edges.

    See: `02-persistence-layer.md §4` (read boundary).
    """
    ...
```

The body shape stays — rename only.

- [ ] **Step 2.2.2: Delete `get_initial_ready_tasks` from `propagation.py`.**

Audit located it at lines 117–125 of `graph/propagation.py`. It reads `ExperimentDefinitionTask` + `ExperimentDefinitionTaskDependency` after the run has started — a definition-tier leak.

Replace it with a run-tier helper:

```python
def get_initial_ready_tasks(session: Session, run_id: UUID) -> list[UUID]:
    """Return task_ids of run-tier graph nodes with zero in-degree.
    Reads only from run_graph_nodes + run_graph_edges."""
    incoming = (
        select(RunGraphEdge.target_task_id)
        .where(RunGraphEdge.run_id == run_id)
        .distinct()
    )
    stmt = (
        select(RunGraphNode.task_id)
        .where(RunGraphNode.run_id == run_id)
        .where(RunGraphNode.task_id.notin_(incoming))
    )
    return list(session.exec(stmt).all())
```

- [ ] **Step 2.2.3: Update `start_workflow.py` to use the new contract.**

In `jobs/start_workflow.py`, the handler currently does (roughly): `WorkflowService.initialize` → reads definition → builds graph → reads definition again via `get_initial_ready_tasks`. Update so:

1. `populate_from_definition` is the single definition read (ahead of any state transition).
2. `get_initial_ready_tasks` runs against the populated run-tier graph (no second definition read).

Pseudo-shape:

```python
async def start_workflow_fn(ctx: inngest.Context) -> JsonObject:
    payload = parse_payload(ctx, WorkflowStartedPayload)
    with session_factory() as session:
        # Single definition-tier read:
        await graph_repo.populate_from_definition(
            session, run_id=payload.run_id, definition_id=payload.definition_id,
        )
        # Run-tier read for fan-out:
        ready_task_ids = get_initial_ready_tasks(session, payload.run_id)
        # Fan out task/ready events:
        for task_id in ready_task_ids:
            await ctx.step.send_event(...)
```

(Phase 3 splits `start_workflow_fn` into `prepare_run_fn` + `advance_run_fn`. Phase 2 keeps the existing function name.)

- [ ] **Step 2.2.4: Run runtime tests.**

```bash
pytest ergon_core/tests/unit/runtime/test_propagation_contracts.py \
       ergon_core/tests/unit/runtime/test_workflow_service.py -v
```

Some failures expected if v1 propagation tests assert on old method names; sweep through and update to `populate_from_definition` / new `get_initial_ready_tasks`. (These tests are KEEP per disposition table — small fixups.)

- [ ] **Step 2.2.5: Commit.**

```bash
git add ergon_core/ergon_core/core/application/graph/ \
        ergon_core/ergon_core/core/application/jobs/start_workflow.py \
        ergon_core/tests/unit/runtime/
git commit -m "v2 phase 2.2: single definition-read boundary in populate_from_definition"
```

**DoD for 2.2:** `populate_from_definition` is the only definition-tier reader called from runtime; `get_initial_ready_tasks` is run-tier only.

### Sub-commit 2.3 — Delete `task_payload_for_execution` and `definition_task_id` DTO field

**Files:**
- Modify: `ergon_core/ergon_core/core/application/tasks/repository.py`
- Modify: `ergon_core/ergon_core/core/application/workflows/orchestration.py`

- [ ] **Step 2.3.1: Delete `TaskExecutionRepository.task_payload_for_execution`.**

Audit confirmed zero callers. Open `tasks/repository.py:78–84`, delete the method.

- [ ] **Step 2.3.2: Drop `definition_task_id` from `PreparedTaskExecution`.**

In `workflows/orchestration.py:69–75`, the comment block + field declaration document the dynamic-subtask hybrid v1 carried. Delete:

```python
# DELETE:
@dataclass
class PreparedTaskExecution:
    ...
    definition_task_id: UUID | None  # remove this field
    ...
```

Replace any callsites that read `prepared.definition_task_id` with — nothing; they shouldn't exist after 2.1. Run a grep:

```bash
rg "definition_task_id" ergon_core/
```

Expected: matches only in the deleted migration files (gone) and possibly old test assertions. Update or delete those.

- [ ] **Step 2.3.3: Run unit tests + arch guards.**

```bash
pytest ergon_core/tests/unit/runtime/ ergon_core/tests/unit/architecture/ -v 2>&1 | tail
```

Expected: most pass; some `test_definition_*` files fail because they test deleted v1 paths. Per disposition table, those get **deleted** (`test_definition_task_payload_typing.py` deletion happens here in phase 2; `test_definition_lookup_boundaries.py` deferred to phase 5):

```bash
git rm ergon_core/tests/unit/runtime/test_definition_task_payload_typing.py
```

- [ ] **Step 2.3.4: Commit.**

```bash
git add ergon_core/ergon_core/core/application/tasks/repository.py \
        ergon_core/ergon_core/core/application/workflows/orchestration.py
git rm ergon_core/tests/unit/runtime/test_definition_task_payload_typing.py
git commit -m "v2 phase 2.3: delete dead definition_task_id paths"
```

**DoD for 2.3:** `rg "definition_task_id" ergon_core/ergon_core/` returns zero matches in production code (matches in `tests/` only for the architecture guard's forbidden list, which is the intended occurrence).

### Sub-commit 2.4 — Architecture guard: runtime does not read definition tables

**Files:**
- Create: `ergon_core/tests/unit/architecture/test_runtime_read_boundary.py`

- [ ] **Step 2.4.1: Write the architecture guard.**

```python
"""Architecture guard: runtime hot paths do not read definition-tier tables.

Definition-tier reads are confined to `populate_from_definition` (single
boundary). After that, runtime works against `run_graph_nodes` /
`run_graph_edges` only.
"""

from pathlib import Path

import pytest

# Files that ARE allowed to read definition-tier tables. Update with care.
ALLOWED_DEFINITION_READERS = {
    "ergon_core/core/application/graph/repository.py",  # populate_from_definition
    "ergon_core/core/application/experiments/definition_writer.py",  # authoring path
    "ergon_core/core/application/experiments/repository.py",  # CRUD on definitions
    "ergon_core/core/application/experiments/launch.py",  # reads definition once at launch
    "ergon_core/core/application/read_models/experiments.py",  # dashboard reads
}

DEFINITION_TIER_TABLES = {
    "experiment_definitions",
    "experiment_definition_tasks",
    "experiment_definition_edges",
}

DEFINITION_TIER_ORM_CLASSES = {
    "ExperimentDefinition",
    "ExperimentDefinitionTask",
    "ExperimentDefinitionEdge",
}


def _scan_runtime_paths():
    runtime_root = Path("ergon_core/ergon_core/core/application")
    for py_file in runtime_root.rglob("*.py"):
        rel = py_file.relative_to("ergon_core/ergon_core").as_posix()
        if rel in ALLOWED_DEFINITION_READERS:
            continue
        if "tests/" in rel:
            continue
        yield py_file, rel


def test_runtime_does_not_read_definition_tables():
    violations = []
    for py_file, rel in _scan_runtime_paths():
        text = py_file.read_text()
        for name in DEFINITION_TIER_ORM_CLASSES | DEFINITION_TIER_TABLES:
            if name in text:
                violations.append(f"{rel}: references {name}")
    assert not violations, (
        "Runtime code outside ALLOWED_DEFINITION_READERS references "
        "definition-tier tables/ORM:\n" + "\n".join(violations)
    )
```

- [ ] **Step 2.4.2: Run it.**

```bash
pytest ergon_core/tests/unit/architecture/test_runtime_read_boundary.py -v
```

Expected: PASS. If it fails, the violation message will name a runtime file that still needs the read removed; iterate.

- [ ] **Step 2.4.3: Commit.**

```bash
git add ergon_core/tests/unit/architecture/test_runtime_read_boundary.py
git commit -m "v2 phase 2.4: architecture guard for runtime read boundary"
```

**DoD for phase 2 overall:**

- `_prepare_definition` deleted; single graph-native prepare path.
- `populate_from_definition` is the sole definition-tier reader called from runtime jobs.
- `get_initial_ready_tasks` reads run-tier only.
- `task_payload_for_execution` deleted (zero callers post-deletion).
- `PreparedTaskExecution.definition_task_id` deleted.
- `test_runtime_does_not_read_definition_tables` passes.
- `pytest ergon_core/tests/unit/runtime/` passes for the kept files (some test files were deleted).

---

## Phase 3 — Unified `worker_execute`, Inngest reorg, four-axis failure semantics

**Encodes:** [Δ.4](08-decisions-log.md) (sandbox owned by `worker_execute`), [Δ.5](08-decisions-log.md) (inline criteria), [06 §`task/failed` four-axis lock](06-inngest-event-contracts.md).

**Goal.** After this phase, the Inngest function registry has 6 functions instead of 13. Criteria run inline in `worker_execute`. Sandbox lifetime is `worker_execute`'s responsibility via `try/finally`. `task/failed` consumer cascades FAILED to the spawn subtree, leaves dependency-dependents at PENDING, and lets non-descendants continue. `runs.status` is `SUCCEEDED` iff every task succeeded.

This is the largest phase. **Approximate diff size: ~700 lines** (the failure-semantics work is net-new behavior).

**Files this phase touches (read in this order):**

1. `ergon_core/ergon_core/core/application/jobs/worker_execute.py` — unified body
2. `ergon_core/ergon_core/core/application/jobs/start_workflow.py` — rename + payload
3. `ergon_core/ergon_core/core/application/jobs/propagate_execution.py` — rewrite as `advance_run`
4. `ergon_core/ergon_core/core/application/jobs/complete_workflow.py` — minimal payload
5. `ergon_core/ergon_core/core/application/jobs/cancel_orphan_subtasks.py` — merge into `advance_run`
6. `ergon_core/ergon_core/core/application/jobs/models.py` — payload classes
7. `ergon_core/ergon_core/core/application/evaluation/service.py` — `evaluate(...)` inline-call shape
8. `ergon_core/ergon_core/core/infrastructure/inngest/registry.py` — `ALL_FUNCTIONS` list
9. `ergon_core/ergon_core/core/infrastructure/inngest/handlers/*.py` — handler bindings

### Sub-commit 3.1 — Rename `start_workflow_fn` → `prepare_run_fn` and lock its payload

**Files:**
- Modify: `ergon_core/ergon_core/core/application/jobs/start_workflow.py` (rename to `prepare_run.py` in 3.6)
- Modify: `ergon_core/ergon_core/core/application/jobs/models.py`
- Modify: `ergon_core/ergon_core/core/application/events/task_events.py`
- Modify: `ergon_core/ergon_core/core/infrastructure/inngest/handlers/start_workflow.py` (rename to `prepare_run.py` in 3.6)

The functional change is small (payload field name + a couple of variable renames). The rename to `prepare_run.py` is deferred to 3.6 to avoid noise during the body changes; here we just rewrite the body in place.

- [ ] **Step 3.1.1: Define `WorkflowStartedPayload` in `events/task_events.py`.**

```python
class WorkflowStartedPayload(BaseModel):
    """Payload for `workflow/started` event. Consumed by `prepare_run_fn`."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    definition_id: UUID
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Delete v1's `WorkflowStartedEvent` if its shape differs — keep one canonical name.

- [ ] **Step 3.1.2: Rewrite `start_workflow.py` body.**

```python
@inngest_client.create_function(
    fn_id="prepare_run",
    trigger=inngest.TriggerEvent(event=WORKFLOW_STARTED),
    retries=3,
)
async def prepare_run_fn(ctx: inngest.Context) -> JsonObject:
    """Consume `workflow/started`. Read definition once, populate run-tier
    graph, transition run.status PENDING → EXECUTING, fan out task/ready
    for every initial-ready task. See 06 §workflow/started."""
    payload = WorkflowStartedPayload.model_validate(ctx.event.data)

    with session_factory() as session:
        # Single definition-tier read for the whole run lifetime:
        await graph_repo.populate_from_definition(
            session, run_id=payload.run_id, definition_id=payload.definition_id,
        )
        # Run.status PENDING → EXECUTING:
        run = session.get(RunRecord, payload.run_id)
        if run is None:
            raise PrepareRunError(f"run {payload.run_id} not found")
        run.status = RunStatus.EXECUTING
        run.started_at = datetime.now(UTC)
        session.add(run)
        session.commit()

        # Run-tier read for fan-out:
        ready_task_ids = get_initial_ready_tasks(session, payload.run_id)

    # Send task/ready events:
    for task_id in ready_task_ids:
        await ctx.step.send_event(
            f"task-ready-{task_id}",
            inngest.Event(
                name=TASK_READY,
                data=TaskReadyPayload(
                    run_id=payload.run_id,
                    task_id=task_id,
                    execution_id=uuid4(),
                    generation=0,
                ).model_dump(mode="json"),
            ),
        )

    return {"ready_task_count": len(ready_task_ids)}
```

- [ ] **Step 3.1.3: Define `TaskReadyPayload` per [06](06-inngest-event-contracts.md).**

In `events/task_events.py`:

```python
class TaskReadyPayload(BaseModel):
    """Payload for `task/ready`. Consumed by `worker_execute_fn` (per 3.2)."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    generation: int  # 0 for initial dispatch, increments on retry
```

- [ ] **Step 3.1.4: Run targeted tests.**

```bash
pytest ergon_core/tests/unit/runtime/test_workflow_service.py \
       ergon_core/tests/unit/runtime/test_workflow_initialization.py -v
```

Some failures expected; update tests to use the new payload class. KEEP the test file; just update to the new shape.

- [ ] **Step 3.1.5: Commit.**

```bash
git add ergon_core/ergon_core/core/application/jobs/start_workflow.py \
        ergon_core/ergon_core/core/application/events/task_events.py \
        ergon_core/ergon_core/core/application/jobs/models.py \
        ergon_core/ergon_core/core/infrastructure/inngest/handlers/start_workflow.py \
        ergon_core/tests/unit/runtime/
git commit -m "v2 phase 3.1: prepare_run handler with v2 payload shapes"
```

**DoD for 3.1:** `prepare_run_fn` exists and consumes `workflow/started` with `WorkflowStartedPayload`; `task/ready` is dispatched with `TaskReadyPayload`. Targeted tests green.

### Sub-commit 3.2 — Unified `worker_execute_fn` (inline criteria + sandbox try/finally)

**Files:**
- Modify: `ergon_core/ergon_core/core/application/jobs/worker_execute.py`
- Modify: `ergon_core/ergon_core/core/application/evaluation/service.py`

This is the structural heart of the phase. Per [03-runtime.md "Inline criteria"](03-runtime.md), `worker_execute_fn` becomes:

```
acquire sandbox →
  try:
    run worker.execute()
    persist execution result
    for criterion in evaluators.criteria_for(task):
      run criterion.evaluate()
      persist criterion outcome
    emit task/completed
  except SomeError as e:
    persist error
    emit task/failed
  finally:
    release sandbox
```

- [ ] **Step 3.2.1: Trigger `worker_execute_fn` on `task/ready` directly.**

v1 has `task/ready → execute_task_fn → step.invoke(worker_execute_fn)`. v2 collapses that: `task/ready → worker_execute_fn` directly, no intermediate orchestrator.

In `worker_execute.py`:

```python
@inngest_client.create_function(
    fn_id="worker_execute",
    trigger=inngest.TriggerEvent(event=TASK_READY),
    retries=2,
    concurrency=inngest.Concurrency(limit=10, scope="account"),
)
async def worker_execute_fn(ctx: inngest.Context) -> JsonObject:
    payload = TaskReadyPayload.model_validate(ctx.event.data)
    # Body in 3.2.2.
```

- [ ] **Step 3.2.2: Implement the unified body.**

```python
async def worker_execute_fn(ctx: inngest.Context) -> JsonObject:
    payload = TaskReadyPayload.model_validate(ctx.event.data)

    with session_factory() as session:
        node = graph_repo.node(
            session, run_id=payload.run_id, task_id=payload.task_id
        ).require()
        task = Task.from_definition(node.task_json, task_id=payload.task_id)
        evaluators = task.evaluators

    # Acquire sandbox:
    sandbox = task.sandbox
    sandbox = await lifecycle_hub.acquire(
        sandbox, run_id=payload.run_id, task_id=payload.task_id,
    )

    try:
        # Mark execution RUNNING:
        with session_factory() as session:
            execution = TaskExecution(
                execution_id=payload.execution_id,
                run_id=payload.run_id,
                task_id=payload.task_id,
                attempt_number=payload.generation + 1,
                status=TaskExecutionStatus.RUNNING,
                started_at=datetime.now(UTC),
            )
            session.add(execution)
            session.commit()

        # Run worker.execute():
        worker_context = build_worker_context(
            run_id=payload.run_id, task_id=payload.task_id,
            execution_id=payload.execution_id, session_factory=session_factory,
        )
        worker_output: WorkerOutput | None = None
        async for chunk in task.worker.execute(task=task, context=worker_context, sandbox=sandbox):
            await context_event_service.persist(chunk, execution_id=payload.execution_id)
            if isinstance(chunk, WorkerOutput):
                worker_output = chunk

        if worker_output is None:
            raise WorkerError("worker yielded no WorkerOutput")

        # Persist worker result:
        with session_factory() as session:
            execution = session.get(TaskExecution, payload.execution_id)
            execution.final_assistant_message = worker_output.final_assistant_message
            execution.output_json = worker_output.model_dump(mode="json")
            session.add(execution)
            session.commit()

        # ── Inline criteria evaluation (Δ.5) ─────────────────────────
        criterion_context = CriterionContext(
            run_id=payload.run_id,
            task_id=payload.task_id,
            execution_id=payload.execution_id,
            task=task,
            worker_result=worker_output,
            sandbox_id=sandbox.sandbox_id,
            metadata={},
        )
        criteria = list(evaluators.criteria_for(task))
        outcomes: list[CriterionOutcome] = []
        for criterion in criteria:
            outcome = await criterion.evaluate(
                context=criterion_context, sandbox=sandbox,
            )
            outcomes.append(outcome)
            with session_factory() as session:
                session.add(CriterionOutcomeRecord(
                    outcome_id=uuid4(),
                    run_id=payload.run_id,
                    execution_id=payload.execution_id,
                    criterion_slug=criterion.slug,
                    score=outcome.score,
                    passed=outcome.passed,
                    evidence_json=outcome.evidence.model_dump(mode="json"),
                ))
                session.commit()

        # Mark execution + node SUCCEEDED:
        with session_factory() as session:
            execution = session.get(TaskExecution, payload.execution_id)
            execution.status = TaskExecutionStatus.SUCCEEDED
            execution.completed_at = datetime.now(UTC)
            session.add(execution)

            node = session.get(RunGraphNode, (payload.run_id, payload.task_id))
            node.status = "succeeded"
            session.add(node)

            session.commit()

        # Emit task/completed:
        await ctx.step.send_event(
            f"task-completed-{payload.task_id}",
            inngest.Event(
                name=TASK_COMPLETED,
                data=TaskCompletedPayload(
                    run_id=payload.run_id,
                    task_id=payload.task_id,
                    execution_id=payload.execution_id,
                ).model_dump(mode="json"),
            ),
        )
        return {"status": "succeeded"}

    except Exception as exc:
        # Persist failure:
        with session_factory() as session:
            execution = session.get(TaskExecution, payload.execution_id)
            if execution is not None:
                execution.status = TaskExecutionStatus.FAILED
                execution.completed_at = datetime.now(UTC)
                execution.error_json = {"type": type(exc).__name__, "message": str(exc)}
                session.add(execution)

            node = session.get(RunGraphNode, (payload.run_id, payload.task_id))
            if node is not None:
                node.status = "failed"
                node.last_error = str(exc)[:4000]
                session.add(node)

            session.commit()

        # Emit task/failed:
        await ctx.step.send_event(
            f"task-failed-{payload.task_id}",
            inngest.Event(
                name=TASK_FAILED,
                data=TaskFailedPayload(
                    run_id=payload.run_id,
                    task_id=payload.task_id,
                    execution_id=payload.execution_id,
                    error=str(exc)[:4000],
                    failure_class=_classify_failure(exc),
                ).model_dump(mode="json"),
            ),
        )
        raise  # Inngest sees the exception, retries up to `retries=2`.

    finally:
        # Δ.4: worker_execute owns sandbox lifetime.
        await lifecycle_hub.release(sandbox)
```

The `_classify_failure` helper inspects the exception type:

```python
def _classify_failure(exc: Exception) -> str:
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    if isinstance(exc, CriterionCheckError):
        return "criterion_error"
    if isinstance(exc, SandboxNotLiveError):
        return "sandbox_error"
    return "worker_error"
```

- [ ] **Step 3.2.3: Strip `EvaluationService.prepare_dispatch`; keep `evaluate(...)`.**

In `evaluation/service.py`, delete `prepare_dispatch`. The remaining `evaluate(...)` callable is what `worker_execute_fn` calls inside the criteria loop above (or, equivalently, calls `criterion.evaluate(...)` directly — pick one and stick with it; the v2 spec calls the public `criterion.evaluate(context=..., sandbox=...)` directly without a service intermediary). Update the file and any tests.

- [ ] **Step 3.2.4: Run targeted tests.**

```bash
pytest ergon_core/tests/unit/runtime/test_worker_execute_sandbox_lifecycle.py -v
```

Expected: this test currently asserts on v1's release-on-error-only behavior. UPDATE it to assert release happens on both happy and error paths (the `try/finally` covers both):

```python
async def test_worker_execute_releases_sandbox_on_happy_path():
    ...
    await worker_execute_fn(ctx)
    assert lifecycle_hub.release.call_count == 1


async def test_worker_execute_releases_sandbox_on_failure():
    ...
    with pytest.raises(WorkerError):
        await worker_execute_fn(ctx)
    assert lifecycle_hub.release.call_count == 1
```

- [ ] **Step 3.2.5: Commit.**

```bash
git add ergon_core/ergon_core/core/application/jobs/worker_execute.py \
        ergon_core/ergon_core/core/application/evaluation/service.py \
        ergon_core/tests/unit/runtime/test_worker_execute_sandbox_lifecycle.py
git commit -m "v2 phase 3.2: worker_execute owns sandbox lifetime; criteria run inline"
```

**DoD for 3.2:** `worker_execute_fn` releases the sandbox in a `finally` block; criteria run inline; the `prepare_dispatch` symbol does not exist.

### Sub-commit 3.3 — Delete dead Inngest handlers and the `CriterionExecutor` Protocol

**Files:**
- Delete: `ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py`
- Delete: `ergon_core/ergon_core/core/application/jobs/check_evaluators.py`
- Delete: `ergon_core/ergon_core/core/application/jobs/execute_task.py`
- Delete: `ergon_core/ergon_core/core/application/jobs/fail_workflow.py`
- Delete: `ergon_core/ergon_core/core/application/evaluation/executors.py` (Protocol)
- Delete: `ergon_core/ergon_core/core/application/evaluation/inngest_executor.py` (impl)
- Delete: `ergon_core/ergon_core/core/infrastructure/inngest/handlers/evaluate_task_run.py`
- Delete: `ergon_core/ergon_core/core/infrastructure/inngest/handlers/check_evaluators.py`
- Delete: `ergon_core/ergon_core/core/infrastructure/inngest/handlers/execute_task.py`
- Delete: `ergon_core/ergon_core/core/infrastructure/inngest/handlers/fail_workflow.py`
- Delete: `ergon_core/tests/unit/runtime/test_inngest_criterion_executor.py`
- Delete: `ergon_core/tests/unit/runtime/test_child_function_payloads.py`

- [ ] **Step 3.3.1: Delete the files in one go.**

```bash
git rm ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py \
       ergon_core/ergon_core/core/application/jobs/check_evaluators.py \
       ergon_core/ergon_core/core/application/jobs/execute_task.py \
       ergon_core/ergon_core/core/application/jobs/fail_workflow.py \
       ergon_core/ergon_core/core/application/evaluation/executors.py \
       ergon_core/ergon_core/core/application/evaluation/inngest_executor.py \
       ergon_core/ergon_core/core/infrastructure/inngest/handlers/evaluate_task_run.py \
       ergon_core/ergon_core/core/infrastructure/inngest/handlers/check_evaluators.py \
       ergon_core/ergon_core/core/infrastructure/inngest/handlers/execute_task.py \
       ergon_core/ergon_core/core/infrastructure/inngest/handlers/fail_workflow.py \
       ergon_core/tests/unit/runtime/test_inngest_criterion_executor.py \
       ergon_core/tests/unit/runtime/test_child_function_payloads.py
```

- [ ] **Step 3.3.2: Sweep for stale imports.**

```bash
rg "evaluate_task_run|check_evaluators|execute_task_fn|fail_workflow_fn|CriterionExecutor|InngestCriterionExecutor|EvaluateTaskRunRequest" ergon_core/
```

Expected: matches in tests/architecture/test_public_api_target_structure.py forbidden lists (intended). Any matches in production code are stale imports — fix them. Common targets: `core/application/__init__.py`, `core/application/jobs/__init__.py`, `infrastructure/inngest/__init__.py`. Strip the imports.

- [ ] **Step 3.3.3: Run unit tests.**

```bash
pytest ergon_core/tests/unit/runtime/ ergon_core/tests/unit/architecture/ -v 2>&1 | tail -30
```

Expected: failures only on `test_propagation_contracts.py` and `test_failed_task_sandbox_cleanup.py` (both rewrite targets in 3.4).

- [ ] **Step 3.3.4: Commit.**

```bash
git add ergon_core/ergon_core/core/application/ \
        ergon_core/ergon_core/core/infrastructure/inngest/ \
        ergon_core/tests/unit/runtime/
git commit -m "v2 phase 3.3: delete dead Inngest handlers and CriterionExecutor"
```

**DoD for 3.3:** `rg` for the deleted symbol names returns zero production-code matches.

### Sub-commit 3.4 — `advance_run_fn` with four-axis failure semantics

**Files:**
- Modify: `ergon_core/ergon_core/core/application/jobs/propagate_execution.py` (rename to `advance_run.py`)
- Modify: `ergon_core/ergon_core/core/application/graph/propagation.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/cancel_orphan_subtasks.py` (delete; behavior folded into `advance_run`)
- Modify: `ergon_core/ergon_core/core/application/workflows/service.py` (delete `propagate_failure`; update `propagate`)
- Create: `ergon_core/tests/unit/runtime/test_advance_run_failure_axes.py`

This sub-commit is where the four-axis lock from [06 §`task/failed`](06-inngest-event-contracts.md) becomes code. Read that section before starting.

- [ ] **Step 3.4.1: Define the spawn-subtree walk helper.**

In `graph/traversal.py`:

```python
def spawn_subtree_task_ids(session: Session, *, run_id: UUID, root_task_id: UUID) -> list[UUID]:
    """Return all task_ids in the spawn subtree rooted at root_task_id.
    Spawn relationships are tracked via RunGraphNode.parent_task_id (not via edges)."""
    result: list[UUID] = []
    queue: list[UUID] = [root_task_id]
    while queue:
        current = queue.pop()
        children_stmt = select(RunGraphNode.task_id).where(
            RunGraphNode.run_id == run_id,
            RunGraphNode.parent_task_id == current,
        )
        for (child_id,) in session.exec(children_stmt).all():
            result.append(child_id)
            queue.append(child_id)
    return result
```

- [ ] **Step 3.4.2: Define `is_run_terminal` per [06](06-inngest-event-contracts.md).**

In `graph/propagation.py`, replace the v1 `is_workflow_complete_v2` / `is_workflow_failed_v2` helpers with:

```python
def is_run_terminal(session: Session, run_id: UUID) -> tuple[bool, RunStatus | None]:
    """A run is terminal when no task is RUNNING and no PENDING task is dispatchable
    (every PENDING task has at least one FAILED or stuck-PENDING dep).

    Returns (is_terminal, final_status). final_status is SUCCEEDED iff every
    task is SUCCEEDED, FAILED otherwise (PENDING-stuck tasks count as not-succeeded)."""

    nodes = session.exec(
        select(RunGraphNode).where(RunGraphNode.run_id == run_id)
    ).all()
    by_id = {n.task_id: n for n in nodes}

    # Any RUNNING task → not terminal:
    if any(n.status == "running" for n in nodes):
        return False, None

    # PENDING tasks: dispatchable if all deps SUCCEEDED. If any is dispatchable,
    # not terminal (advance_run should fan it out).
    deps_by_target = _build_deps_by_target(session, run_id)
    for n in nodes:
        if n.status != "pending":
            continue
        deps = deps_by_target.get(n.task_id, [])
        if all(by_id[d].status == "succeeded" for d in deps):
            return False, None

    # Otherwise terminal. Compute final_status:
    if all(n.status == "succeeded" for n in nodes):
        return True, RunStatus.SUCCEEDED
    return True, RunStatus.FAILED


def _build_deps_by_target(session: Session, run_id: UUID) -> dict[UUID, list[UUID]]:
    edges = session.exec(
        select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)
    ).all()
    deps: dict[UUID, list[UUID]] = {}
    for e in edges:
        deps.setdefault(e.target_task_id, []).append(e.source_task_id)
    return deps
```

- [ ] **Step 3.4.3: Implement `advance_run_fn`.**

Rename `jobs/propagate_execution.py` to `jobs/advance_run.py` and rewrite. The body consumes both `task/completed` and `task/failed`:

```python
@inngest_client.create_function(
    fn_id="advance_run",
    trigger=[
        inngest.TriggerEvent(event=TASK_COMPLETED),
        inngest.TriggerEvent(event=TASK_FAILED),
    ],
    retries=5,
)
async def advance_run_fn(ctx: inngest.Context) -> JsonObject:
    event_name = ctx.event.name
    if event_name == TASK_COMPLETED:
        payload = TaskCompletedPayload.model_validate(ctx.event.data)
        return await _on_task_completed(ctx, payload)
    elif event_name == TASK_FAILED:
        payload = TaskFailedPayload.model_validate(ctx.event.data)
        return await _on_task_failed(ctx, payload)
    raise ValueError(f"unexpected trigger event: {event_name}")


async def _on_task_completed(ctx, payload: TaskCompletedPayload) -> JsonObject:
    """Fan out task/ready for newly-dispatchable tasks, or fire workflow/completed."""
    with session_factory() as session:
        # Find dispatchable tasks (deps now all SUCCEEDED, not yet RUNNING):
        ready_task_ids = _find_newly_dispatchable(session, payload.run_id, payload.task_id)
        terminal, final_status = is_run_terminal(session, payload.run_id)

    for task_id in ready_task_ids:
        await ctx.step.send_event(
            f"task-ready-{task_id}",
            inngest.Event(
                name=TASK_READY,
                data=TaskReadyPayload(
                    run_id=payload.run_id, task_id=task_id,
                    execution_id=uuid4(), generation=0,
                ).model_dump(mode="json"),
            ),
        )

    if terminal:
        await _fire_workflow_completed(ctx, payload.run_id, final_status)
    return {"dispatched": len(ready_task_ids), "terminal": terminal}


async def _on_task_failed(ctx, payload: TaskFailedPayload) -> JsonObject:
    """Four-axis failure lock per 06 §task/failed:
    - Spawn-children of failed task: cascade FAILED.
    - Dependency-dependents: stay PENDING (no action).
    - Non-descendants: continue (no action).
    - Re-evaluate run terminal state.
    """
    with session_factory() as session:
        # Axis 1: spawn-subtree cascade.
        descendant_ids = spawn_subtree_task_ids(
            session, run_id=payload.run_id, root_task_id=payload.task_id,
        )
        for desc_id in descendant_ids:
            node = session.get(RunGraphNode, (payload.run_id, desc_id))
            if node is None or node.status in {"succeeded", "failed", "cancelled"}:
                continue
            node.status = "failed"
            node.last_error = f"spawn-parent {payload.task_id} failed"
            session.add(node)

        session.commit()

        # Axis 2 + 3: re-evaluate run terminal state.
        terminal, final_status = is_run_terminal(session, payload.run_id)

    if terminal:
        await _fire_workflow_completed(ctx, payload.run_id, final_status)
    return {"cascaded_count": len(descendant_ids), "terminal": terminal}


async def _fire_workflow_completed(ctx, run_id: UUID, final_status: RunStatus) -> None:
    await ctx.step.send_event(
        f"workflow-completed-{run_id}",
        inngest.Event(
            name=WORKFLOW_COMPLETED,
            data=WorkflowCompletedPayload(
                run_id=run_id, final_status=final_status.value,
            ).model_dump(mode="json"),
        ),
    )
```

`_find_newly_dispatchable` is a small helper that returns task_ids whose `depends_on` set is fully SUCCEEDED and whose own status is PENDING.

- [ ] **Step 3.4.4: Delete `cancel_orphan_subtasks.py` and its handler.**

```bash
git rm ergon_core/ergon_core/core/application/jobs/cancel_orphan_subtasks.py \
       ergon_core/ergon_core/core/infrastructure/inngest/handlers/cancel_orphan_subtasks.py
```

The behavior is now in `_on_task_failed`'s spawn-subtree walk.

- [ ] **Step 3.4.5: Write four-axis tests.**

In `ergon_core/tests/unit/runtime/test_advance_run_failure_axes.py`:

```python
"""Tests for the four-axis failure lock per 06-inngest-event-contracts.md."""

async def test_axis_1_spawn_children_cascade_failed():
    """When task A fails, every descendant in the spawn subtree is marked FAILED."""
    run_id = ...
    task_a, task_a_child, task_a_grandchild = ...
    # Setup: task_a_child.parent_task_id = task_a; task_a_grandchild.parent_task_id = task_a_child.
    # Mark task_a as FAILED.

    await advance_run_fn(_failed_ctx(run_id, task_a))

    with session_factory() as session:
        assert session.get(RunGraphNode, (run_id, task_a_child)).status == "failed"
        assert session.get(RunGraphNode, (run_id, task_a_grandchild)).status == "failed"


async def test_axis_2_dependency_dependents_stay_pending():
    """When task A fails and task B has depends_on=[A], task B stays PENDING."""
    run_id = ...
    task_a, task_b = ...  # B depends on A via run_graph_edges

    await advance_run_fn(_failed_ctx(run_id, task_a))

    with session_factory() as session:
        assert session.get(RunGraphNode, (run_id, task_b)).status == "pending"


async def test_axis_3_run_status_failed_if_any_pending_stuck():
    """Run is FAILED (not SUCCEEDED) if any task is stuck-PENDING at terminal."""
    run_id = ...
    task_a, task_b = ...  # B depends on A; A fails

    await advance_run_fn(_failed_ctx(run_id, task_a))

    with session_factory() as session:
        run = session.get(RunRecord, run_id)
        # advance_run fires workflow/completed; the actual run.status update
        # happens in complete_workflow_fn (3.5). Here we assert the
        # workflow/completed event payload:
        sent_events = _captured_events_in_test_harness(...)
        assert any(
            e.name == WORKFLOW_COMPLETED and e.data["final_status"] == "failed"
            for e in sent_events
        )


async def test_axis_4_non_descendants_continue():
    """Independent subtree continues running when a parallel subtree fails."""
    run_id = ...
    task_a, task_a_child, task_b = ...  # task_b is independent of task_a

    await advance_run_fn(_failed_ctx(run_id, task_a))

    with session_factory() as session:
        # task_b is unaffected; its status is whatever it was before.
        assert session.get(RunGraphNode, (run_id, task_b)).status != "failed"
```

(Test fixtures `_failed_ctx`, `_captured_events_in_test_harness` are sketched — fill in per local test idioms.)

- [ ] **Step 3.4.6: Run.**

```bash
pytest ergon_core/tests/unit/runtime/test_advance_run_failure_axes.py -v
```

Expected: 4 PASSED.

- [ ] **Step 3.4.7: Commit.**

```bash
git add ergon_core/ergon_core/core/application/jobs/ \
        ergon_core/ergon_core/core/application/graph/ \
        ergon_core/ergon_core/core/application/workflows/service.py \
        ergon_core/tests/unit/runtime/test_advance_run_failure_axes.py
git rm ergon_core/ergon_core/core/application/jobs/cancel_orphan_subtasks.py \
       ergon_core/ergon_core/core/infrastructure/inngest/handlers/cancel_orphan_subtasks.py
git commit -m "v2 phase 3.4: advance_run with four-axis failure semantics"
```

**DoD for 3.4:** Four-axis test cases pass; `advance_run_fn` is the single consumer of `task/completed` + `task/failed`; `cancel_orphan_subtasks_fn` deleted.

### Sub-commit 3.5 — `complete_workflow_fn` with minimal payload; cleanup linkage

**Files:**
- Modify: `ergon_core/ergon_core/core/application/jobs/complete_workflow.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/run_cleanup.py`
- Modify: `ergon_core/ergon_core/core/application/events/task_events.py`

- [ ] **Step 3.5.1: Define minimal `WorkflowCompletedPayload`.**

```python
class WorkflowCompletedPayload(BaseModel):
    """Minimal payload per [06 Decisions locked at workshop]."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    final_status: Literal["succeeded", "failed"]
```

- [ ] **Step 3.5.2: Rewrite `complete_workflow_fn`.**

```python
@inngest_client.create_function(
    fn_id="complete_workflow",
    trigger=inngest.TriggerEvent(event=WORKFLOW_COMPLETED),
    retries=3,
)
async def complete_workflow_fn(ctx: inngest.Context) -> JsonObject:
    payload = WorkflowCompletedPayload.model_validate(ctx.event.data)

    with session_factory() as session:
        run = session.get(RunRecord, payload.run_id)
        if run is None:
            raise CompleteWorkflowError(f"run {payload.run_id} not found")
        run.status = (
            RunStatus.SUCCEEDED if payload.final_status == "succeeded" else RunStatus.FAILED
        )
        run.completed_at = datetime.now(UTC)
        session.add(run)
        session.commit()

    # Best-effort sandbox sweep:
    await ctx.step.send_event(
        f"run-cleanup-{payload.run_id}",
        inngest.Event(
            name=RUN_CLEANUP,
            data={"run_id": str(payload.run_id)},
        ),
    )

    return {"final_status": payload.final_status}
```

- [ ] **Step 3.5.3: `run_cleanup_fn` stays as best-effort backstop.**

The audit found `run_cleanup_fn` at `jobs/run_cleanup.py:59` calls `terminate_sandbox_by_id` from `RunRecord.summary_json["sandbox_id"]`. Since `worker_execute_fn` now releases sandboxes in `try/finally` (3.2), `run_cleanup` is rarely needed in practice — but keeps the role of "anything that escaped, sweep it." Keep the body; just confirm it doesn't break with v2's `summary_json` shape.

- [ ] **Step 3.5.4: Delete `summary_json["sandbox_id"]` writer in worker_execute (no longer needed).**

In `worker_execute.py`, the v1 code wrote `sandbox_id` into `RunRecord.summary_json` so `run_cleanup` could find it. With per-task release, this is dead. Remove the writer.

(`run_cleanup_fn` will see `None` for `sandbox_id` and no-op. That's the intended behavior.)

- [ ] **Step 3.5.5: Commit.**

```bash
git add ergon_core/ergon_core/core/application/jobs/complete_workflow.py \
        ergon_core/ergon_core/core/application/jobs/run_cleanup.py \
        ergon_core/ergon_core/core/application/jobs/worker_execute.py \
        ergon_core/ergon_core/core/application/events/task_events.py
git commit -m "v2 phase 3.5: minimal workflow/completed payload; run_cleanup as backstop"
```

**DoD for 3.5:** `complete_workflow_fn` consumes the minimal payload and writes `runs.status`; `run_cleanup_fn` is best-effort.

### Sub-commit 3.6 — Inngest registry + handler renames

**Files:**
- Modify: `ergon_core/ergon_core/core/infrastructure/inngest/registry.py`
- Rename: handlers and jobs files for clarity

- [ ] **Step 3.6.1: Update `ALL_FUNCTIONS` to v2 shape.**

```python
ALL_FUNCTIONS: list[inngest.Function] = [
    prepare_run_fn,
    worker_execute_fn,
    advance_run_fn,
    complete_workflow_fn,
    cleanup_cancelled_task_fn,
    run_cleanup_fn,
]
```

Six functions, down from 13. Verify the imports at the top of `registry.py` match.

- [ ] **Step 3.6.2: Rename files for consistency.**

```bash
git mv ergon_core/ergon_core/core/application/jobs/start_workflow.py \
       ergon_core/ergon_core/core/application/jobs/prepare_run.py
git mv ergon_core/ergon_core/core/application/jobs/propagate_execution.py \
       ergon_core/ergon_core/core/application/jobs/advance_run.py
git mv ergon_core/ergon_core/core/infrastructure/inngest/handlers/start_workflow.py \
       ergon_core/ergon_core/core/infrastructure/inngest/handlers/prepare_run.py
git mv ergon_core/ergon_core/core/infrastructure/inngest/handlers/propagate_execution.py \
       ergon_core/ergon_core/core/infrastructure/inngest/handlers/advance_run.py
```

Update imports in `registry.py` and `jobs/__init__.py` accordingly.

- [ ] **Step 3.6.3: Run import smoke + arch tests.**

```bash
python -c "from ergon_core.core.infrastructure.inngest.registry import ALL_FUNCTIONS; \
           print(len(ALL_FUNCTIONS), [f.id for f in ALL_FUNCTIONS])"
```

Expected: `6 ['prepare_run', 'worker_execute', 'advance_run', 'complete_workflow', 'cleanup_cancelled_task', 'run_cleanup']`.

- [ ] **Step 3.6.4: Commit.**

```bash
git add ergon_core/ergon_core/core/infrastructure/inngest/ \
        ergon_core/ergon_core/core/application/jobs/
git commit -m "v2 phase 3.6: Inngest registry shrunk to 6 functions"
```

**DoD for 3.6:** `ALL_FUNCTIONS` has exactly 6 entries with the v2 names; all imports succeed.

### Sub-commit 3.7 — Phase 3 architecture guards

**Files:**
- Create: `ergon_core/tests/unit/architecture/test_inngest_v2_shape.py`

- [ ] **Step 3.7.1: Write the architecture guards.**

```python
"""Architecture guards for v2 Inngest shape (phase 3 deliverables)."""

from ergon_core.core.infrastructure.inngest.registry import ALL_FUNCTIONS


def test_inngest_registry_has_six_functions():
    """v2 ships exactly 6 Inngest functions per [06]."""
    assert len(ALL_FUNCTIONS) == 6
    fn_ids = {f.id for f in ALL_FUNCTIONS}
    assert fn_ids == {
        "prepare_run",
        "worker_execute",
        "advance_run",
        "complete_workflow",
        "cleanup_cancelled_task",
        "run_cleanup",
    }


def test_no_evaluate_task_run_function():
    """v2 deletes evaluate_task_run; criteria run inline in worker_execute."""
    fn_ids = {f.id for f in ALL_FUNCTIONS}
    forbidden = {"evaluate_task_run", "check_evaluators", "execute_task",
                 "fail_workflow", "cancel_orphan_subtasks", "propagate_task"}
    assert not (forbidden & fn_ids)


def test_sandbox_release_in_worker_execute_finally():
    """worker_execute owns sandbox lifetime via try/finally per Δ.4."""
    src = Path("ergon_core/ergon_core/core/application/jobs/worker_execute.py").read_text()
    # Crude but effective: assert the finally block exists and contains release.
    assert "finally:" in src
    finally_block = src.split("finally:", 1)[1]
    assert "lifecycle_hub.release" in finally_block, \
        "worker_execute's finally block must call lifecycle_hub.release"


def test_no_other_release_callsites():
    """Only worker_execute calls lifecycle_hub.release (and its own try/finally)."""
    runtime_root = Path("ergon_core/ergon_core/core/application")
    allowed = {"jobs/worker_execute.py"}
    violations = []
    for py_file in runtime_root.rglob("*.py"):
        rel = py_file.relative_to(runtime_root).as_posix()
        if rel in allowed:
            continue
        text = py_file.read_text()
        if "lifecycle_hub.release" in text:
            violations.append(rel)
    assert not violations, f"Unexpected lifecycle_hub.release callsites: {violations}"
```

- [ ] **Step 3.7.2: Run.**

```bash
pytest ergon_core/tests/unit/architecture/test_inngest_v2_shape.py -v
```

Expected: 4 PASSED.

- [ ] **Step 3.7.3: Commit.**

```bash
git add ergon_core/tests/unit/architecture/test_inngest_v2_shape.py
git commit -m "v2 phase 3.7: architecture guards for v2 Inngest shape"
```

**DoD for phase 3 overall:**

- 6-function Inngest registry; v2 event payloads.
- `worker_execute_fn` runs criteria inline and releases sandbox in `finally`.
- `advance_run_fn` consumes both `task/completed` and `task/failed` with the four-axis lock.
- `complete_workflow_fn` consumes minimal `WorkflowCompletedPayload`.
- 4 four-axis failure tests pass + 4 architecture guards pass.
- `pytest ergon_core/tests/unit/runtime/ ergon_core/tests/unit/architecture/` all pass.

---

## Phase 4 — Dynamic subtasks graph-native

**Encodes:** [Δ.3](08-decisions-log.md) (dynamic subtasks live in `run_graph_nodes`, no synthetic definition row).

**Goal.** After this phase, `WorkerContext.spawn_task` writes only to `run_graph_nodes` with `is_dynamic = TRUE`. There is no synthetic `experiment_definition_tasks` row for spawned tasks. Lookups discriminate on `is_dynamic`.

**Audit finding:** v1 already routes `spawn_task` through `WorkflowGraphRepository.add_node` only — the dreaded `materialize_dynamic_subtask_definition` does not exist. **Phase 4 is mostly verification + the `is_dynamic` flag wiring**, not a refactor.

**Approximate diff size: ~150 lines** (smaller than original estimate; the audit found the work already mostly done).

**Files this phase touches:**

1. `ergon_core/ergon_core/core/application/tasks/management.py` — `add_subtask` body
2. `ergon_core/ergon_core/core/application/graph/repository.py` — `add_node` signature + body
3. `ergon_core/ergon_core/api/worker/context.py` — `spawn_task` (verify; should not need changes)

### Sub-commit 4.1 — Set `is_dynamic = TRUE` on dynamically-spawned graph nodes

**Files:**
- Modify: `ergon_core/ergon_core/core/application/graph/repository.py`
- Modify: `ergon_core/ergon_core/core/application/tasks/management.py`

- [ ] **Step 4.1.1: Add `is_dynamic` parameter to `add_node`.**

In `graph/repository.py`, `WorkflowGraphRepository.add_node` currently inserts `RunGraphNode` rows for both static (from `populate_from_definition`) and dynamic (from `spawn_task`). Add a kwarg:

```python
async def add_node(
    self,
    session: Session,
    *,
    run_id: UUID,
    task: Task,
    task_id: UUID,
    task_json: dict[str, Any],
    parent_task_id: UUID | None = None,
    level: int = 0,
    is_dynamic: bool = False,           # ← new
    meta: MutationMeta,
) -> GraphNodeDto:
    node = RunGraphNode(
        run_id=run_id,
        task_id=task_id,
        task_json=task_json,
        status="pending",
        parent_task_id=parent_task_id,
        level=level,
        is_dynamic=is_dynamic,           # ← propagate
    )
    session.add(node)
    ...
```

- [ ] **Step 4.1.2: `populate_from_definition` passes `is_dynamic=False`.**

In the same file, the `populate_from_definition` body (renamed in 2.2) loops over definition tasks and calls `add_node(...)`. Pass `is_dynamic=False` explicitly (it's the default, but explicit is better here):

```python
await self.add_node(
    session, run_id=run_id, task=task, task_id=task.task_id,
    task_json=task.to_definition(), is_dynamic=False, meta=...,
)
```

- [ ] **Step 4.1.3: `TaskManagementService.add_subtask` passes `is_dynamic=True`.**

In `tasks/management.py`, `add_subtask` is the path called from `WorkerContext.spawn_task`. Update the `add_node` call to pass `is_dynamic=True`:

```python
async def add_subtask(
    self,
    session: Session,
    *,
    run_id: UUID,
    parent_task_id: UUID,
    task: Task,
    depends_on: list[UUID],
) -> SpawnedTaskHandle:
    ...
    parent_node = self._graph_repo.node(session, run_id=run_id, task_id=parent_task_id).require()
    node = await self._graph_repo.add_node(
        session, run_id=run_id,
        task=task, task_id=uuid4(),
        task_json=task.to_definition(),
        parent_task_id=parent_task_id,
        level=parent_node.level + 1,
        is_dynamic=True,                  # ← phase 4 lock
        meta=...,
    )
    ...
```

- [ ] **Step 4.1.4: Run targeted tests.**

```bash
pytest ergon_core/tests/unit/runtime/test_worker_context_spawn_task.py -v
```

Update assertions to check `is_dynamic == True` on the spawned node.

- [ ] **Step 4.1.5: Commit.**

```bash
git add ergon_core/ergon_core/core/application/graph/repository.py \
        ergon_core/ergon_core/core/application/tasks/management.py \
        ergon_core/tests/unit/runtime/
git commit -m "v2 phase 4.1: is_dynamic=TRUE for spawned tasks; FALSE for definition-derived"
```

**DoD for 4.1:** `add_node` carries `is_dynamic`; static path passes FALSE, spawn path passes TRUE.

### Sub-commit 4.2 — Architecture guard: no synthetic definition rows for dynamic tasks

**Files:**
- Create: `ergon_core/tests/unit/architecture/test_dynamic_subtask_graph_native.py`

- [ ] **Step 4.2.1: Write the guard.**

```python
"""Architecture guard: dynamic subtasks live exclusively in run_graph_nodes.

There is no `materialize_dynamic_subtask_definition` (or similar) function
that writes a synthetic experiment_definition_tasks row for spawned tasks.
This is the Δ.3 lock made testable.
"""

from pathlib import Path
import re


def test_no_synthetic_definition_row_for_dynamic_tasks():
    """No code path inserts experiment_definition_tasks rows from a spawn-path callsite."""
    forbidden_function_names = [
        "materialize_dynamic_subtask_definition",
        "create_dynamic_definition_task",
        "_persist_spawned_task_to_definition_tier",
    ]
    runtime_root = Path("ergon_core/ergon_core")
    violations = []
    for py_file in runtime_root.rglob("*.py"):
        text = py_file.read_text()
        for name in forbidden_function_names:
            if name in text:
                violations.append(f"{py_file}: defines or references {name}")
    assert not violations, "Forbidden synthetic-definition functions present:\n" + "\n".join(violations)


def test_spawn_task_path_sets_is_dynamic():
    """TaskManagementService.add_subtask must call add_node with is_dynamic=True."""
    src = Path("ergon_core/ergon_core/core/application/tasks/management.py").read_text()
    add_subtask = re.search(r"async def add_subtask\b.*?(?=\n    (?:async )?def |\nclass )",
                            src, re.DOTALL)
    assert add_subtask is not None, "add_subtask method not found"
    body = add_subtask.group(0)
    assert "is_dynamic=True" in body, \
        "add_subtask must pass is_dynamic=True to add_node (Δ.3 lock)"


def test_populate_from_definition_sets_is_dynamic_false():
    """populate_from_definition is the static path; is_dynamic=False."""
    src = Path("ergon_core/ergon_core/core/application/graph/repository.py").read_text()
    populate = re.search(r"async def populate_from_definition\b.*?(?=\n    (?:async )?def |\nclass )",
                         src, re.DOTALL)
    assert populate is not None
    body = populate.group(0)
    assert "is_dynamic=False" in body
```

- [ ] **Step 4.2.2: Run.**

```bash
pytest ergon_core/tests/unit/architecture/test_dynamic_subtask_graph_native.py -v
```

Expected: 3 PASSED.

- [ ] **Step 4.2.3: Commit.**

```bash
git add ergon_core/tests/unit/architecture/test_dynamic_subtask_graph_native.py
git commit -m "v2 phase 4.2: architecture guard for graph-native dynamic subtasks"
```

**DoD for phase 4 overall:**

- `is_dynamic` is set correctly per spawn vs static path.
- 3 architecture guards pass.
- `pytest ergon_core/tests/unit/runtime/test_worker_context_spawn_task.py` and friends pass.

---

## Phase 5 — Symbol deletions and CLI rewrite

**Encodes:** [Δ.7](08-decisions-log.md) (deletions), [Δ.8](08-decisions-log.md) (CLI as composition convenience).

**Goal.** After this phase: `Worker.from_buffer`, `saved_specs` package, `terminate_sandbox_by_id` stub, `_persist_single_sample_workflow_definition` factory plumbing, `task_payload_for_execution`, `definition_task_id → node_id` lookup are all gone. The CLI command `ergon experiment define <slug>` calls `persist_definition` directly; `ergon experiment run <definition-id>` calls `launch_run` directly.

**Files this phase touches:**

1. `ergon_core/ergon_core/api/worker/worker.py` — delete `from_buffer`
2. `ergon_core/ergon_core/core/persistence/saved_specs/` — delete directory
3. `ergon_core/ergon_core/core/infrastructure/sandbox/lifecycle.py` — delete `terminate_sandbox_by_id`
4. `ergon_core/ergon_core/core/application/experiments/launch.py` — full rewrite
5. `ergon_core/ergon_core/core/application/experiments/service.py` — delete `define_benchmark_experiment`
6. `ergon_core/ergon_core/core/application/graph/lookup.py` — delete `GraphNodeLookup` (definition_task_id→node_id)
7. `ergon_cli/ergon_cli/commands/experiment.py` — full rewrite

### Sub-commit 5.1 — Delete `Worker.from_buffer` (zero callers)

**Files:**
- Modify: `ergon_core/ergon_core/api/worker/worker.py`

- [ ] **Step 5.1.1: Verify zero callers.**

```bash
rg "from_buffer" ergon_core/ ergon_builtins/ ergon_cli/
```

Expected: matches only in the definition + (possibly) `ergon_builtins/.../react_worker.py`. Per audit, the api `from_buffer` returns None and has zero callers; if `react_worker` has its own `from_buffer` *method* that's named the same but is unrelated, leave it.

- [ ] **Step 5.1.2: Delete the classmethod.**

In `api/worker/worker.py`, delete:

```python
@classmethod
def from_buffer(
    cls,
    execution_id: UUID,
    session: Any,
    **kwargs: Any,
) -> Self | None:
    """Construct a worker pre-seeded with context event history."""
    return None
```

- [ ] **Step 5.1.3: Run unit tests.**

```bash
pytest ergon_core/tests/unit/api/test_worker_contract.py -v
pytest ergon_builtins/tests/ -v
```

Expected: pass. If `ergon_builtins/.../react_worker.py` had its own `from_buffer` method with the same shape, audit confirms there's no test asserting on it; safe to leave.

- [ ] **Step 5.1.4: Commit.**

```bash
git add ergon_core/ergon_core/api/worker/worker.py
git commit -m "v2 phase 5.1: delete Worker.from_buffer (zero callers per audit)"
```

**DoD for 5.1:** `rg "Worker\.from_buffer|from_buffer" ergon_core/ergon_core/api/` returns zero matches.

### Sub-commit 5.2 — Delete `saved_specs` package and ORM

**Files:**
- Delete: `ergon_core/ergon_core/core/persistence/saved_specs/` (entire directory)

- [ ] **Step 5.2.1: Verify zero callers.**

```bash
rg -l "saved_specs|SavedBenchmarkSpec|SavedWorkerSpec|SavedEvaluatorSpec|SavedExperimentTemplate" \
   ergon_core/ ergon_builtins/ ergon_cli/
```

Per audit, no production code imports these. Architecture-guard tests will reference them in their `forbidden` lists; that's fine.

- [ ] **Step 5.2.2: Delete the directory.**

```bash
git rm -r ergon_core/ergon_core/core/persistence/saved_specs/
```

(Phase 1's initial migration already omits the four `saved_*` tables. No follow-up migration needed.)

- [ ] **Step 5.2.3: Run import smoke + tests.**

```bash
python -c "from ergon_core.core.persistence import definitions, telemetry, graph"
pytest ergon_core/tests/unit/persistence/ -v
```

Expected: imports succeed; tests pass.

- [ ] **Step 5.2.4: Commit.**

```bash
git add ergon_core/
git commit -m "v2 phase 5.2: delete saved_specs package (Δ.7)"
```

**DoD for 5.2:** `saved_specs` directory does not exist; production code grep is clean.

### Sub-commit 5.3 — Delete `terminate_sandbox_by_id` stub and `GraphNodeLookup`

**Files:**
- Modify: `ergon_core/ergon_core/core/infrastructure/sandbox/lifecycle.py`
- Delete: `ergon_core/ergon_core/core/application/graph/lookup.py`

- [ ] **Step 5.3.1: Delete the `terminate_sandbox_by_id` no-op stub.**

Audit confirmed it's at `lifecycle.py:75–88` and always reports "not terminated". It was called from `propagate_execution.py`, `check_evaluators.py`, `run_cleanup.py` in v1. After phase 3, callers are: only `run_cleanup.py`. Replace `run_cleanup.py`'s call with a direct sandbox-runtime termination via `lifecycle_hub`:

In `run_cleanup.py`, replace the `terminate_sandbox_by_id` call with:

```python
# Best-effort sandbox sweep using the cached lifecycle hub.
# In practice worker_execute already released; this is a backstop.
await lifecycle_hub.terminate_all_for_run(payload.run_id)
```

Implement `terminate_all_for_run` on `SandboxLifecycleHub` (small addition):

```python
async def terminate_all_for_run(self, run_id: UUID) -> None:
    """Best-effort: terminate any sandboxes still cached for this run."""
    keys = [k for k in self._cache if k[0] == run_id]
    for key in keys:
        sandbox = self._cache.pop(key, None)
        if sandbox is not None:
            with contextlib.suppress(Exception):
                await sandbox.terminate()
```

Then delete the `terminate_sandbox_by_id` function.

- [ ] **Step 5.3.2: Delete `GraphNodeLookup`.**

Audit located `graph/lookup.py` as a `definition_task_id → node_id` map. Post-phase-2, run-tier graph is keyed by `task_id` directly; this lookup is dead.

```bash
git rm ergon_core/ergon_core/core/application/graph/lookup.py
```

Update `graph/__init__.py` to drop the `GraphNodeLookup` export.

- [ ] **Step 5.3.3: Delete `test_definition_lookup_boundaries.py`.**

```bash
git rm ergon_core/tests/unit/runtime/test_definition_lookup_boundaries.py
```

- [ ] **Step 5.3.4: Run.**

```bash
pytest ergon_core/tests/unit/runtime/ ergon_core/tests/unit/architecture/ -v 2>&1 | tail
```

Expected: pass.

- [ ] **Step 5.3.5: Commit.**

```bash
git add ergon_core/ergon_core/
git commit -m "v2 phase 5.3: delete terminate_sandbox_by_id stub and GraphNodeLookup"
```

**DoD for 5.3:** `terminate_sandbox_by_id` and `GraphNodeLookup` symbols do not exist; all callsites updated.

### Sub-commit 5.4 — Rewrite `experiments/launch.py` to be the canonical `launch_run`

**Files:**
- Modify: `ergon_core/ergon_core/core/application/experiments/launch.py`
- Modify: `ergon_core/ergon_core/core/application/experiments/service.py`

Per audit, `launch.py:40–41` references `_persist_single_sample_workflow_definition` as a default factory but the function isn't defined anywhere. v1's CLI worked around this by injecting a factory; v2 deletes the indirection.

- [ ] **Step 5.4.1: Rewrite `launch.py`.**

```python
"""launch_run: takes a definition_id, creates a Run row, and fires workflow/started."""

async def launch_run(
    definition_id: UUID,
    *,
    metadata: dict[str, Any] | None = None,
) -> RunHandle:
    """Create a fresh run from an existing experiment definition. Single
    entry point for run launches; called from CLI and from REST."""
    metadata = metadata or {}
    with session_factory() as session:
        # Verify definition exists:
        definition = session.get(ExperimentDefinition, definition_id)
        if definition is None:
            raise DefinitionNotFoundError(definition_id)

        # Create the Run row (status PENDING):
        run = RunRecord(
            run_id=uuid4(),
            experiment_definition_id=definition_id,
            status=RunStatus.PENDING,
            metadata_json=metadata,
        )
        session.add(run)
        session.commit()
        run_id = run.run_id

    # Fire workflow/started; prepare_run_fn picks it up:
    await inngest_client.send(
        inngest.Event(
            name=WORKFLOW_STARTED,
            data=WorkflowStartedPayload(
                run_id=run_id, definition_id=definition_id, metadata=metadata,
            ).model_dump(mode="json"),
        )
    )

    return RunHandle(run_id=run_id, definition_id=definition_id)
```

Delete `WorkflowDefinitionFactory`, `_persist_single_sample_workflow_definition` references, and the slug-based experiment-record creation path. Those died with phase 1.

- [ ] **Step 5.4.2: Strip `ExperimentService` of legacy methods.**

In `experiments/service.py`:
- Delete `define_benchmark_experiment` (slug → experiment record path; no longer used).
- Delete `run_experiment` (slug-based launch; replaced by `launch_run`).
- Keep `persist_definition(experiment: Experiment) -> DefinitionHandle` as the single authoring entry point.

- [ ] **Step 5.4.3: Update tests.**

`test_experiment_launch_service.py`: rewrite to assert `launch_run` body (no factory injection). `test_experiment_definition_service.py`: replace `define_benchmark_experiment` calls with `persist_definition` calls.

- [ ] **Step 5.4.4: Commit.**

```bash
git add ergon_core/ergon_core/core/application/experiments/ \
        ergon_core/tests/unit/runtime/test_experiment_launch_service.py \
        ergon_core/tests/unit/runtime/test_experiment_definition_service.py
git commit -m "v2 phase 5.4: launch_run + persist_definition as single entry points"
```

**DoD for 5.4:** `launch_run` and `persist_definition` are the single launch/define entry points; `_persist_single_sample_workflow_definition`, `WorkflowDefinitionFactory`, and `define_benchmark_experiment` symbols don't exist.

### Sub-commit 5.5 — CLI rewrite per [05-cli-authoring-interface.md](05-cli-authoring-interface.md)

**Files:**
- Modify: `ergon_cli/ergon_cli/commands/experiment.py`
- Modify: `ergon_cli/tests/test_experiment_cli.py`

- [ ] **Step 5.5.1: Rewrite `ergon experiment define`.**

```python
def define(
    slug: str = typer.Argument(...),
    name: str = typer.Option(..., "--name", "-n"),
    description: str = typer.Option("", "--description", "-d"),
    metadata: list[str] = typer.Option([], "--metadata", "-m"),
) -> None:
    """ergon experiment define <slug>: persist a new experiment definition."""
    factory = BUILTIN_BENCHMARKS.get(slug)
    if factory is None:
        typer.echo(f"unknown benchmark slug: {slug}", err=True)
        raise typer.Exit(1)

    benchmark = factory()
    metadata_dict = dict(_parse_kv(item) for item in metadata)
    experiment = Experiment(
        benchmark=benchmark,
        name=name,
        description=description or None,
        metadata=metadata_dict,
    )
    handle = persist_definition(experiment)
    typer.echo(str(handle.definition_id))
```

- [ ] **Step 5.5.2: Rewrite `ergon experiment run`.**

```python
def run(
    definition_id: UUID = typer.Argument(...),
    metadata: list[str] = typer.Option([], "--metadata", "-m"),
) -> None:
    """ergon experiment run <definition-id>: launch a new run from an existing definition."""
    metadata_dict = dict(_parse_kv(item) for item in metadata)
    handle = asyncio.run(launch_run(definition_id, metadata=metadata_dict))
    typer.echo(f"launched run {handle.run_id} (definition {definition_id})")
```

Per [05](05-cli-authoring-interface.md), there is no `ergon experiment run <slug>` shortcut; users compose: `defn=$(ergon experiment define <slug> --name foo) && ergon experiment run "$defn"`.

- [ ] **Step 5.5.3: Update `test_experiment_cli.py`.**

```python
def test_define_calls_persist_definition(monkeypatch):
    captured = {}
    def fake_persist(experiment):
        captured["experiment"] = experiment
        return DefinitionHandle(definition_id=uuid4())
    monkeypatch.setattr("ergon_cli.commands.experiment.persist_definition", fake_persist)

    result = runner.invoke(app, ["experiment", "define", "test-bench", "--name", "x"])
    assert result.exit_code == 0
    assert captured["experiment"].name == "x"
    assert captured["experiment"].benchmark.type_slug == "test-bench"


def test_run_calls_launch_run(monkeypatch):
    captured = {}
    async def fake_launch(definition_id, *, metadata):
        captured["definition_id"] = definition_id
        return RunHandle(run_id=uuid4(), definition_id=definition_id)
    monkeypatch.setattr("ergon_cli.commands.experiment.launch_run", fake_launch)

    result = runner.invoke(app, ["experiment", "run", str(uuid4())])
    assert result.exit_code == 0


def test_no_run_slug_shortcut():
    """ergon experiment run does not accept a slug; only a definition UUID."""
    result = runner.invoke(app, ["experiment", "run", "test-bench"])
    assert result.exit_code != 0  # UUID parsing fails
```

- [ ] **Step 5.5.4: Commit.**

```bash
git add ergon_cli/
git commit -m "v2 phase 5.5: ergon experiment define/run call persist_definition/launch_run directly"
```

**DoD for 5.5:** `ergon experiment define <slug>` and `ergon experiment run <uuid>` work end-to-end against the v2 schema. CLI tests pass.

### Sub-commit 5.6 — Symbol-deletion architecture guard

**Files:**
- Create: `ergon_core/tests/unit/architecture/test_no_deleted_symbols.py`

- [ ] **Step 5.6.1: Write the per-symbol guard.**

```python
"""Architecture guard: phase 5 deleted symbols stay deleted."""

from pathlib import Path

DELETED_SYMBOLS = [
    "Worker.from_buffer",
    "saved_specs",
    "SavedBenchmarkSpec", "SavedWorkerSpec", "SavedEvaluatorSpec", "SavedExperimentTemplate",
    "terminate_sandbox_by_id",
    "GraphNodeLookup",
    "_persist_single_sample_workflow_definition",
    "WorkflowDefinitionFactory",
    "define_benchmark_experiment",
    "CriterionExecutor",
    "InngestCriterionExecutor",
    "EvaluateTaskRunRequest",
    "evaluate_task_run_fn",
    "execute_task_fn",
    "fail_workflow_fn",
    "check_and_run_evaluators",
    "cancel_orphans_on_cancelled_fn",
    "block_descendants_on_failed_fn",
    "_prepare_definition",
    "task_payload_for_execution",
    "materialize_dynamic_subtask_definition",
]

PRODUCTION_ROOTS = [
    Path("ergon_core/ergon_core"),
    Path("ergon_builtins/ergon_builtins"),
    Path("ergon_cli/ergon_cli"),
]


def test_no_deleted_symbols_in_production_code():
    violations: list[str] = []
    for root in PRODUCTION_ROOTS:
        for py_file in root.rglob("*.py"):
            text = py_file.read_text()
            for symbol in DELETED_SYMBOLS:
                if symbol in text:
                    violations.append(f"{py_file}: contains deleted symbol '{symbol}'")
    assert not violations, "Deleted symbols re-introduced:\n" + "\n".join(violations)
```

- [ ] **Step 5.6.2: Run.**

```bash
pytest ergon_core/tests/unit/architecture/test_no_deleted_symbols.py -v
```

Expected: PASS. If anything fails, the message names the symbol + file; iterate.

- [ ] **Step 5.6.3: Commit.**

```bash
git add ergon_core/tests/unit/architecture/test_no_deleted_symbols.py
git commit -m "v2 phase 5.6: architecture guard for symbol deletions"
```

**DoD for phase 5 overall:**

- All deleted symbols stay deleted (guard enforces).
- CLI works end-to-end against v2 schema.
- `pytest ergon_core/tests/ ergon_cli/tests/ ergon_builtins/tests/ -v` all pass.

---

## Phase 6 — Test consolidation and walkthrough integration

**Goal.** Consolidate all phase 1–5 tests into a coherent suite, add the walkthrough integration test with four variants, configure CI.

**Files this phase touches:**

1. `ergon_core/tests/unit/architecture/` — consolidate guards
2. `ergon_core/tests/unit/regression/` — new directory for the 8 audit findings
3. `tests/integration/test_walkthrough.py` — new walkthrough test
4. CI configuration (`.github/workflows/ci.yml` or equivalent)

### Sub-commit 6.1 — Move scattered architecture guards under one directory

**Files:**
- Move/consolidate files in `ergon_core/tests/unit/architecture/`

- [ ] **Step 6.1.1: Inventory.**

```bash
ls ergon_core/tests/unit/architecture/
```

Expected: 10 v1 guards (per audit) + the 5 new ones from phases 1–5 (`test_v2_schema.py`, `test_runtime_read_boundary.py`, `test_inngest_v2_shape.py`, `test_dynamic_subtask_graph_native.py`, `test_no_deleted_symbols.py`).

- [ ] **Step 6.1.2: Sweep v1 guards for stale assertions.**

Open each of the 10 v1 guards. For any that asserts on retired surfaces (e.g. forbidding `definition_task_id` *only*; we want broader v2 forbidden lists), update the constants. Specifically:

- `test_public_api_target_structure.py`: extend the persistence forbidden-string list with `experiment_records`, `saved_specs`, `criterion_outcomes` *(positive)*.
- `test_core_schema_sources.py`: replace `define_benchmark_experiment` in the asserted `ExperimentService` surface with `persist_definition`, `launch_run`.

- [ ] **Step 6.1.3: Run the full suite.**

```bash
pytest ergon_core/tests/unit/architecture/ -v
```

Expected: 15 test files, all green.

- [ ] **Step 6.1.4: Commit.**

```bash
git add ergon_core/tests/unit/architecture/
git commit -m "v2 phase 6.1: consolidate architecture guards"
```

**DoD for 6.1:** All architecture guards pass; v1 guards updated for v2 surface.

### Sub-commit 6.2 — Regression net for the 8 load-bearing audit findings

**Files:**
- Create: `ergon_core/tests/unit/regression/__init__.py`
- Create: `ergon_core/tests/unit/regression/test_v1_audit_findings.py`

- [ ] **Step 6.2.1: Write one test per finding.**

```python
"""Regression tests for the 8 load-bearing v1 audit findings.

Each test asserts that the bug class identified in
docs/rfcs/active/2026-05-08-authoring-api-redesign/08-cleanup-audit.md
cannot reappear without a test failure.
"""

# Finding 1: ExperimentRecord telemetry separate from ExperimentDefinition
def test_experiment_record_table_does_not_exist():
    """Δ.1 lock: ExperimentRecord collapsed into ExperimentDefinition."""
    from ergon_core.core.persistence.shared.db import metadata
    assert "experiments" not in metadata.tables


# Finding 2: Cross-tier read leak (definition reads after run starts)
def test_runtime_does_not_read_definition_tables():
    """Δ.2 lock: runtime reads exclusively from run-tier tables."""
    # Re-runs the architecture guard from phase 2.4.
    from ergon_core.tests.unit.architecture.test_runtime_read_boundary import (
        test_runtime_does_not_read_definition_tables as _impl,
    )
    _impl()


# Finding 3: Dynamic subtask synthetic definition row
def test_dynamic_subtask_has_no_definition_row():
    """Δ.3 lock: spawned tasks live only in run_graph_nodes."""
    # Integration-style: spawn a task, assert no experiment_definition_tasks row.
    run_id, parent_task_id = _setup_run_with_one_task()
    asyncio.run(_spawn_subtask(run_id, parent_task_id, _make_test_task()))

    with session_factory() as session:
        defn_tasks = session.exec(
            select(ExperimentDefinitionTask).where(...)
        ).all()
        assert len(defn_tasks) == 1, "only the original definition task; no synthetic row for spawned task"
        graph_nodes = session.exec(
            select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        ).all()
        assert len(graph_nodes) == 2, "static + dynamic both in graph"
        dynamic = next(n for n in graph_nodes if n.is_dynamic)
        assert dynamic.parent_task_id == parent_task_id


# Finding 4: Sandbox not released on happy path
def test_sandbox_released_on_worker_execute_happy_path():
    """Δ.4 lock: worker_execute releases sandbox in finally."""
    # Mock-based; verifies lifecycle_hub.release is called.
    ...


# Finding 5: Sandbox leaked when criteria run in separate Inngest function
def test_sandbox_released_after_inline_criteria():
    """Δ.5 lock: criteria run inline; sandbox release waits for them."""
    ...


# Finding 6: Forked Alembic chain + ORM/migration drift
def test_alembic_history_is_linear_with_one_head():
    """Δ.6 lock: schema reset produced one head."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config("ergon_core/alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"expected one head, got {heads}"
    assert heads[0] == "00000000"


# Finding 7: Dead saved_specs package + Worker.from_buffer + CriterionExecutor
def test_no_deleted_symbols_redux():
    """Δ.7 lock: deleted symbols stay deleted."""
    # Re-runs the architecture guard from phase 5.6.
    from ergon_core.tests.unit.architecture.test_no_deleted_symbols import (
        test_no_deleted_symbols_in_production_code as _impl,
    )
    _impl()


# Finding 8: CLI's broken define path (missing _persist_single_sample_workflow_definition)
def test_cli_define_routes_through_persist_definition():
    """Δ.8 lock: CLI calls persist_definition directly."""
    src = Path("ergon_cli/ergon_cli/commands/experiment.py").read_text()
    assert "persist_definition" in src
    assert "_persist_single_sample_workflow_definition" not in src
    assert "define_benchmark_experiment" not in src
```

- [ ] **Step 6.2.2: Run.**

```bash
pytest ergon_core/tests/unit/regression/test_v1_audit_findings.py -v
```

Expected: 8 PASSED.

- [ ] **Step 6.2.3: Commit.**

```bash
git add ergon_core/tests/unit/regression/
git commit -m "v2 phase 6.2: regression net for 8 v1 audit findings"
```

**DoD for 6.2:** 8 regression tests pass; each maps to a Δ.* lock.

### Sub-commit 6.3 — Walkthrough integration test (4 variants)

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_walkthrough.py`
- Create: `tests/integration/conftest.py` (Postgres test container fixture)

- [ ] **Step 6.3.1: Postgres test container fixture.**

```python
# tests/integration/conftest.py
import pytest
import testcontainers.postgres

@pytest.fixture(scope="session")
def postgres_url():
    with testcontainers.postgres.PostgresContainer("postgres:15") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session", autouse=True)
def schema(postgres_url):
    """Run alembic upgrade head against the container DB at session start."""
    from alembic.config import Config
    from alembic import command
    cfg = Config("ergon_core/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(cfg, "head")
    yield
```

- [ ] **Step 6.3.2: Walkthrough scenario builder.**

Per [04-walkthrough.md](04-walkthrough.md), the canonical scenario is: 1 cohort × 1 benchmark × 4 tasks × 1 criterion × 1 sandbox. Build a fixture:

```python
@pytest.fixture
def walkthrough_experiment():
    """The canonical 1-benchmark/4-tasks/1-criterion fixture from 04-walkthrough.md."""
    benchmark = _SimpleTestBenchmark()  # 4 tasks: T1, T2, T3, T4 with deps T1→T2→T3→T4 sequential
    return Experiment(
        benchmark=benchmark,
        name="walkthrough-test",
        description="Canonical v2 walkthrough scenario",
        metadata={},
    )
```

- [ ] **Step 6.3.3: Variant 1 — happy path.**

```python
@pytest.mark.asyncio
async def test_walkthrough_happy_path(walkthrough_experiment):
    handle = persist_definition(walkthrough_experiment)
    run_handle = await launch_run(handle.definition_id)
    await _drain_inngest(run_handle.run_id, expected_terminal=True)

    with session_factory() as session:
        run = session.get(RunRecord, run_handle.run_id)
        assert run.status == RunStatus.SUCCEEDED
        nodes = session.exec(
            select(RunGraphNode).where(RunGraphNode.run_id == run_handle.run_id)
        ).all()
        assert len(nodes) == 4
        assert all(n.status == "succeeded" for n in nodes)
        outcomes = session.exec(
            select(CriterionOutcomeRecord).where(CriterionOutcomeRecord.run_id == run_handle.run_id)
        ).all()
        assert len(outcomes) == 4  # one criterion per task
        assert all(o.passed for o in outcomes)
```

- [ ] **Step 6.3.4: Variant 2 — failure cascade (four-axis lock).**

```python
@pytest.mark.asyncio
async def test_walkthrough_failure_cascade(walkthrough_failing_experiment):
    """T2 fails. T1: succeeded. T2: failed. T3: stays PENDING (depends on T2). T4: stays PENDING."""
    handle = persist_definition(walkthrough_failing_experiment)
    run_handle = await launch_run(handle.definition_id)
    await _drain_inngest(run_handle.run_id, expected_terminal=True)

    with session_factory() as session:
        run = session.get(RunRecord, run_handle.run_id)
        assert run.status == RunStatus.FAILED, "any task failed → run failed"

        nodes = {n.task_id: n for n in session.exec(
            select(RunGraphNode).where(RunGraphNode.run_id == run_handle.run_id)
        ).all()}
        # Map back to slugs:
        by_slug = {Task.from_definition(n.task_json, task_id=tid).task_slug: n
                   for tid, n in nodes.items()}
        assert by_slug["T1"].status == "succeeded"
        assert by_slug["T2"].status == "failed"
        assert by_slug["T3"].status == "pending", "T3 depends on T2; stays PENDING (Axis 4)"
        assert by_slug["T4"].status == "pending"
```

- [ ] **Step 6.3.5: Variant 3 — dynamic spawn.**

```python
@pytest.mark.asyncio
async def test_walkthrough_dynamic_spawn(walkthrough_dynamic_experiment):
    """T1 spawns a child during execute(). Verify it lands in run_graph_nodes with is_dynamic=True."""
    ...
```

- [ ] **Step 6.3.6: Variant 4 — restart.**

```python
@pytest.mark.asyncio
async def test_walkthrough_restart_after_failure(walkthrough_experiment):
    """Restart a failed run; existing PENDING tasks pick up where left off."""
    ...
```

- [ ] **Step 6.3.7: Run all variants.**

```bash
pytest tests/integration/test_walkthrough.py -v
```

Expected: 4 PASSED. Wall time ~2 min including Postgres container spinup.

- [ ] **Step 6.3.8: Commit.**

```bash
git add tests/integration/
git commit -m "v2 phase 6.3: walkthrough integration test (4 variants)"
```

**DoD for 6.3:** 4 walkthrough variants pass against Postgres test container.

### Sub-commit 6.4 — CI configuration

**Files:**
- Modify: `.github/workflows/ci.yml` (or equivalent)

- [ ] **Step 6.4.1: Add v2 jobs.**

```yaml
# .github/workflows/ci.yml
jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ergon_core -e ergon_builtins -e ergon_cli
      - run: pip install pytest pytest-asyncio
      - run: pytest ergon_core/tests/unit/ ergon_builtins/tests/ ergon_cli/tests/ -v

  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: ergon
          POSTGRES_PASSWORD: ergon
          POSTGRES_DB: ergon_test
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ergon_core -e ergon_builtins -e ergon_cli
      - run: pip install pytest pytest-asyncio testcontainers
      - run: alembic -c ergon_core/alembic.ini upgrade head
        env:
          DATABASE_URL: postgresql://ergon:ergon@localhost/ergon_test
      - run: pytest tests/integration/ -v
```

- [ ] **Step 6.4.2: Verify locally first.**

Push to a feature branch, watch CI. Expected: both `unit` and `integration` jobs green.

- [ ] **Step 6.4.3: Commit.**

```bash
git add .github/workflows/
git commit -m "v2 phase 6.4: CI runs unit + walkthrough integration on every push"
```

**DoD for phase 6 overall:**

- 15+ architecture guards in one directory.
- 8 regression tests in `unit/regression/`.
- 4 walkthrough integration tests pass against Postgres container.
- CI green on the v2 branch.
- Total CI wall time ≤ 5 min.

---

## Risks (per phase, sharpened)

| Phase | Risk | Mitigation |
|---|---|---|
| 1 | Schema reset loses dev data | No prod data exists; the PR description includes "drop your local DB before pulling". `make reset-dev-db` target ships in the PR for convenience. |
| 1 | ORM ↔ migration drift recurs | Phase 1.6's schema introspection guards catch column-shape drift on every test run. |
| 2 | A definition-read sneaks back in via a forgotten path | `test_runtime_does_not_read_definition_tables` AST-style scan catches reintroduction of any `ExperimentDefinitionTask` reference outside the allowlist. |
| 2 | `populate_from_definition` gets too large | If it crosses ~150 lines, factor into `_populate_nodes` + `_populate_edges` helpers in the same file. |
| 3 | Inline criteria slow down task throughput | Criteria are O(1) per the audit; but if a future benchmark adds expensive criteria, the option remains to dispatch them as separate Inngest steps within `worker_execute_fn` (i.e. `step.run("criterion_X", criterion_X.evaluate)`) without changing the function topology. |
| 3 | Four-axis failure semantics regress | 4 dedicated tests + walkthrough variant 2 + the architecture guard exercise the spec. Any bug shows up immediately. |
| 3 | `is_run_terminal` undercounts (run never finishes) or overcounts (run finishes too early) | Walkthrough variants exercise both happy and failure-cascade terminal cases. Add a "two independent subtrees, one fails" variant if real workloads surface a regression. |
| 4 | `is_dynamic = TRUE` accidentally set on static tasks (or vice versa) | Architecture guard `test_populate_from_definition_sets_is_dynamic_false` + `test_spawn_task_path_sets_is_dynamic` enforce both directions. |
| 5 | Deletion of `Worker.from_buffer` breaks an external caller we didn't find | Audit confirmed zero callers; if a downstream package has its own callsite, the import error surfaces immediately on its first import attempt. |
| 5 | CLI rewrite breaks integration with downstream tooling that scrapes `ergon experiment define` output | The new output is `<UUID>` (just the definition_id). Old output had more text. The change is documented in the PR description. |
| 6 | Postgres test container spinup is flaky in CI | `testcontainers` library with retry; if persistent, swap for a `services: postgres` declaration (already shown in 6.4.1). |
| All | Single-PR review fatigue | Phase boundaries make commit-by-commit review tractable. ~2,900 lines is at the edge of "single PR is reasonable" but well below the v1 PR's ~12,000. |

## PR-level definition of done

The branch is mergeable when:

- [ ] All 6 phases' DoD entries are checked.
- [ ] `pytest ergon_core/tests/ ergon_builtins/tests/ ergon_cli/tests/ -v` passes (entire unit suite, all 60+ files).
- [ ] `pytest tests/integration/test_walkthrough.py -v` passes for all 4 variants.
- [ ] `alembic -c ergon_core/alembic.ini upgrade head` succeeds on a fresh DB; `alembic history` shows one linear chain with one head (`00000000`).
- [ ] `rg "ExperimentRecord|saved_specs|definition_task_id|terminate_sandbox_by_id|_persist_single_sample_workflow_definition|CriterionExecutor|InngestCriterionExecutor|EvaluateTaskRunRequest|Worker.from_buffer|GraphNodeLookup|task_payload_for_execution|materialize_dynamic_subtask_definition|define_benchmark_experiment" ergon_core/ergon_core/ ergon_builtins/ergon_builtins/ ergon_cli/ergon_cli/` returns zero matches.
- [ ] CI green on the v2 branch.
- [ ] charlie has reviewed the cumulative diff.

## Decisions locked at workshop `[v2: locked]`

- **Single PR vs. multiple PRs** — **locked: single PR.** charlie reviews everything; phase commits make commit-by-commit review tractable. No multi-PR ladder.
- **Reviewer assignment** — **locked: charlie reviews all phases.**
- **Production data confirmation** — **locked: no prod data.** Local tool only; dev databases are the only thing the schema reset touches.
- **Postgres test container vs. SQLite** — **locked: SQLite for unit-level (architecture guards, regression net), Postgres test container for walkthrough integration only.** Most tests use SQLite for speed; the integration test uses Postgres for honesty with prod schema.
- **Test consolidation timing** — **locked: phase 6 last.** Tests are added piecemeal in earlier phases (architecture guards land with the changes that need them); phase 6 consolidates the suite shape.
- **Half-state mid-phase** — **locked: accepted.** The branch may be non-runnable between sub-commits within a phase; only the cumulative PR is guaranteed green at merge. This was the principled response to phase 1's "schema lands but runtime hasn't caught up" half-state.
- **`is_dynamic` default** — **locked: NOT NULL DEFAULT FALSE.** Phase 1 sets the default; phase 4 sets TRUE for spawn paths only.
- **`saved_specs` migration ordering** — **locked: phase-1 schema simply omits the four `saved_*` tables.** Phase 5's deletion is code-only.
- **`run_cleanup` after worker_execute owns release** — **locked: keep as best-effort backstop.** Sandboxes that escape `worker_execute`'s `try/finally` (Inngest crash mid-execution; pid kill; etc.) get swept by `run_cleanup_fn` consuming `run/cleanup`.
- **Sub-commit granularity** — **locked: 3–7 sub-commits per phase**, each with files + steps + DoD.

---

> **End of phase plan. Total estimated diff: ~2,900 lines. Reviewable in one PR with phase-named commits.**
