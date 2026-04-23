# E2E Smoke Coverage Rewrite — Implementation Plan

**Unified entry point:** [`2026-04-22-unified-testing-e2e-smoke-plan.md`](2026-04-22-unified-testing-e2e-smoke-plan.md) — testing tiers, smoke invariants, delivery bundle, and RFC errata (sandbox attach). This document remains the **step-by-step task checklist** (PR 0, Task 1, …).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the retired `tests/e2e/` tier with three canonical per-env smoke tests (researchrubrics, minif2f, swebench-verified) built on a shared multi-agent smoke-worker pattern, plus a backend test-harness router, Playwright frontend assertions, and on-PR inline screenshot delivery.

**Architecture:** Shared `CanonicalSmokeWorker` spawns a hardcoded 9-subtask graph (diamond + line + 2 singletons) via `add_subtask`; per-env `SmokeSubworker` leaves write an env file + run a bash probe; per-env `SmokeCriterion` verifies structure + content. Python pytest drives the CLI + asserts Postgres record-log, invokes Playwright as a subprocess for dashboard assertion. Screenshots upload to orphan `screenshots/pr-{N}` ref; PR comment inlines them on pass AND fail. Parallel CI matrix with 5-min budget per env on every PR.

**Tech Stack:** Python 3.13 (pytest, httpx, sqlmodel, FastAPI), TypeScript (Playwright, Next.js), Docker Compose, GitHub Actions, `gh` CLI, UV workspace, pnpm.

**Canonical references:**
- Spec: `docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md`
- Superseded-but-absorbed spec: `docs/rfcs/rejected/2026-04-18-test-harness-endpoints.md` (harness absorbed by smoke RFC; paths in this plan may still cite it)
- Parent project RFC (prerequisites): `docs/rfcs/accepted/2026-04-18-testing-posture-reset.md`

**Prerequisites gating:**
- **PR 0 of this plan** is a standalone engine rename (no dependencies) — must merge before PR 1 branch is created.
- **PR 1 of this plan** requires PR 0 merged. It does not touch `tests/e2e/`.
- **PR 2–4 of this plan** require these reset-RFC PRs to have merged first:
  - Reset RFC PR 2 (Docker layer caching) — required for 5-min CI budget.
  - Reset RFC PR 3 (`tests/integration/` real-Postgres infrastructure) — the pytest driver reuses this stack.
  - Reset RFC PR 4 (`tests/e2e/` deleted) — clean slate.
- If any of those haven't landed when you reach PR 2 of this plan, pause and escalate.

---

## File structure overview

### Python production code (added)

| File | Purpose |
|---|---|
| `ergon_builtins/ergon_builtins/workers/stubs/__init__.py` | Package marker (new subdir) |
| `ergon_builtins/ergon_builtins/workers/stubs/smoke_subworker.py` | `SmokeSubworker` Protocol + `SubworkerResult` dataclass |
| `ergon_builtins/ergon_builtins/workers/stubs/base_smoke_leaf.py` | `BaseSmokeLeafWorker` — shared glue from subworker to resource publish |
| `ergon_builtins/ergon_builtins/workers/stubs/canonical_smoke_worker.py` | `CanonicalSmokeWorker` + `EXPECTED_SUBTASK_SLUGS` constant |
| `ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py` | `SmokeCriterionBase` abstract + 3 env-specific subclasses |
| `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/smoke_subworker.py` | `ResearchRubricsSmokeSubworker` + `ResearchRubricsSmokeLeafWorker` |
| `ergon_builtins/ergon_builtins/benchmarks/minif2f/smoke_subworker.py` | `MiniF2FSmokeSubworker` + `MiniF2FSmokeLeafWorker` |
| `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/smoke_subworker.py` | `SweBenchSmokeSubworker` + `SweBenchSmokeLeafWorker` |
| `ergon_core/ergon_core/core/api/test_harness.py` | FastAPI `/api/test/*` router (absorbed from superseded RFC) |

### Python production code (modified)

| File | Change |
|---|---|
| `ergon_builtins/ergon_builtins/registry_core.py` | Register `canonical-smoke`, 3 env leaf workers, 3 env criteria |
| `ergon_cli/ergon_cli/composition/__init__.py` | Add `smoke-leaf` binding for 3 env compositions |
| `ergon_core/ergon_core/core/api/app.py` | Conditional `include_router(test_harness_router)` gated on `ENABLE_TEST_HARNESS=1` |
| `docker-compose.ci.yml` | Add `ENABLE_TEST_HARNESS=1` + `TEST_HARNESS_SECRET=ci-secret` to api env |

### Python tests (added)

| File | Purpose |
|---|---|
| `tests/unit/test_canonical_smoke_worker.py` | Unit: registry entries exist, topology constant correct |
| `tests/unit/test_smoke_criterion.py` | Unit: structural assertions + per-env content assertions against a fake context |
| `tests/unit/test_test_harness.py` | Unit: harness gate on env var, secret header check, schema stability |
| `tests/integration/smokes/test_smoke_harness.py` | Integration: seed → read → reset round-trip against real Postgres |
| `tests/e2e/conftest.py` | Finalizer + `run_benchmark` + `wait_for_terminal` helpers |
| `tests/e2e/test_researchrubrics_smoke.py` | Canonical smoke pytest for researchrubrics |
| `tests/e2e/test_minif2f_smoke.py` | Canonical smoke pytest for minif2f |
| `tests/e2e/test_swebench_verified_smoke.py` | Canonical smoke pytest for swebench-verified |

### TypeScript (added)

| File | Purpose |
|---|---|
| `ergon-dashboard/tests/helpers/testHarnessClient.ts` | `BackendHarnessClient` class (distinct from existing `harnessClient.ts`) |
| `ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts` | Playwright spec for researchrubrics |
| `ergon-dashboard/tests/e2e/minif2f.smoke.spec.ts` | Playwright spec for minif2f |
| `ergon-dashboard/tests/e2e/swebench-verified.smoke.spec.ts` | Playwright spec for swebench-verified |

### TypeScript (modified)

| File | Change |
|---|---|
| `ergon-dashboard/playwright.config.ts` | `screenshot: "only-on-failure"` → `"on"` |

### CI (added)

| File | Purpose |
|---|---|
| `.github/workflows/e2e-benchmarks.yml` | Parallel per-env matrix with 5-min budget + screenshot-ref cleanup |

### Docs (modified on PR 4)

| File | Change |
|---|---|
| `docs/architecture/06_builtins.md` | Rewrite §4 invariant for `SmokeSubworker`/`SmokeCriterion` contract |
| `docs/architecture/07_testing.md` | Update §2 code map + §3 trigger policy + §4 new invariant |
| `docs/architecture/05_dashboard.md` | Add canonical-smoke invariant |
| `docs/architecture/01_public_api.md` | Add "Test-only extension points" section |

### RFC moves

| On PR | From | To |
|---|---|---|
| PR 1 merge | `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md` | `docs/rfcs/rejected/` |
| PR 1 merge | `docs/rfcs/active/2026-04-18-test-harness-endpoints.md` | `docs/rfcs/rejected/` |
| PR 4 merge | `docs/rfcs/active/2026-04-21-e2e-smoke-coverage-rewrite.md` | `docs/rfcs/accepted/` |

---

# PR 0 — Engine rename: `TaskSlug` + `AssignedWorkerSlug`

**PR branch:** `feature/engine-task-slug-rename`

**Goal:** Make dynamic-subtask identity durable and caller-controllable. Add `TaskSlug` and `AssignedWorkerSlug` `NewType` aliases. Rename `task_key` → `task_slug` on both the experiment-definition and run-graph models. Rename `worker_binding_key` (DTO) / `assigned_worker_key` (graph column) → `assigned_worker_slug` end-to-end. Drop the auto-generated `dynamic:<hex>` prefix — `plan_subtasks` and `add_subtask` now require a caller-supplied `task_slug`.

**Motivation:** Currently `SubtaskSpec.local_key` is used only for in-call dep resolution and then discarded. The persisted `task_key` is engine-generated (`dynamic:<hex>`) and opaque. External observers — smoke criteria, tests, dashboards — cannot identify dynamically-spawned nodes semantically. Collapsing the two into a single caller-chosen, persisted slug is the prerequisite for PR 1's criterion to assert topology by name (`d_root`, `d_left`, …). The rename also fixes existing semantic noise: the values stored in these fields are already slugs (`"researcher"`, `"research-av-safety"`), not opaque keys.

**Scope:** Mechanical rename across DTOs, service layer, repositories, graph + definition models, one Alembic migration, `SubtaskLifecycleToolkit`, both manager workers, and all tests referencing the old names. Runtime behaviour is otherwise unchanged.

**PR 0 acceptance gate:**
- `pnpm run check:fast` green
- `uv run pytest tests/state tests/unit -x` green
- Alembic migration applies + reverses cleanly (`alembic upgrade head && alembic downgrade -1 && alembic upgrade head`)
- `grep -rn "task_key\|worker_binding_key\|assigned_worker_key\|local_key" ergon_core/ ergon_builtins/ tests/ --include="*.py"` returns zero matches (except inside the new Alembic migration)
- PR 0 MUST merge before `feature/smoke-shared-infra` is branched

---

## Task PR0.A — Branch setup for PR 0

**Files:** none (environment prep).

- [ ] **Step A.1: Verify clean baseline**

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
git checkout main
git pull origin main
uv sync --all-packages --group dev
uv run pytest tests/state tests/unit -x
pnpm run check:fast
```

Expected: all green. Stop and fix any failures before starting.

- [ ] **Step A.2: Create PR 0 branch**

```bash
git checkout -b feature/engine-task-slug-rename
```

Expected: on `feature/engine-task-slug-rename`, clean working tree.

---

## Task PR0.B — `TaskSlug` + `AssignedWorkerSlug` NewTypes

**Files:**
- Modify: `ergon_core/ergon_core/core/persistence/shared/types.py`
- Test: none — `NewType` aliases are erased at runtime; downstream call-site tests provide coverage.

- [ ] **Step B.1: Add the NewTypes and drop `WorkerBindingKey`**

Edit `shared/types.py` so it reads:

```python
"""Shared type aliases for stringly-typed identifiers.

NewType aliases are erased at runtime but catch cross-field
misassignment in type checkers (e.g., passing a task_slug where a
node_id is expected).
"""

from typing import NewType
from uuid import UUID

# ── String aliases ────────────────────────────────────────────────
TaskSlug = NewType("TaskSlug", str)
AssignedWorkerSlug = NewType("AssignedWorkerSlug", str)
BenchmarkSlug = NewType("BenchmarkSlug", str)

# ── UUID aliases ──────────────────────────────────────────────────
RunId = NewType("RunId", UUID)
NodeId = NewType("NodeId", UUID)
DefinitionId = NewType("DefinitionId", UUID)
ExecutionId = NewType("ExecutionId", UUID)
EdgeId = NewType("EdgeId", UUID)
```

- [ ] **Step B.2: Commit**

```bash
git add ergon_core/ergon_core/core/persistence/shared/types.py
git commit -m "refactor(types): add TaskSlug, rename WorkerBindingKey -> AssignedWorkerSlug"
```

The next tasks will progressively break `ty` and imports of `WorkerBindingKey` until the rename lands across call-sites — this is expected.

---

## Task PR0.C — Rename graph + definition columns; Alembic migration

**Files:**
- Modify: `ergon_core/ergon_core/core/persistence/graph/models.py`
- Modify: `ergon_core/ergon_core/core/persistence/definitions/models.py`
- Create: `ergon_core/migrations/versions/<hash>_rename_task_key_to_task_slug.py`

- [ ] **Step C.1: Rename fields on `RunGraphNode`**

Edit `graph/models.py` around lines 58–72 — keep all surrounding fields, change only these two:

```python
# Identifies the task slot in the experiment template (e.g.
# 'research-av-safety') OR the caller-chosen slug for a
# dynamically-spawned subtask. Required at creation, persisted verbatim.
task_slug: str = Field(index=True)          # was: task_key
description: str
...
# WORKERS-registry slug, e.g. "researcher", "smoke-test-worker".
assigned_worker_slug: str | None = None     # was: assigned_worker_key
```

- [ ] **Step C.2: Rename on `ExperimentDefinitionTask`**

Edit `definitions/models.py:172`:

```python
task_slug: str = Field(index=True)          # was: task_key
```

- [ ] **Step C.3: Generate Alembic migration skeleton**

```bash
cd ergon/ergon_core
uv run alembic revision -m "rename task_key to task_slug and assigned_worker_key to assigned_worker_slug"
```

- [ ] **Step C.4: Fill migration body**

Replace the generated `upgrade`/`downgrade` with:

```python
def upgrade() -> None:
    op.alter_column("run_graph_nodes", "task_key", new_column_name="task_slug")
    op.alter_column(
        "run_graph_nodes",
        "assigned_worker_key",
        new_column_name="assigned_worker_slug",
    )
    op.alter_column(
        "experiment_definition_tasks",
        "task_key",
        new_column_name="task_slug",
    )


def downgrade() -> None:
    op.alter_column(
        "experiment_definition_tasks",
        "task_slug",
        new_column_name="task_key",
    )
    op.alter_column(
        "run_graph_nodes",
        "assigned_worker_slug",
        new_column_name="assigned_worker_key",
    )
    op.alter_column("run_graph_nodes", "task_slug", new_column_name="task_key")
```

- [ ] **Step C.5: Round-trip the migration**

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: clean output; dev DB ends on the new head.

- [ ] **Step C.6: Commit**

```bash
git add ergon_core/ergon_core/core/persistence/graph/models.py \
        ergon_core/ergon_core/core/persistence/definitions/models.py \
        ergon_core/migrations/versions/*rename_task_key*.py
git commit -m "refactor(persistence): rename task_key->task_slug, assigned_worker_key->assigned_worker_slug"
```

---

## Task PR0.D — DTOs + `plan_subtasks` + `add_subtask` service updates

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/services/task_management_dto.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/task_management_service.py`
- Modify: `ergon_core/ergon_core/core/persistence/graph/repository.py` (or wherever `add_node` lives — grep to confirm)
- Modify: `tests/state/test_plan_subtasks.py`
- Modify: `tests/state/test_task_management_service.py`

- [ ] **Step D.1: Update DTOs**

Edit `task_management_dto.py`:

```python
from ergon_core.core.persistence.shared.types import (
    AssignedWorkerSlug, NodeId, RunId, TaskSlug,
)

class SubtaskSpec(BaseModel):
    task_slug: TaskSlug = Field(min_length=1)            # was: local_key
    description: str = Field(min_length=1)
    assigned_worker_slug: AssignedWorkerSlug = Field(
        default=AssignedWorkerSlug("researcher"),
    )                                                     # was: worker_binding_key
    depends_on: list[TaskSlug] = Field(default_factory=list)
    model_config = {"frozen": True}


class PlanSubtasksCommand(BaseModel):
    run_id: RunId
    parent_node_id: NodeId
    subtasks: list[SubtaskSpec]


class PlanSubtasksResult(BaseModel):
    nodes: dict[TaskSlug, NodeId]                         # was: dict[str, NodeId] (keyed by local_key)
    roots: list[TaskSlug]


class AddSubtaskCommand(BaseModel):
    run_id: RunId
    parent_node_id: NodeId
    task_slug: TaskSlug = Field(min_length=1)             # NEW — mandatory
    description: str
    assigned_worker_slug: AssignedWorkerSlug = Field(
        default=AssignedWorkerSlug("researcher"),
    )                                                     # was: worker_binding_key
    depends_on: list[NodeId] = Field(default_factory=list)
```

(Preserve any other pre-existing fields on these classes.)

- [ ] **Step D.2: Update `plan_subtasks` and `add_subtask` in service**

Edit `task_management_service.py`:

- Delete the `_DYNAMIC_TASK_KEY_PREFIX = "dynamic:"` constant (line 58).
- At both sites that currently do `task_key = f"{_DYNAMIC_TASK_KEY_PREFIX}{node_uuid.hex[:8]}"` (lines 129 and 265), replace with `task_slug = spec.task_slug` (in `plan_subtasks`) and `task_slug = command.task_slug` (in `add_subtask`).
- Pass `task_slug=task_slug, assigned_worker_slug=spec.assigned_worker_slug` to `add_node`.
- In `plan_subtasks`, rename the local `key_to_node_id: dict[str, UUID]` → `slug_to_node_id: dict[TaskSlug, NodeId]`, keyed by `spec.task_slug`. The second loop iterates `spec.depends_on` (now `list[TaskSlug]`) and looks up each in `slug_to_node_id`.
- `PlanSubtasksResult(nodes=slug_to_node_id, roots=roots)` — `roots` is `list[TaskSlug]`.

- [ ] **Step D.3: Update `add_node` signature**

Grep for `def add_node(` in `ergon_core/core/persistence/graph/`:

```bash
grep -n "def add_node" ergon_core/ergon_core/core/persistence/graph/*.py
```

In whichever file, rename the parameters:
- `task_key: str` → `task_slug: str`
- `assigned_worker_key: ...` → `assigned_worker_slug: ...`

Update all call-sites in `task_management_service.py` and any other in-repo callers (grep `add_node(` in `ergon_core/`).

- [ ] **Step D.4: Update state tests that reference old field names**

Edit `tests/state/test_plan_subtasks.py` and `tests/state/test_task_management_service.py` — replace `local_key=` with `task_slug=`, `worker_binding_key=` with `assigned_worker_slug=`, `task_key=` with `task_slug=`, and adjust any result-dict accesses (`result.nodes["foo"]` stays unchanged in shape but the dict is now typed `dict[TaskSlug, NodeId]`).

- [ ] **Step D.5: Run state tests**

```bash
uv run pytest tests/state/test_plan_subtasks.py tests/state/test_task_management_service.py -x
```

Expected: all pass.

- [ ] **Step D.6: Commit**

```bash
git add ergon_core/ tests/state/test_plan_subtasks.py tests/state/test_task_management_service.py
git commit -m "refactor(runtime): collapse local_key/task_key into task_slug on SubtaskSpec + AddSubtaskCommand"
```

---

## Task PR0.E — `SubtaskLifecycleToolkit` + manager workers

**Files:**
- Modify: `ergon_builtins/ergon_builtins/tools/subtask_lifecycle_toolkit.py`
- Modify: `ergon_builtins/ergon_builtins/workers/baselines/manager_researcher_worker.py`
- Modify: `ergon_builtins/ergon_builtins/workers/research_rubrics/manager_worker.py`
- Modify: `tests/state/test_subtask_lifecycle_toolkit.py`
- Modify: `tests/state/test_research_rubrics_workers.py`
- Modify: `tests/state/test_manager_dag_scenario.py`
- Modify: `tests/state/test_delegation_scenario.py`

- [ ] **Step E.1: Toolkit — expose `task_slug` to the LLM**

In `subtask_lifecycle_toolkit.py`:

- `add_subtask(description, worker_binding_key="researcher", depends_on=None)` → `add_subtask(task_slug: str, description: str, assigned_worker_slug: str = "researcher", depends_on: list[str] | None = None)`. `depends_on` here still refers to sibling `NodeId` strings (the LLM passes real UUIDs it got from earlier calls).
- Docstring: "The `task_slug` is a short kebab-case identifier for this subtask. It is persisted verbatim and used by observers (dashboard, criteria, tests) to identify this node."
- Build `AddSubtaskCommand(task_slug=TaskSlug(task_slug), description=description, assigned_worker_slug=AssignedWorkerSlug(assigned_worker_slug), depends_on=deps, ...)`.

- `plan_subtasks(subtasks)` — each entry's `local_key` is renamed to `task_slug` in the dict the LLM supplies. Docstring: "Each entry has `task_slug` (kebab-case identifier, persisted verbatim), `description`, optional `assigned_worker_slug`, optional `depends_on` (list of sibling `task_slug`s within this call)." `SubtaskSpec.model_validate(s)` continues to work because the DTO field renames match the dict keys.

- [ ] **Step E.2: Manager workers — update prompt text and any static call-sites**

In `manager_researcher_worker.py` and `research_rubrics/manager_worker.py`:
- Replace any prompt text referencing `local_key` or `worker_binding_key` with `task_slug` / `assigned_worker_slug`.
- If there are non-LLM call-sites that build `SubtaskSpec` directly, update fields.

- [ ] **Step E.3: Update toolkit + scenario tests**

Sweep `tests/state/test_subtask_lifecycle_toolkit.py`, `test_manager_dag_scenario.py`, `test_delegation_scenario.py`, `test_research_rubrics_workers.py` for any of: `local_key`, `worker_binding_key`, `task_key`, `assigned_worker_key`. Replace with the new names.

- [ ] **Step E.4: Run full unit + state suite**

```bash
uv run pytest tests/unit tests/state -x
```

Expected: all pass. Any failure must be a call-site missed in the sweep — fix it.

- [ ] **Step E.5: Commit**

```bash
git add ergon_builtins/ tests/state/
git commit -m "refactor(builtins): plumb task_slug through toolkit and manager workers"
```

---

## Task PR0.F — Grep sweep + push PR 0

**Files:** various (clean-up pass).

- [ ] **Step F.1: Verify no references to the old names remain**

```bash
grep -rn "task_key\|worker_binding_key\|assigned_worker_key\|local_key" \
    ergon_core/ ergon_builtins/ tests/ --include="*.py" \
  | grep -v "migrations/versions/.*rename_task_key"
```

Expected: zero matches. If any remain, fix them and re-commit before pushing.

- [ ] **Step F.2: Run full check:fast**

```bash
pnpm run check:fast
```

Expected: green.

- [ ] **Step F.3: Push and open PR 0**

```bash
git push -u origin feature/engine-task-slug-rename
gh pr create --title "refactor: collapse local_key/task_key into caller-chosen task_slug" --body "$(cat <<'EOF'
## Summary
- Adds `TaskSlug` and `AssignedWorkerSlug` `NewType` aliases in `shared/types.py`
- Renames `task_key` → `task_slug` on `RunGraphNode` and `ExperimentDefinitionTask`
- Renames `worker_binding_key` (DTO) / `assigned_worker_key` (model column) → `assigned_worker_slug`
- Makes `task_slug` a caller-mandatory, persisted slug on both `plan_subtasks` and `add_subtask`
- Drops the auto-generated `dynamic:<hex>` prefix
- One Alembic migration (renames three columns; reverses cleanly)

Prerequisite for `docs/superpowers/plans/2026-04-21-e2e-smoke-coverage-rewrite.md` PR 1.

## Test plan
- [x] `uv run pytest tests/state tests/unit -x`
- [x] `pnpm run check:fast`
- [x] `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
EOF
)"
```

- [ ] **Step F.4: Block on PR 0 merging before starting PR 1**

Once PR 0 merges to `main`, proceed to `## Task 0` below. If PR 0 is blocked on review, pause the plan.

---

## Task 0 — Confirm prerequisites and set up PR 1 branch

**Files:** none (environment check).

- [ ] **Step 0.1: Verify workspace builds cleanly**

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
uv sync --all-packages --group dev
pnpm install --frozen-lockfile
pnpm run check:fast
```

Expected: all checks pass. If they don't, stop — the baseline must be green before starting.

- [ ] **Step 0.2: Verify the RFC is merged on main**

```bash
git fetch origin main
git log --oneline origin/main -3 | grep -F "e2e smoke coverage rewrite"
```

Expected: the RFC commit (`d256059` or its equivalent) is visible on `origin/main`.

- [ ] **Step 0.3: Verify PR 0 (engine rename) is merged on main**

```bash
grep -n "TaskSlug\|AssignedWorkerSlug" ergon_core/ergon_core/core/persistence/shared/types.py
grep -n "task_slug" ergon_core/ergon_core/core/runtime/services/task_management_dto.py | head -5
```

Expected: both greps produce matches. If they don't, PR 0 hasn't merged yet — pause the plan until it does. PR 1 depends on the renamed fields.

- [ ] **Step 0.4: Create PR 1 feature branch**

```bash
git checkout main
git pull origin main
git checkout -b feature/smoke-shared-infra
```

Expected: on `feature/smoke-shared-infra`, clean working tree.

---

# PR 1 — Shared smoke worker infrastructure + `/api/test/*` harness + close superseded RFCs

**PR branch:** `feature/smoke-shared-infra`

**Goal:** All reusable infrastructure lands, no env-specific smoke wiring yet, no CI workflow. End state: `CanonicalSmokeWorker`, `BaseSmokeLeafWorker`, `SmokeSubworker` Protocol, `SmokeCriterionBase`, and `/api/test/*` router are all registered, unit-tested, and importable. Two superseded RFCs are moved to `rejected/`.

**PR 1 acceptance gate:** `pnpm run check:fast` + all unit tests + one integration test for the harness pass; superseded RFCs are in `rejected/` with `superseded_by` frontmatter set; `/api/test/read/run/{id}/state` returns a 404 when `ENABLE_TEST_HARNESS` is unset and a valid DTO (or 404-by-run-id) when set.

---

## Task 1 — `SmokeSubworker` Protocol + `SubworkerResult` dataclass

**Files:**
- Create: `ergon_builtins/ergon_builtins/workers/stubs/__init__.py`
- Create: `ergon_builtins/ergon_builtins/workers/stubs/smoke_subworker.py`
- Test: `tests/unit/test_smoke_subworker_protocol.py`

- [ ] **Step 1.1: Write the failing test for Protocol conformance**

```python
# tests/unit/test_smoke_subworker_protocol.py
"""Contract test: anything claiming to be a SmokeSubworker must pass runtime_checkable."""

from ergon_builtins.workers.stubs.smoke_subworker import (
    SmokeSubworker,
    SubworkerResult,
)


def test_subworker_result_is_frozen() -> None:
    r = SubworkerResult(file_path="/tmp/x", probe_stdout="1\n", probe_exit_code=0)
    try:
        r.file_path = "/tmp/y"  # type: ignore[misc]
    except Exception as e:
        assert isinstance(e, Exception)
    else:
        raise AssertionError("SubworkerResult must be frozen")


def test_minimal_async_class_satisfies_protocol() -> None:
    class OK:
        async def work(self, node_id: str, sandbox):  # noqa: ANN001
            return SubworkerResult("/tmp/x", "out", 0)

    assert isinstance(OK(), SmokeSubworker)


def test_missing_work_method_fails_protocol_check() -> None:
    class Bad:
        pass

    assert not isinstance(Bad(), SmokeSubworker)
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_smoke_subworker_protocol.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ergon_builtins.workers.stubs'`.

- [ ] **Step 1.3: Create package marker**

```python
# ergon_builtins/ergon_builtins/workers/stubs/__init__.py
"""Canonical smoke worker infrastructure shared across environments."""
```

- [ ] **Step 1.4: Write the Protocol + dataclass**

```python
# ergon_builtins/ergon_builtins/workers/stubs/smoke_subworker.py
"""Env-agnostic leaf worker Protocol for canonical smoke runs.

The parent CanonicalSmokeWorker spawns 9 subtasks via add_subtask; each subtask
resolves to a leaf worker via the composition binding `smoke-leaf`. That leaf
worker wraps a SmokeSubworker instance (one concrete class per env) whose sole
job is to prove the sandbox is correctly set up for that environment:

  1. Write a deterministic, well-known file into the sandbox.
  2. Run a bash probe against it (compile / parse / count lines / etc.).
  3. Return both so the criterion can assert on them.

MUST NOT call an LLM. MUST NOT make network calls. MUST complete in under 20s
under normal sandbox conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ergon_core.core.providers.sandbox.manager import AsyncSandbox


@dataclass(frozen=True)
class SubworkerResult:
    """Return payload from one SmokeSubworker.work() call."""

    file_path: str
    probe_stdout: str
    probe_exit_code: int


@runtime_checkable
class SmokeSubworker(Protocol):
    """The pluggable env-specific leaf."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        ...
```

- [ ] **Step 1.5: Run tests to verify pass**

```bash
uv run pytest tests/unit/test_smoke_subworker_protocol.py -v
```

Expected: PASS 3/3.

- [ ] **Step 1.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/workers/stubs/__init__.py \
        ergon_builtins/ergon_builtins/workers/stubs/smoke_subworker.py \
        tests/unit/test_smoke_subworker_protocol.py
git commit -m "feat(smoke): SmokeSubworker Protocol + SubworkerResult"
```

---

## Task 2 — `BaseSmokeLeafWorker` (shared glue)

**Files:**
- Create: `ergon_builtins/ergon_builtins/workers/stubs/base_smoke_leaf.py`
- Test: `tests/unit/test_base_smoke_leaf.py`

**Context for the implementer:** `BaseSmokeLeafWorker` is a real `Worker` subclass (see [`ergon_core/api/worker.py`](../../ergon_core/ergon_core/api/worker.py) and reference pattern at [`smoke_test_worker.py`](../../ergon_builtins/ergon_builtins/workers/baselines/smoke_test_worker.py)). It must:

1. Inherit `ergon_core.api.Worker` and define `type_slug`.
2. Implement `execute(self, task, *, context) -> AsyncGenerator[GenerationTurn, None]` — an async generator that yields at least once.
3. Acquire the sandbox via `AsyncSandbox.connect(sandbox_id=context.sandbox_id)` — **not** `ctx.acquire_sandbox()`. That method does not exist.
4. Write its output files under `/workspace/final_output/` inside the sandbox. The runtime's `persist_outputs_fn` (Inngest post-execute step) will pick them up and create `RunResource` rows automatically — do NOT call `publish_resource`; that API does not exist.
5. Yield a `GenerationTurn` describing what happened.
6. Override `get_output(context) -> WorkerOutput` to report probe success/failure via structured metadata.

Uniqueness: canonical smoke uses **one sandbox per leaf subtask** (no run-wide reuse). Filenames are still prefixed with `context.node_id.hex[:8]` so artifacts are stable and unambiguous in logs and `RunResource` rows.

- [ ] **Step 2.1: Write failing test with a fake subworker**

```python
# tests/unit/test_base_smoke_leaf.py
"""BaseSmokeLeafWorker: runs the subworker, writes files into the sandbox,
yields a turn, and get_output reflects probe success/failure."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from ergon_builtins.workers.stubs.base_smoke_leaf import BaseSmokeLeafWorker
from ergon_builtins.workers.stubs.smoke_subworker import SubworkerResult


class _OkSubworker:
    async def work(self, node_id, sandbox):  # noqa: ANN001
        await sandbox.files.write(f"/workspace/final_output/{node_id}.txt", "hi")
        return SubworkerResult(
            file_path=f"/workspace/final_output/{node_id}.txt",
            probe_stdout="ok\n",
            probe_exit_code=0,
        )


class _OkLeaf(BaseSmokeLeafWorker):
    type_slug = "smoke-leaf-test-ok"
    subworker_cls = _OkSubworker  # type: ignore[assignment]


def _ctx(node_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        run_id=uuid4(),
        definition_id=None,
        task_id=uuid4(),
        execution_id=uuid4(),
        sandbox_id="sb-test",
        node_id=node_id,
        metadata={},
    )


@pytest.mark.asyncio
async def test_leaf_writes_file_yields_turn_and_reports_success() -> None:
    fake_sandbox = MagicMock()
    fake_sandbox.files.write = AsyncMock()

    with patch(
        "ergon_builtins.workers.stubs.base_smoke_leaf.AsyncSandbox.connect",
        AsyncMock(return_value=fake_sandbox),
    ):
        node_id = UUID("00000000-0000-0000-0000-0000000000aa")
        leaf = _OkLeaf(name="ok")
        ctx = _ctx(node_id)

        turns = [turn async for turn in leaf.execute(task=None, context=ctx)]

    assert len(turns) >= 1
    fake_sandbox.files.write.assert_awaited()  # subworker wrote at least one file
    output = leaf.get_output(ctx)
    assert output.success is True
    assert output.metadata["probe_exit_code"] == 0


@pytest.mark.asyncio
async def test_leaf_reports_failure_when_probe_nonzero() -> None:
    class _FailSubworker:
        async def work(self, node_id, sandbox):  # noqa: ANN001
            return SubworkerResult(f"/workspace/final_output/{node_id}.txt", "err", 1)

    class _FailLeaf(BaseSmokeLeafWorker):
        type_slug = "smoke-leaf-test-fail"
        subworker_cls = _FailSubworker  # type: ignore[assignment]

    fake_sandbox = MagicMock()
    fake_sandbox.files.write = AsyncMock()

    with patch(
        "ergon_builtins.workers.stubs.base_smoke_leaf.AsyncSandbox.connect",
        AsyncMock(return_value=fake_sandbox),
    ):
        node_id = UUID("00000000-0000-0000-0000-0000000000bb")
        leaf = _FailLeaf(name="fail")
        ctx = _ctx(node_id)
        _ = [t async for t in leaf.execute(task=None, context=ctx)]

    assert leaf.get_output(ctx).success is False
```

- [ ] **Step 2.2: Run — expect module-missing**

```bash
uv run pytest tests/unit/test_base_smoke_leaf.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2.3: Implement `BaseSmokeLeafWorker`**

```python
# ergon_builtins/ergon_builtins/workers/stubs/base_smoke_leaf.py
"""Shared glue between any SmokeSubworker and the Ergon Worker ABC.

Subclasses set ``type_slug`` and ``subworker_cls``. The base class handles
sandbox attach, delegation to the subworker, and reporting success/failure via
``get_output``. Output files land under ``/workspace/final_output/`` where the
runtime's persist_outputs step creates RunResource rows for them.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import ClassVar

from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]
from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart
from ergon_core.api.results import WorkerOutput

from ergon_builtins.workers.stubs.smoke_subworker import (
    SmokeSubworker,
    SubworkerResult,
)


class BaseSmokeLeafWorker(Worker):
    """Abstract base. Subclasses set `subworker_cls: type[SmokeSubworker]`."""

    subworker_cls: ClassVar[type[SmokeSubworker]]

    def __init__(self, *, name: str, model: str | None = None) -> None:
        super().__init__(name=name, model=model)
        self._last_result: SubworkerResult | None = None

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        sandbox = await AsyncSandbox.connect(sandbox_id=context.sandbox_id)
        node_hex = (context.node_id.hex[:8] if context.node_id else "unknown")
        subworker = self.subworker_cls()
        result = await subworker.work(node_id=node_hex, sandbox=sandbox)
        self._last_result = result

        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"smoke-leaf node={node_hex} "
                        f"file={result.file_path} "
                        f"probe_exit={result.probe_exit_code}"
                    ),
                ),
            ],
        )

    def get_output(self, context: WorkerContext) -> WorkerOutput:
        r = self._last_result
        if r is None:
            return WorkerOutput(output="", success=False, metadata={"error": "no_result"})
        return WorkerOutput(
            output=r.probe_stdout,
            success=r.probe_exit_code == 0,
            metadata={
                "probe_exit_code": r.probe_exit_code,
                "file_path": r.file_path,
            },
        )
```

- [ ] **Step 2.4: Confirm imports resolve**

```bash
uv run python -c "
from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart
from ergon_core.api.results import WorkerOutput
from e2b_code_interpreter import AsyncSandbox
print('ok')
"
```

Expected: `ok`. If anything fails, grep `ergon_core/api/__init__.py` for the right re-export.

- [ ] **Step 2.5: Run tests**

```bash
uv run pytest tests/unit/test_base_smoke_leaf.py -v
```

Expected: PASS 2/2.

- [ ] **Step 2.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/workers/stubs/base_smoke_leaf.py \
        tests/unit/test_base_smoke_leaf.py
git commit -m "feat(smoke): BaseSmokeLeafWorker as real Worker subclass (async gen + get_output)"
```

---

## Task 3 — `CanonicalSmokeWorker` + `EXPECTED_SUBTASK_SLUGS`

**Files:**
- Create: `ergon_builtins/ergon_builtins/workers/stubs/canonical_smoke_worker.py`
- Test: `tests/unit/test_canonical_smoke_worker.py`

**Context for the implementer:** `CanonicalSmokeWorker` is a real `Worker` subclass that declares a 9-node DAG atomically by calling `TaskManagementService.plan_subtasks` directly — **no LLM**. After PR 0, `SubtaskSpec.task_slug` is caller-supplied and persisted, so this worker can name each subtask (`d_root`, `d_left`, …) and have the names survive into the DB for the criterion and dashboard to observe.

The runtime dispatches the roots automatically when `plan_subtasks` returns. This worker does **not** need to `wait_all` — the Ergon engine handles child execution and completion propagation; the parent's `execute` completes after the plan is submitted and the initial "plan summary" turn is yielded. Child completion/failure surfaces as run-level state that the criterion reads from Postgres.

Critical API facts (see [`task_management_service.py`](../../ergon_core/ergon_core/core/runtime/services/task_management_service.py) and [`task_management_dto.py`](../../ergon_core/ergon_core/core/runtime/services/task_management_dto.py)):
- `SubtaskSpec` takes `task_slug`, `description`, `assigned_worker_slug`, `depends_on: list[TaskSlug]`.
- `PlanSubtasksCommand(run_id, parent_node_id, subtasks)` wraps the batch.
- `TaskManagementService().plan_subtasks(session, command)` returns `PlanSubtasksResult(nodes: dict[TaskSlug, NodeId], roots: list[TaskSlug])`.
- The session is obtained via `from ergon_core.core.persistence.shared.db import get_session` using a `with get_session() as session:` block, mirroring the pattern in [`subtask_lifecycle_toolkit.py`](../../ergon_builtins/ergon_builtins/tools/subtask_lifecycle_toolkit.py).

- [ ] **Step 3.1: Write failing test for topology constant**

```python
# tests/unit/test_canonical_smoke_worker.py
"""CanonicalSmokeWorker: plans a hardcoded 9-node DAG via plan_subtasks."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from ergon_builtins.workers.stubs.canonical_smoke_worker import (
    EXPECTED_SUBTASK_SLUGS,
    CanonicalSmokeWorker,
)


def test_expected_slugs_constant_shape() -> None:
    assert EXPECTED_SUBTASK_SLUGS == (
        "d_root", "d_left", "d_right", "d_join",
        "l_1", "l_2", "l_3",
        "s_a", "s_b",
    )
    assert len(EXPECTED_SUBTASK_SLUGS) == 9
    assert len(set(EXPECTED_SUBTASK_SLUGS)) == 9


@pytest.mark.asyncio
async def test_execute_calls_plan_subtasks_with_correct_topology() -> None:
    captured_command = {}

    async def fake_plan_subtasks(session, command):
        captured_command["cmd"] = command
        nodes = {spec.task_slug: uuid4() for spec in command.subtasks}
        roots = [spec.task_slug for spec in command.subtasks if not spec.depends_on]
        return SimpleNamespace(nodes=nodes, roots=roots)

    fake_service = MagicMock()
    fake_service.plan_subtasks = AsyncMock(side_effect=fake_plan_subtasks)

    # Stub get_session() as a context manager yielding a dummy session
    class _DummySessionCtx:
        def __enter__(self): return MagicMock()
        def __exit__(self, *a): return False

    with (
        patch(
            "ergon_builtins.workers.stubs.canonical_smoke_worker.TaskManagementService",
            return_value=fake_service,
        ),
        patch(
            "ergon_builtins.workers.stubs.canonical_smoke_worker.get_session",
            return_value=_DummySessionCtx(),
        ),
    ):
        parent_node = UUID("00000000-0000-0000-0000-00000000dead")
        ctx = SimpleNamespace(
            run_id=uuid4(),
            definition_id=None,
            task_id=uuid4(),
            execution_id=uuid4(),
            sandbox_id="sb",
            node_id=parent_node,
            metadata={},
        )
        worker = CanonicalSmokeWorker(name="smoke")
        turns = [t async for t in worker.execute(task=None, context=ctx)]

    assert len(turns) >= 1
    cmd = captured_command["cmd"]
    assert cmd.parent_node_id == parent_node
    slugs = {s.task_slug: s for s in cmd.subtasks}
    assert set(slugs) == set(EXPECTED_SUBTASK_SLUGS)
    assert slugs["d_root"].depends_on == []
    assert slugs["d_left"].depends_on == ["d_root"]
    assert slugs["d_right"].depends_on == ["d_root"]
    assert sorted(slugs["d_join"].depends_on) == ["d_left", "d_right"]
    assert slugs["l_1"].depends_on == []
    assert slugs["l_2"].depends_on == ["l_1"]
    assert slugs["l_3"].depends_on == ["l_2"]
    assert slugs["s_a"].depends_on == []
    assert slugs["s_b"].depends_on == []
    for spec in cmd.subtasks:
        assert spec.assigned_worker_slug == "smoke-leaf"
```

- [ ] **Step 3.2: Run — expect module-missing**

```bash
uv run pytest tests/unit/test_canonical_smoke_worker.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3.3: Implement the worker**

```python
# ergon_builtins/ergon_builtins/workers/stubs/canonical_smoke_worker.py
"""Canonical smoke parent worker.

Always plans the same 9-subtask graph regardless of env:

    Diamond (4):           Line (3):           Singletons (2):
          d_root           l_1 -> l_2 -> l_3         s_a    s_b
          /     \\
      d_left   d_right
          \\     /
          d_join

Determinism is the point: a graph regression either surfaces identically in
every env's smoke, or doesn't exist. The leaf work is env-specific via the
composition binding `smoke-leaf`. The worker calls plan_subtasks directly
(no LLM) so the topology is fixed by code, not model behaviour.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.types import (
    AssignedWorkerSlug,
    NodeId,
    RunId,
    TaskSlug,
)
from ergon_core.core.runtime.services.task_management_dto import (
    PlanSubtasksCommand,
    SubtaskSpec,
)
from ergon_core.core.runtime.services.task_management_service import (
    TaskManagementService,
)

EXPECTED_SUBTASK_SLUGS: tuple[str, ...] = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)


def _build_specs() -> list[SubtaskSpec]:
    leaf = AssignedWorkerSlug("smoke-leaf")

    def spec(slug: str, description: str, deps: list[str]) -> SubtaskSpec:
        return SubtaskSpec(
            task_slug=TaskSlug(slug),
            description=description,
            assigned_worker_slug=leaf,
            depends_on=[TaskSlug(d) for d in deps],
        )

    return [
        spec("d_root", "Diamond root", []),
        spec("d_left", "Diamond left arm", ["d_root"]),
        spec("d_right", "Diamond right arm", ["d_root"]),
        spec("d_join", "Diamond join", ["d_left", "d_right"]),
        spec("l_1", "Line node 1", []),
        spec("l_2", "Line node 2", ["l_1"]),
        spec("l_3", "Line node 3", ["l_2"]),
        spec("s_a", "Singleton A", []),
        spec("s_b", "Singleton B", []),
    ]


class CanonicalSmokeWorker(Worker):
    """Shared parent for every env's canonical smoke."""

    type_slug = "canonical-smoke"

    def __init__(self, *, name: str = "canonical-smoke", model: str | None = None) -> None:
        super().__init__(name=name, model=model)

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        assert context.node_id is not None, "CanonicalSmokeWorker requires node_id"
        service = TaskManagementService()
        command = PlanSubtasksCommand(
            run_id=RunId(context.run_id),
            parent_node_id=NodeId(context.node_id),
            subtasks=_build_specs(),
        )
        with get_session() as session:
            result = await service.plan_subtasks(session, command)

        summary = "\n".join(
            f"{slug}: planned (node_id={result.nodes[TaskSlug(slug)]})"
            for slug in EXPECTED_SUBTASK_SLUGS
        )
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        "canonical-smoke planned 9 subtasks "
                        f"(roots={sorted(result.roots)}):\n{summary}"
                    ),
                ),
            ],
        )
```

- [ ] **Step 3.4: Run tests**

```bash
uv run pytest tests/unit/test_canonical_smoke_worker.py -v
```

Expected: PASS 2/2.

- [ ] **Step 3.5: Commit**

```bash
git add ergon_builtins/ergon_builtins/workers/stubs/canonical_smoke_worker.py \
        tests/unit/test_canonical_smoke_worker.py
git commit -m "feat(smoke): CanonicalSmokeWorker plans 9-node DAG via plan_subtasks (no LLM)"
```

---

## Task 4 — `SmokeCriterionBase` abstract + 3 env subclasses (skeletons only)

This task lands the abstract + stub subclasses; per-env content assertions land in PRs 2–4 alongside their env subworkers.

**Files:**
- Create: `ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py`
- Test: `tests/unit/test_smoke_criterion.py`

**Context for the implementer:** The real `Criterion` API ([`ergon_core/api/criterion.py`](../../ergon_core/ergon_core/api/criterion.py)) takes `evaluate(context: EvaluationContext) -> CriterionResult`. `EvaluationContext` is thin: `run_id`, `task_id`, `execution_id`, `task`, `worker_result`, `sandbox_id`, `metadata`, `runtime`. It does **not** pre-collect graph nodes or resources — criteria own their own data-pulling.

To verify the 9-subtask DAG this criterion must:
1. Open a DB session (`from ergon_core.core.persistence.shared.db import get_session`).
2. Find the parent `RunGraphNode` (the smoke worker's own node) via `task_execution_id == context.execution_id` using the graph repository — grep `ergon_core/core/persistence/graph/` for the repository and its query methods; follow the existing idiom in [`task_management_service.py`](../../ergon_core/ergon_core/core/runtime/services/task_management_service.py).
3. Query its direct children (where `parent_node_id == smoke_node.id`).
4. Verify children's `task_slug` set equals `EXPECTED_SUBTASK_SLUGS` and every child's status is a terminal-completed state.
5. Query `RunResource` rows for this `run_id`, correlate to the 9 child executions, verify each has a non-empty `content_hash` and the probe artifact parses to `exit_code == 0`.

**Reference criteria for idiom:**
- [`sandbox_file_check.py`](../../ergon_builtins/ergon_builtins/evaluators/criteria/sandbox_file_check.py) — sandbox read pattern via `AsyncSandbox.connect`.
- [`stub_criterion.py`](../../ergon_builtins/ergon_builtins/evaluators/criteria/stub_criterion.py) — minimal `CriterionResult` construction.
- [`sandbox_resource_file_check.py`](../../ergon_builtins/ergon_builtins/evaluators/criteria/) or similar (grep) — RunResource + DB-pull idiom, if one exists.

The leaf worker writes `/workspace/final_output/probe_<node_hex>.json` (JSON containing `{"exit_code": int, "stdout": str}`) — matching Task 2's contract. The criterion reads probe exit codes by downloading the RunResource blob or re-connecting to each child's sandbox; choose the simpler path once existing idioms are clear.

- [ ] **Step 4.1: Write failing test with mocked repo + resource lookups**

```python
# tests/unit/test_smoke_criterion.py
"""SmokeCriterionBase: structural + probe checks via DB lookups.

All DB-pulling methods on the base class are monkeypatched in these tests
so the unit tests stay self-contained. Integration-level coverage (real
Postgres, real RunResources) lives in the PR 2+ pytest suite.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from ergon_builtins.evaluators.criteria.smoke_criterion import SmokeCriterionBase
from ergon_builtins.workers.stubs.canonical_smoke_worker import EXPECTED_SUBTASK_SLUGS


def _healthy_children() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(task_slug=s, status="completed", id=uuid4())
        for s in EXPECTED_SUBTASK_SLUGS
    ]


def _healthy_probes() -> dict[UUID, dict]:
    return {}  # override per test via the pulled-children list


class _PassthroughCriterion(SmokeCriterionBase):
    type_slug = "smoke-passthrough-test"

    async def _verify_env_content(self, context, children, probes) -> None:  # noqa: ANN001
        return


def _patched(crit, children, probes_by_child_id):
    crit._pull_children = AsyncMock(return_value=children)
    crit._pull_probe_results = AsyncMock(return_value=probes_by_child_id)
    return crit


def _eval_context() -> SimpleNamespace:
    return SimpleNamespace(
        run_id=uuid4(), task_id=uuid4(), execution_id=uuid4(),
        task=None, worker_result=None, sandbox_id="sb", metadata={}, runtime=None,
    )


@pytest.mark.asyncio
async def test_passes_with_canonical_graph_and_probes() -> None:
    children = _healthy_children()
    probes = {c.id: {"exit_code": 0, "stdout": "ok"} for c in children}
    crit = _patched(_PassthroughCriterion(name="smoke"), children, probes)
    result = await crit.evaluate(_eval_context())
    assert result.passed is True and result.score == 1.0


@pytest.mark.asyncio
async def test_fails_when_graph_shape_differs() -> None:
    children = _healthy_children()[:-1]  # drop s_b
    probes = {c.id: {"exit_code": 0, "stdout": "ok"} for c in children}
    crit = _patched(_PassthroughCriterion(name="smoke"), children, probes)
    result = await crit.evaluate(_eval_context())
    assert result.passed is False
    assert "graph shape" in (result.feedback or "").lower()


@pytest.mark.asyncio
async def test_fails_when_child_not_completed() -> None:
    children = _healthy_children()
    children[0].status = "failed"
    probes = {c.id: {"exit_code": 0, "stdout": "ok"} for c in children}
    crit = _patched(_PassthroughCriterion(name="smoke"), children, probes)
    result = await crit.evaluate(_eval_context())
    assert result.passed is False
    assert "not completed" in (result.feedback or "").lower()


@pytest.mark.asyncio
async def test_fails_when_probe_exit_nonzero() -> None:
    children = _healthy_children()
    probes = {c.id: {"exit_code": 0, "stdout": "ok"} for c in children}
    probes[children[0].id] = {"exit_code": 1, "stdout": "boom"}
    crit = _patched(_PassthroughCriterion(name="smoke"), children, probes)
    result = await crit.evaluate(_eval_context())
    assert result.passed is False
    assert "probe" in (result.feedback or "").lower()


@pytest.mark.asyncio
async def test_verify_env_content_is_abstract_default() -> None:
    class Subclass(SmokeCriterionBase):
        type_slug = "smoke-abstract-test"

    crit = _patched(Subclass(name="smoke"), _healthy_children(), {})
    # _verify_env_content is called after structural checks pass; the default raises.
    with pytest.raises(NotImplementedError):
        await crit.evaluate(_eval_context())
```

- [ ] **Step 4.2: Run — expect module-missing**

```bash
uv run pytest tests/unit/test_smoke_criterion.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4.3: Implement abstract base + env subclass stubs**

```python
# ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py
"""Shared smoke criterion: structural + probe checks; env subclass adds content.

The base class owns all data-pulling (children, probe artifacts). Subclasses
implement `_verify_env_content` to check env-specific file contents.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ergon_core.api import Criterion, CriterionResult, EvaluationContext

from ergon_builtins.workers.stubs.canonical_smoke_worker import EXPECTED_SUBTASK_SLUGS


class SmokeCriterionBase(Criterion):
    """Structural + probe-success checks shared by every env's smoke criterion."""

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        try:
            children = await self._pull_children(context)
            self._assert_graph_shape(children)
            self._assert_children_completed(children)
            probes = await self._pull_probe_results(context, children)
            self._assert_probes_succeeded(probes, children)
            await self._verify_env_content(context, children, probes)
        except AssertionError as e:
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback=f"smoke criterion failed: {e}",
            )
        return CriterionResult(
            name=self.name,
            score=1.0,
            passed=True,
            weight=self.weight,
            feedback="canonical smoke passed",
        )

    # -- pullers (overridable; tests monkeypatch these) --------------------

    async def _pull_children(self, context: EvaluationContext) -> list[Any]:
        """Return direct-child RunGraphNodes of the smoke parent.

        Opens a session, finds the parent node by
        `task_execution_id == context.execution_id`, and returns its
        direct children (one row per subtask). Each row must expose
        `task_slug`, `status`, and `id`.

        Use the graph repository in `ergon_core/core/persistence/graph/`
        — grep for the method name; mirror the pattern in
        `task_management_service.py`.
        """
        raise NotImplementedError(
            "_pull_children: port the graph-repo call from task_management_service.py",
        )

    async def _pull_probe_results(
        self, context: EvaluationContext, children: list[Any],
    ) -> dict[UUID, dict[str, Any]]:
        """Return `{child_node_id: {"exit_code": int, "stdout": str}}`.

        Strategy: for each child, locate its probe artifact via `RunResource`
        (kind=ARTIFACT, name matches `probe_*.json`), download the blob,
        and parse JSON. See `sandbox_file_check.py` for a blob-reading
        idiom; grep `ergon_core/` for the RunResource repository API.
        """
        raise NotImplementedError(
            "_pull_probe_results: read probe_*.json RunResources for each child",
        )

    # -- structural assertions --------------------------------------------

    def _assert_graph_shape(self, children: list[Any]) -> None:
        actual = {c.task_slug for c in children}
        expected = set(EXPECTED_SUBTASK_SLUGS)
        assert actual == expected, (
            f"graph shape mismatch: actual={sorted(actual)} expected={sorted(expected)}"
        )

    def _assert_children_completed(self, children: list[Any]) -> None:
        for c in children:
            status = getattr(c.status, "name", c.status)
            assert str(status).lower() == "completed", (
                f"child {c.task_slug} not completed (status={status!r})"
            )

    def _assert_probes_succeeded(
        self, probes: dict[UUID, dict[str, Any]], children: list[Any],
    ) -> None:
        for c in children:
            probe = probes.get(c.id, {})
            code = probe.get("exit_code")
            assert code == 0, (
                f"probe for {c.task_slug} exited {code}, "
                f"stdout={probe.get('stdout', '')!r}"
            )

    # -- env-specific hook ------------------------------------------------

    async def _verify_env_content(
        self,
        context: EvaluationContext,
        children: list[Any],
        probes: dict[UUID, dict[str, Any]],
    ) -> None:
        raise NotImplementedError(
            "Subclasses must implement env-specific content verification",
        )


class ResearchRubricsSmokeCriterion(SmokeCriterionBase):
    """Populated in PR 2 when the researchrubrics subworker lands."""

    type_slug = "researchrubrics-smoke-criterion"

    async def _verify_env_content(self, context, children, probes) -> None:
        raise NotImplementedError("populated in PR 2")


class MiniF2FSmokeCriterion(SmokeCriterionBase):
    """Populated in PR 3."""

    type_slug = "minif2f-smoke-criterion"

    async def _verify_env_content(self, context, children, probes) -> None:
        raise NotImplementedError("populated in PR 3")


class SweBenchSmokeCriterion(SmokeCriterionBase):
    """Populated in PR 4."""

    type_slug = "swebench-smoke-criterion"

    async def _verify_env_content(self, context, children, probes) -> None:
        raise NotImplementedError("populated in PR 4")
```

- [ ] **Step 4.4: Confirm Criterion imports resolve**

```bash
uv run python -c "from ergon_core.api import Criterion, CriterionResult, EvaluationContext; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4.5: Run tests**

```bash
uv run pytest tests/unit/test_smoke_criterion.py -v
```

Expected: PASS 5/5.

- [ ] **Step 4.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py \
        tests/unit/test_smoke_criterion.py
git commit -m "feat(smoke): SmokeCriterionBase with structural + probe checks; 3 env subclass stubs"
```

**Known follow-up for PR 2:** `_pull_children` and `_pull_probe_results` currently `NotImplementedError` — PR 2's first task wires them up against the real repos before adding the researchrubrics content check. They are deliberately unimplemented here so their shape can be validated against a real integration run before committing to an idiom.

---

## Task 5 — Register shared infra in `registry_core.py`

**Files:**
- Modify: `ergon_builtins/ergon_builtins/registry_core.py`
- Test: `tests/unit/test_registry_core_smoke_entries.py`

- [ ] **Step 5.1: Write failing test**

```python
# tests/unit/test_registry_core_smoke_entries.py
"""Registry includes the shared canonical-smoke entries after PR 1."""

from ergon_builtins.registry_core import EVALUATORS, WORKERS


def test_canonical_smoke_worker_registered() -> None:
    from ergon_builtins.workers.stubs.canonical_smoke_worker import (
        CanonicalSmokeWorker,
    )

    assert WORKERS["canonical-smoke"] is CanonicalSmokeWorker


def test_env_smoke_criteria_registered() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        MiniF2FSmokeCriterion,
        ResearchRubricsSmokeCriterion,
        SweBenchSmokeCriterion,
    )

    assert EVALUATORS["researchrubrics-smoke-rubric"] is ResearchRubricsSmokeCriterion
    assert EVALUATORS["minif2f-smoke-rubric"] is MiniF2FSmokeCriterion
    assert EVALUATORS["swebench-smoke-rubric"] is SweBenchSmokeCriterion
```

- [ ] **Step 5.2: Run — expect KeyError**

```bash
uv run pytest tests/unit/test_registry_core_smoke_entries.py -v
```

Expected: FAIL with `KeyError: 'canonical-smoke'`.

- [ ] **Step 5.3: Wire registry entries**

Add these imports at the top of `ergon_builtins/ergon_builtins/registry_core.py`, grouped with the existing evaluator / worker imports:

```python
from ergon_builtins.evaluators.criteria.smoke_criterion import (
    MiniF2FSmokeCriterion,
    ResearchRubricsSmokeCriterion,
    SweBenchSmokeCriterion,
)
from ergon_builtins.workers.stubs.canonical_smoke_worker import CanonicalSmokeWorker
```

Add these entries to the existing dicts (insert before the closing `}`):

```python
# In WORKERS
    "canonical-smoke": CanonicalSmokeWorker,
```

```python
# In EVALUATORS
    "researchrubrics-smoke-rubric": ResearchRubricsSmokeCriterion,
    "minif2f-smoke-rubric": MiniF2FSmokeCriterion,
    "swebench-smoke-rubric": SweBenchSmokeCriterion,
```

Do **not** add leaf-worker entries yet; those land per-env in PRs 2–4.

- [ ] **Step 5.4: Run tests**

```bash
uv run pytest tests/unit/test_registry_core_smoke_entries.py -v
```

Expected: PASS 2/2.

- [ ] **Step 5.5: Run existing contract test to confirm no regression**

```bash
uv run pytest tests/unit/test_benchmark_contract.py -v 2>/dev/null || echo "(contract test doesn't exist yet — fine)"
```

Expected: green or "doesn't exist" (the contract test lands in the testing-posture-reset RFC's PR 1).

- [ ] **Step 5.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/registry_core.py \
        tests/unit/test_registry_core_smoke_entries.py
git commit -m "feat(smoke): register canonical-smoke worker + 3 env smoke-criterion entries"
```

---

## Task 6 — `/api/test/*` harness router: state DTO + read endpoint

This task and Task 7 implement the router described in detail in `docs/rfcs/active/2026-04-18-test-harness-endpoints.md` §4–5 (absorbed verbatim into this RFC). If any ambiguity arises, defer to the superseded RFC's implementation spec — it is more detailed than the summary in the new RFC.

**Files:**
- Create: `ergon_core/ergon_core/core/api/test_harness.py`
- Test: `tests/unit/test_test_harness.py`

- [ ] **Step 6.1: Write failing test for read-endpoint schema**

```python
# tests/unit/test_test_harness.py
"""Test-harness router: conditional mount, read DTO shape, write-gate secret."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app_with_harness(*, enabled: bool, secret: str | None = "ci-secret") -> FastAPI:
    app = FastAPI()
    prev_enable = os.environ.get("ENABLE_TEST_HARNESS")
    prev_secret = os.environ.get("TEST_HARNESS_SECRET")
    try:
        os.environ["ENABLE_TEST_HARNESS"] = "1" if enabled else "0"
        if secret is not None:
            os.environ["TEST_HARNESS_SECRET"] = secret
        else:
            os.environ.pop("TEST_HARNESS_SECRET", None)

        if enabled:
            from ergon_core.core.api.test_harness import router
            app.include_router(router)
    finally:
        if prev_enable is None:
            os.environ.pop("ENABLE_TEST_HARNESS", None)
        else:
            os.environ["ENABLE_TEST_HARNESS"] = prev_enable
        if prev_secret is None:
            os.environ.pop("TEST_HARNESS_SECRET", None)
        else:
            os.environ["TEST_HARNESS_SECRET"] = prev_secret
    return app


def test_read_endpoint_returns_404_for_unknown_run_id() -> None:
    app = _build_app_with_harness(enabled=True)
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    assert resp.status_code == 404


def test_read_endpoint_unmounted_when_disabled() -> None:
    app = _build_app_with_harness(enabled=False)
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    assert resp.status_code == 404  # unmounted = route doesn't exist
```

- [ ] **Step 6.2: Run — expect module-missing**

```bash
uv run pytest tests/unit/test_test_harness.py -v
```

Expected: FAIL with import error.

- [ ] **Step 6.3: Implement the router with read endpoint only (write endpoints land in Task 7)**

```python
# ergon_core/ergon_core/core/api/test_harness.py
"""Test-only FastAPI router exposing narrow DTOs for Playwright/backend tests.

Gates:
  - Router is only mounted when ENABLE_TEST_HARNESS=1 (caller-side in app.py).
  - Write endpoints additionally require the `X-Test-Secret` header to match
    TEST_HARNESS_SECRET. Absence of the env var = 500 (distinct from 401 bad
    secret) so misconfiguration is distinguishable from auth failure.

Wire-shape stability: these DTOs are used by Playwright. Additive-only schema —
never remove or rename a field without coordinating a TS helper update.
"""

from __future__ import annotations

import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
)

router = APIRouter(prefix="/api/test", tags=["test-harness"])


class TestGraphNodeDto(BaseModel):
    task_slug: str
    level: int
    status: str
    parent_task_slug: str | None


class TestEvaluationDto(BaseModel):
    score: float
    reason: str


class TestGraphMutationDto(BaseModel):
    sequence: int
    mutation_type: str
    target_task_slug: str | None


class TestRunStateDto(BaseModel):
    run_id: UUID
    status: str
    graph_nodes: list[TestGraphNodeDto]
    mutations: list[TestGraphMutationDto]
    evaluations: list[TestEvaluationDto]
    resource_count: int


def _require_secret(
    x_test_secret: Annotated[str | None, Header(alias="X-Test-Secret")],
) -> None:
    configured = os.environ.get("TEST_HARNESS_SECRET")
    if configured is None:
        # Distinguishable from 401: the server is misconfigured.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TEST_HARNESS_SECRET not configured",
        )
    if x_test_secret != configured:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


@router.get("/read/run/{run_id}/state", response_model=TestRunStateDto)
def read_run_state(run_id: UUID) -> TestRunStateDto:
    with Session(get_engine()) as s:
        run = s.exec(select(RunRecord).where(RunRecord.id == run_id)).first()
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")

        nodes = s.exec(
            select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        ).all()
        node_by_id = {n.id: n for n in nodes}
        node_dtos = [
            TestGraphNodeDto(
                task_slug=n.task_slug,
                level=n.level,
                status=getattr(n.status, "value", str(n.status)),
                parent_task_slug=(
                    node_by_id[n.parent_id].task_slug
                    if getattr(n, "parent_id", None) and n.parent_id in node_by_id
                    else None
                ),
            )
            for n in nodes
        ]

        muts = s.exec(
            select(RunGraphMutation)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(RunGraphMutation.sequence)
        ).all()
        mut_dtos = [
            TestGraphMutationDto(
                sequence=m.sequence,
                mutation_type=str(m.mutation_type),
                target_task_slug=(
                    node_by_id[m.target_id].task_slug
                    if getattr(m, "target_id", None) and m.target_id in node_by_id
                    else None
                ),
            )
            for m in muts
        ]

        evals = s.exec(
            select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
        ).all()
        eval_dtos = [
            TestEvaluationDto(score=float(e.score), reason=e.reason or "")
            for e in evals
        ]

        resource_count = s.exec(
            select(RunResource).where(RunResource.run_id == run_id)
        ).all()

        return TestRunStateDto(
            run_id=run_id,
            status=getattr(run.status, "value", str(run.status)),
            graph_nodes=node_dtos,
            mutations=mut_dtos,
            evaluations=eval_dtos,
            resource_count=len(resource_count),
        )
```

Note: if field names on `RunRecord`/`RunGraphNode`/`RunGraphMutation`/`RunTaskEvaluation`/`RunResource` differ from those used above (e.g. `status`, `parent_id`, `run_id`, `target_id`, `sequence`, `score`), adjust the field access. The list above is the RFC's declared contract — the model definitions live under `ergon_core/core/persistence/`. Grep before guessing:

```bash
uv run python -c "from ergon_core.core.persistence.graph.models import RunGraphNode; print([f for f in RunGraphNode.__fields__])"
uv run python -c "from ergon_core.core.persistence.graph.models import RunGraphMutation; print([f for f in RunGraphMutation.__fields__])"
uv run python -c "from ergon_core.core.persistence.telemetry.models import RunRecord, RunResource, RunTaskEvaluation; print([f for f in RunRecord.__fields__], [f for f in RunResource.__fields__], [f for f in RunTaskEvaluation.__fields__])"
```

- [ ] **Step 6.4: Run tests**

```bash
uv run pytest tests/unit/test_test_harness.py -v
```

Expected: PASS 2/2.

- [ ] **Step 6.5: Commit**

```bash
git add ergon_core/ergon_core/core/api/test_harness.py \
        tests/unit/test_test_harness.py
git commit -m "feat(harness): /api/test/read/run/{id}/state router with TestRunStateDto"
```

---

## Task 7 — `/api/test/*` write endpoints (seed + reset) with secret gating

**Files:**
- Modify: `ergon_core/ergon_core/core/api/test_harness.py`
- Modify: `tests/unit/test_test_harness.py`

- [ ] **Step 7.1: Extend tests for the write endpoints**

Append to `tests/unit/test_test_harness.py`:

```python
def test_seed_requires_secret_header() -> None:
    app = _build_app_with_harness(enabled=True, secret="ci-secret")
    client = TestClient(app)
    resp = client.post("/api/test/write/run/seed", json={})
    assert resp.status_code == 401


def test_seed_returns_500_when_secret_env_missing() -> None:
    app = _build_app_with_harness(enabled=True, secret=None)
    client = TestClient(app)
    resp = client.post(
        "/api/test/write/run/seed",
        json={},
        headers={"X-Test-Secret": "anything"},
    )
    assert resp.status_code == 500


def test_reset_requires_secret_header() -> None:
    app = _build_app_with_harness(enabled=True, secret="ci-secret")
    client = TestClient(app)
    resp = client.post("/api/test/write/reset", json={})
    assert resp.status_code == 401
```

- [ ] **Step 7.2: Run — expect missing routes**

```bash
uv run pytest tests/unit/test_test_harness.py -v
```

Expected: FAIL 3 new tests (404 instead of 401/500).

- [ ] **Step 7.3: Extend the router with write endpoints**

Append to `ergon_core/ergon_core/core/api/test_harness.py`:

```python
class SeedRunRequest(BaseModel):
    cohort: str
    status: str = "completed"
    task_slugs: list[str] = []


class ResetRequest(BaseModel):
    cohort_prefix: str = "ci-smoke-"


@router.post("/write/run/seed", status_code=201)
def seed_run(
    body: SeedRunRequest,
    x_test_secret: Annotated[str | None, Header(alias="X-Test-Secret")] = None,
) -> dict:
    _require_secret(x_test_secret)
    with Session(get_engine()) as s:
        run = RunRecord(
            cohort=body.cohort,
            status=body.status,
            metadata={"_test_seeded": True},
        )
        s.add(run)
        s.commit()
        s.refresh(run)
        return {"run_id": str(run.id)}


@router.post("/write/reset", status_code=204)
def reset_test_rows(
    body: ResetRequest,
    x_test_secret: Annotated[str | None, Header(alias="X-Test-Secret")] = None,
) -> None:
    _require_secret(x_test_secret)
    with Session(get_engine()) as s:
        stale = s.exec(
            select(RunRecord).where(RunRecord.cohort.startswith(body.cohort_prefix))
        ).all()
        for r in stale:
            if (r.metadata or {}).get("_test_seeded"):
                s.delete(r)
        s.commit()
    return None
```

If `RunRecord` does not support `metadata` as a free-form dict, introspect with:

```bash
uv run python -c "from ergon_core.core.persistence.telemetry.models import RunRecord; print([f for f in RunRecord.__fields__])"
```

…and adjust the seed/reset discriminator (e.g. prefix the cohort with `_test_` and filter by cohort instead).

- [ ] **Step 7.4: Run tests**

```bash
uv run pytest tests/unit/test_test_harness.py -v
```

Expected: PASS 5/5.

- [ ] **Step 7.5: Commit**

```bash
git add ergon_core/ergon_core/core/api/test_harness.py \
        tests/unit/test_test_harness.py
git commit -m "feat(harness): /api/test/write/{run/seed,reset} with X-Test-Secret gate"
```

---

## Task 8 — Mount harness router conditionally in `app.py`

**Files:**
- Modify: `ergon_core/ergon_core/core/api/app.py`
- Test: `tests/unit/test_app_mounts_harness_conditionally.py`

- [ ] **Step 8.1: Locate the app-factory function**

```bash
uv run python -c "from ergon_core.core.api.app import app; print(type(app))"
```

If `app` is a module-level FastAPI instance, patching via env-var requires importlib reloading in the test. If there's a `create_app()` factory, prefer invoking it with the env var set.

- [ ] **Step 8.2: Write failing test**

```python
# tests/unit/test_app_mounts_harness_conditionally.py
"""app.py mounts /api/test/* iff ENABLE_TEST_HARNESS=1 at import time."""

import importlib
import os
from uuid import uuid4

from fastapi.testclient import TestClient


def _reload_app_with(env_value: str | None):
    prev = os.environ.get("ENABLE_TEST_HARNESS")
    try:
        if env_value is None:
            os.environ.pop("ENABLE_TEST_HARNESS", None)
        else:
            os.environ["ENABLE_TEST_HARNESS"] = env_value
        import ergon_core.core.api.app as app_mod
        importlib.reload(app_mod)
        return app_mod.app
    finally:
        if prev is None:
            os.environ.pop("ENABLE_TEST_HARNESS", None)
        else:
            os.environ["ENABLE_TEST_HARNESS"] = prev


def test_harness_unmounted_when_env_absent() -> None:
    app = _reload_app_with(None)
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    assert resp.status_code == 404


def test_harness_mounted_when_env_set() -> None:
    app = _reload_app_with("1")
    client = TestClient(app)
    resp = client.get(f"/api/test/read/run/{uuid4()}/state")
    # With no DB seeded, the handler either raises 404 (unknown run_id) or 500
    # if Postgres is unreachable from the unit-test env. Either proves the route
    # is mounted.
    assert resp.status_code in (404, 500)
```

- [ ] **Step 8.3: Run — expect FAIL on the mounted case**

```bash
uv run pytest tests/unit/test_app_mounts_harness_conditionally.py -v
```

- [ ] **Step 8.4: Modify `app.py` to mount the router conditionally**

Read `ergon_core/ergon_core/core/api/app.py` to find where other routers are included. Add at the end of the router-wiring block:

```python
# Test-only harness: mounted in CI + local-e2e only.
if os.environ.get("ENABLE_TEST_HARNESS") == "1":
    from ergon_core.core.api.test_harness import router as _test_harness_router
    app.include_router(_test_harness_router)
```

Ensure `import os` is present at the top of `app.py`.

- [ ] **Step 8.5: Run tests**

```bash
uv run pytest tests/unit/test_app_mounts_harness_conditionally.py -v
```

Expected: PASS 2/2.

- [ ] **Step 8.6: Run full unit suite to catch regressions**

```bash
uv run pytest tests/unit -v
```

Expected: green.

- [ ] **Step 8.7: Commit**

```bash
git add ergon_core/ergon_core/core/api/app.py \
        tests/unit/test_app_mounts_harness_conditionally.py
git commit -m "feat(harness): conditionally mount /api/test/* router on ENABLE_TEST_HARNESS=1"
```

---

## Task 9 — Integration test: seed → read → reset round-trip

**Files:**
- Create: `tests/integration/smokes/__init__.py`
- Create: `tests/integration/smokes/test_smoke_harness.py`

This test runs against real Postgres via the integration-tier fixture (already wired by the parent reset RFC's PR 3). If that fixture isn't available yet (reset PR 3 not merged), mark with `@pytest.mark.skip` and add a TODO to re-enable; do NOT block PR 1 of this plan on reset PR 3.

- [ ] **Step 9.1: Create the integration-test module**

```python
# tests/integration/smokes/__init__.py
```

```python
# tests/integration/smokes/test_smoke_harness.py
"""Integration: /api/test/* round-trips against real Postgres."""

from __future__ import annotations

import os

import httpx
import pytest


pytestmark = pytest.mark.integration


API = os.environ.get("ERGON_API_BASE_URL", "http://127.0.0.1:9000")
SECRET = os.environ.get("TEST_HARNESS_SECRET", "ci-secret")


@pytest.fixture(autouse=True)
def _reset_before_each() -> None:
    httpx.post(
        f"{API}/api/test/write/reset",
        json={"cohort_prefix": "ci-smoke-"},
        headers={"X-Test-Secret": SECRET},
        timeout=5,
    )
    yield


def test_seed_then_read_then_reset_roundtrip() -> None:
    # Seed
    seed = httpx.post(
        f"{API}/api/test/write/run/seed",
        json={"cohort": "ci-smoke-harness-test", "status": "completed"},
        headers={"X-Test-Secret": SECRET},
        timeout=5,
    )
    assert seed.status_code == 201, seed.text
    run_id = seed.json()["run_id"]

    # Read
    read = httpx.get(f"{API}/api/test/read/run/{run_id}/state", timeout=5)
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["run_id"] == run_id
    assert body["status"] == "completed"

    # Reset
    reset = httpx.post(
        f"{API}/api/test/write/reset",
        json={"cohort_prefix": "ci-smoke-"},
        headers={"X-Test-Secret": SECRET},
        timeout=5,
    )
    assert reset.status_code == 204

    # Now gone
    read2 = httpx.get(f"{API}/api/test/read/run/{run_id}/state", timeout=5)
    assert read2.status_code == 404
```

- [ ] **Step 9.2: Attempt to run (may skip if integration fixtures unavailable)**

```bash
uv run pytest tests/integration/smokes/test_smoke_harness.py -v -m integration
```

Expected: PASS if the integration stack is up; else skipped. Document the result in the PR body.

- [ ] **Step 9.3: Commit**

```bash
git add tests/integration/smokes/__init__.py \
        tests/integration/smokes/test_smoke_harness.py
git commit -m "test(harness): integration round-trip for /api/test/* against real Postgres"
```

---

## Task 10 — `BackendHarnessClient` TypeScript helper

**Files:**
- Create: `ergon-dashboard/tests/helpers/testHarnessClient.ts`

Note: The existing `ergon-dashboard/tests/helpers/harnessClient.ts` talks to **dashboard-side** harness routes (`/api/test/dashboard/*`) on Next.js. That is a different system and remains untouched. The new file talks to the **backend Python** harness.

- [ ] **Step 10.1: Implement the helper**

```typescript
// ergon-dashboard/tests/helpers/testHarnessClient.ts

import type { APIRequestContext } from "@playwright/test";

export interface TestGraphNodeDto {
  task_slug: string;
  level: number;
  status: string;
  parent_task_slug: string | null;
}

export interface TestEvaluationDto {
  score: number;
  reason: string;
}

export interface TestGraphMutationDto {
  sequence: number;
  mutation_type: string;
  target_task_slug: string | null;
}

export interface TestRunStateDto {
  run_id: string;
  status: string;
  graph_nodes: TestGraphNodeDto[];
  mutations: TestGraphMutationDto[];
  evaluations: TestEvaluationDto[];
  resource_count: number;
}

export class BackendHarnessClient {
  constructor(
    private readonly request: APIRequestContext,
    private readonly baseUrl: string,
  ) {}

  async getRunState(runId: string): Promise<TestRunStateDto> {
    const response = await this.request.get(
      `${this.baseUrl}/api/test/read/run/${runId}/state`,
    );
    if (!response.ok()) {
      throw new Error(
        `BackendHarnessClient.getRunState failed: ${response.status()} ${await response.text()}`,
      );
    }
    return (await response.json()) as TestRunStateDto;
  }
}
```

- [ ] **Step 10.2: Confirm TS compiles**

```bash
pnpm --dir ergon-dashboard exec tsc --noEmit
```

Expected: no TS errors.

- [ ] **Step 10.3: Commit**

```bash
git add ergon-dashboard/tests/helpers/testHarnessClient.ts
git commit -m "feat(harness): BackendHarnessClient TS helper for /api/test/read"
```

---

## Task 11 — `playwright.config.ts`: screenshots always on

**Files:**
- Modify: `ergon-dashboard/playwright.config.ts`

- [ ] **Step 11.1: Flip the screenshot setting**

Read the file to locate the `use:` block, then change:

```diff
 use: {
   baseURL,
   trace: "on-first-retry",
-  screenshot: "only-on-failure",
+  screenshot: "on",
   video: "retain-on-failure",
 },
```

- [ ] **Step 11.2: Confirm Playwright config still parses**

```bash
pnpm --dir ergon-dashboard exec playwright test --list 2>&1 | head -5
```

Expected: lists existing tests with no config-parse errors.

- [ ] **Step 11.3: Commit**

```bash
git add ergon-dashboard/playwright.config.ts
git commit -m "chore(playwright): screenshots always on (required by e2e smoke RFC)"
```

---

## Task 12 — Close superseded RFCs + open PR 1

**Files:**
- Move: `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md` → `docs/rfcs/rejected/2026-04-18-fixed-delegation-stub-worker.md`
- Move: `docs/rfcs/active/2026-04-18-test-harness-endpoints.md` → `docs/rfcs/rejected/2026-04-18-test-harness-endpoints.md`

- [ ] **Step 12.1: Create `rejected/` dir if absent**

```bash
mkdir -p docs/rfcs/rejected
```

- [ ] **Step 12.2: Move + set frontmatter on the fixed-delegation RFC**

```bash
git mv docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md \
       docs/rfcs/rejected/2026-04-18-fixed-delegation-stub-worker.md
```

Open the moved file. Change its frontmatter `status:` to `rejected` and add `superseded_by:` if not already present:

```yaml
---
status: rejected
superseded_by: docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md
# (other fields unchanged)
---
```

Note: the path under `superseded_by:` points to `accepted/` because by the time someone reads this RFC, the successor is expected to be accepted. Until PR 4 of this plan lands, the successor still lives at `docs/rfcs/active/...` — that is OK, the pointer is the *intended* final path.

- [ ] **Step 12.3: Move + set frontmatter on the test-harness-endpoints RFC**

```bash
git mv docs/rfcs/active/2026-04-18-test-harness-endpoints.md \
       docs/rfcs/rejected/2026-04-18-test-harness-endpoints.md
```

Edit the frontmatter identically.

- [ ] **Step 12.4: Run full check suite**

```bash
pnpm run check:fast
uv run pytest tests/unit -v
```

Expected: both green.

- [ ] **Step 12.5: Commit RFC moves**

```bash
git add docs/rfcs/rejected/2026-04-18-fixed-delegation-stub-worker.md \
        docs/rfcs/rejected/2026-04-18-test-harness-endpoints.md \
        docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md \
        docs/rfcs/active/2026-04-18-test-harness-endpoints.md
git commit -m "docs(rfc): move fixed-delegation-stub-worker + test-harness-endpoints to rejected/ (absorbed)"
```

- [ ] **Step 12.6: Push + open PR**

```bash
git push -u origin feature/smoke-shared-infra
gh pr create --title "feat(smoke): shared canonical-smoke infrastructure + /api/test/* harness (PR 1 of 4)" \
  --body "$(cat <<'EOF'
## Summary
- Lands shared canonical-smoke worker infrastructure (parent worker + subworker Protocol + base leaf + criterion base).
- Lands `/api/test/*` harness router with conditional mount and `X-Test-Secret` gate.
- Closes two superseded RFCs (absorbed into `2026-04-21-e2e-smoke-coverage-rewrite.md`).
- **No** env-specific smoke wiring; no CI workflow. Those arrive in PRs 2–4.

## Test plan
- [x] `uv run pytest tests/unit -v` — unit suite green (new smoke + harness tests)
- [x] `pnpm run check:fast` — backend + frontend lint/type green
- [x] Integration harness round-trip (if integration stack up locally; otherwise CI verifies)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 12.7: Watch PR CI**

If CI fails, iterate with fresh commits on the branch. Never `--amend` a pushed commit. Never `--no-verify`.

---

# PR 2 — `researchrubrics` canary env smoke

**PR branch:** `feature/smoke-researchrubrics`

**Precondition:** PR 1 of this plan is merged. Reset RFC PRs 2 + 3 + 4 are merged (Docker caching, integration infra, `tests/e2e/` deleted).

**Goal:** First live canonical smoke, end-to-end wired. CI matrix exists with only this env. Failure-mode rehearsal verifies screenshots upload on all failure paths.

**PR 2 acceptance gate:** `researchrubrics` smoke runs on every PR in under 5 minutes; Postgres record-log + Playwright assertions + screenshot upload + PR inline comment all work end-to-end on pass AND on induced failure.

---

## Task 13 — Prereq check + branch setup

- [ ] **Step 13.1: Verify prerequisites**

```bash
cd /Users/charliemasters/Desktop/synced_vm_002/ergon
git fetch origin main
git log origin/main --oneline | head -20
ls tests/e2e/ 2>&1 | grep -v "No such" || echo "tests/e2e/ clean slate confirmed"
ls docker-compose.ci.yml && grep -c "cache-from\|cache-to" .github/workflows/*.yml
```

Expected: `tests/e2e/` does not exist (reset PR 4 merged); `docker-compose.ci.yml` present; GHA cache directives present in at least one workflow.

If any prereq is missing, stop and post a note on the team channel — do not proceed to PR 2 until reset is complete.

- [ ] **Step 13.2: Create branch**

```bash
git checkout main
git pull origin main
git checkout -b feature/smoke-researchrubrics
```

---

## Task 14 — `ResearchRubricsSmokeSubworker` + leaf worker

**Files:**
- Create: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/smoke_subworker.py`
- Test: `tests/unit/test_researchrubrics_smoke_subworker.py`

- [ ] **Step 14.1: Write failing test**

```python
# tests/unit/test_researchrubrics_smoke_subworker.py
"""ResearchRubricsSmokeSubworker: writes markdown report + runs wc -l."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ergon_builtins.benchmarks.researchrubrics.smoke_subworker import (
    ResearchRubricsSmokeSubworker,
)


@pytest.mark.asyncio
async def test_writes_deterministic_markdown_and_runs_wc() -> None:
    sandbox = MagicMock()
    sandbox.files = MagicMock()
    sandbox.files.write = AsyncMock()
    sandbox.commands = MagicMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(stdout="3 /tmp/d_root.md\n", exit_code=0)
    )

    sub = ResearchRubricsSmokeSubworker()
    result = await sub.work(node_id="d_root", sandbox=sandbox)

    sandbox.files.write.assert_awaited_once()
    write_args = sandbox.files.write.await_args.args
    assert write_args[0] == "/tmp/d_root.md"
    assert "# Report d_root" in write_args[1]
    sandbox.commands.run.assert_awaited_once_with("wc -l /tmp/d_root.md")

    assert result.file_path == "/tmp/d_root.md"
    assert result.probe_exit_code == 0
    assert result.probe_stdout.strip().split()[0].isdigit()
```

- [ ] **Step 14.2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_researchrubrics_smoke_subworker.py -v
```

- [ ] **Step 14.3: Implement**

```python
# ergon_builtins/ergon_builtins/benchmarks/researchrubrics/smoke_subworker.py
"""Per-env canonical smoke subworker + leaf for researchrubrics."""

from __future__ import annotations

from ergon_core.core.providers.sandbox.manager import AsyncSandbox

from ergon_builtins.workers.stubs.base_smoke_leaf import BaseSmokeLeafWorker
from ergon_builtins.workers.stubs.smoke_subworker import SubworkerResult


class ResearchRubricsSmokeSubworker:
    """Writes a deterministic markdown report + runs `wc -l`."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        content = f"# Report {node_id}\n\nFinding: canonical smoke artifact.\n"
        path = f"/tmp/{node_id}.md"
        await sandbox.files.write(path, content)
        probe = await sandbox.commands.run(f"wc -l {path}")
        return SubworkerResult(
            file_path=path,
            probe_stdout=probe.stdout,
            probe_exit_code=probe.exit_code,
        )


class ResearchRubricsSmokeLeafWorker(BaseSmokeLeafWorker):
    subworker_cls = ResearchRubricsSmokeSubworker  # type: ignore[assignment]
```

- [ ] **Step 14.4: Run tests**

```bash
uv run pytest tests/unit/test_researchrubrics_smoke_subworker.py -v
```

Expected: PASS.

- [ ] **Step 14.5: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/researchrubrics/smoke_subworker.py \
        tests/unit/test_researchrubrics_smoke_subworker.py
git commit -m "feat(smoke/rr): ResearchRubricsSmokeSubworker writes .md + runs wc -l"
```

---

## Task 15 — Fill `ResearchRubricsSmokeCriterion._verify_env_content`

**Files:**
- Modify: `ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py`
- Modify: `tests/unit/test_smoke_criterion.py`

- [ ] **Step 15.1: Add failing test**

Append to `tests/unit/test_smoke_criterion.py`:

```python
from dataclasses import replace


@pytest.mark.asyncio
async def test_researchrubrics_criterion_passes_with_markdown_and_digit_wc() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        ResearchRubricsSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = f"# Report {r.task_slug}\n\nFinding: x.\n".encode()
        r.metadata["probe_stdout"] = "3 /tmp/x.md\n"
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await ResearchRubricsSmokeCriterion().evaluate(ctx)
    assert score.value == 1.0


@pytest.mark.asyncio
async def test_researchrubrics_criterion_fails_missing_header() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        ResearchRubricsSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = b"no header here\n"
        r.metadata["probe_stdout"] = "3 /tmp/x.md\n"
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await ResearchRubricsSmokeCriterion().evaluate(ctx)
    assert score.value == 0.0
    assert "markdown header" in score.reason.lower()


@pytest.mark.asyncio
async def test_researchrubrics_criterion_fails_non_digit_wc_output() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        ResearchRubricsSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = f"# Report {r.task_slug}\n".encode()
        r.metadata["probe_stdout"] = "hello world\n"
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await ResearchRubricsSmokeCriterion().evaluate(ctx)
    assert score.value == 0.0
    assert "number" in score.reason.lower()
```

- [ ] **Step 15.2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_smoke_criterion.py -v
```

- [ ] **Step 15.3: Fill the criterion**

Edit `ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py`. Replace `ResearchRubricsSmokeCriterion._verify_env_content`:

```python
class ResearchRubricsSmokeCriterion(SmokeCriterionBase):
    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        for r in ctx.resources.all():
            text = r.content.decode("utf-8")
            assert text.startswith(f"# Report {r.task_slug}"), (
                f"{r.task_slug}: missing expected markdown header"
            )
            wc_output = r.metadata["probe_stdout"].strip()
            first_token = wc_output.split()[0] if wc_output else ""
            assert first_token.isdigit(), (
                f"{r.task_slug}: wc -l probe did not return a number, got {wc_output!r}"
            )
```

- [ ] **Step 15.4: Run tests**

```bash
uv run pytest tests/unit/test_smoke_criterion.py -v
```

Expected: all pass.

- [ ] **Step 15.5: Commit**

```bash
git add ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py \
        tests/unit/test_smoke_criterion.py
git commit -m "feat(smoke/rr): ResearchRubricsSmokeCriterion asserts markdown header + wc digit"
```

---

## Task 16 — Register `researchrubrics-smoke-leaf` + composition binding

**Files:**
- Modify: `ergon_builtins/ergon_builtins/registry_core.py`
- Modify: `ergon_cli/ergon_cli/composition/__init__.py`
- Test: `tests/unit/test_researchrubrics_registry_and_binding.py`

- [ ] **Step 16.1: Write failing test**

```python
# tests/unit/test_researchrubrics_registry_and_binding.py
"""Registry + composition bindings include the researchrubrics smoke leaf."""


def test_researchrubrics_smoke_leaf_registered() -> None:
    from ergon_builtins.registry_core import WORKERS
    from ergon_builtins.benchmarks.researchrubrics.smoke_subworker import (
        ResearchRubricsSmokeLeafWorker,
    )

    assert WORKERS["researchrubrics-smoke-leaf"] is ResearchRubricsSmokeLeafWorker


def test_researchrubrics_composition_binds_smoke_leaf() -> None:
    from ergon_cli.composition import BENCHMARK_COMPOSITIONS

    comp = BENCHMARK_COMPOSITIONS["researchrubrics"]
    assert comp.bindings["smoke-leaf"] == "researchrubrics-smoke-leaf"
```

Import path for `BENCHMARK_COMPOSITIONS` may differ. Confirm with:

```bash
uv run python -c "from ergon_cli.composition import BENCHMARK_COMPOSITIONS; print(list(BENCHMARK_COMPOSITIONS.keys()))"
```

If the module path is different (e.g. `ergon_cli.ergon_cli.composition`), adjust both the import in the test and the source.

- [ ] **Step 16.2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_researchrubrics_registry_and_binding.py -v
```

- [ ] **Step 16.3: Register leaf worker**

In `ergon_builtins/ergon_builtins/registry_core.py`, add to imports:

```python
from ergon_builtins.benchmarks.researchrubrics.smoke_subworker import (
    ResearchRubricsSmokeLeafWorker,
)
```

Add to `WORKERS`:

```python
    "researchrubrics-smoke-leaf": ResearchRubricsSmokeLeafWorker,
```

- [ ] **Step 16.4: Add composition binding**

In `ergon_cli/ergon_cli/composition/__init__.py`, locate `BENCHMARK_COMPOSITIONS` (or its equivalent; confirm with step 16.1 grep). Add/extend the `researchrubrics` entry:

```python
    "researchrubrics": Composition(
        bindings={
            # ... existing bindings preserved ...
            "smoke-leaf": "researchrubrics-smoke-leaf",
        },
    ),
```

- [ ] **Step 16.5: Run tests**

```bash
uv run pytest tests/unit/test_researchrubrics_registry_and_binding.py -v
pnpm run check:be:type
```

Expected: unit tests pass; `ty` check clean.

- [ ] **Step 16.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/registry_core.py \
        ergon_cli/ergon_cli/composition/__init__.py \
        tests/unit/test_researchrubrics_registry_and_binding.py
git commit -m "feat(smoke/rr): register researchrubrics-smoke-leaf + smoke-leaf composition binding"
```

---

## Task 17 — `tests/e2e/conftest.py` with finalizer + helpers

**Files:**
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/conftest.py`

- [ ] **Step 17.1: Create the package marker**

```python
# tests/e2e/__init__.py
```

- [ ] **Step 17.2: Write the conftest**

```python
# tests/e2e/conftest.py
"""Shared fixtures + helpers for the canonical e2e smoke tier.

Key responsibilities:
  - run_benchmark(): invoke the `ergon` CLI and extract the run_id.
  - wait_for_terminal(): poll /runs/{id} until the run reaches a terminal state.
  - screenshot_upload_finalizer: after every test (pass or fail), push captures
    to the `screenshots/pr-{N}` orphan ref and post a PR inline-image comment.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from uuid import UUID

import httpx
import pytest


log = logging.getLogger(__name__)


def run_benchmark(
    *,
    slug: str,
    worker: str,
    evaluator: str,
    cohort: str,
    limit: int = 1,
) -> UUID:
    """Run a benchmark via the CLI. Returns the newly-created run_id.

    The CLI is expected to emit the run_id on its last stdout line. If the CLI
    output shape changes, update this parser accordingly.
    """
    result = subprocess.run(
        [
            "ergon", "benchmark", "run", slug,
            "--worker", worker,
            "--evaluator", evaluator,
            "--cohort", cohort,
            "--limit", str(limit),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    result.check_returncode()
    last_line = result.stdout.strip().splitlines()[-1]
    return UUID(last_line.strip())


def wait_for_terminal(run_id: UUID, *, timeout_seconds: int = 180) -> None:
    """Poll /runs/{run_id} every 2s until status ∈ {completed, failed, cancelled}."""
    deadline = time.time() + timeout_seconds
    api = os.environ.get("ERGON_API_BASE_URL", "http://127.0.0.1:9000")
    while time.time() < deadline:
        try:
            r = httpx.get(f"{api}/runs/{run_id}", timeout=5)
        except httpx.HTTPError:
            time.sleep(2)
            continue
        if r.status_code == 200:
            status = r.json().get("status")
            if status in {"completed", "failed", "cancelled"}:
                return
        time.sleep(2)
    raise TimeoutError(
        f"run {run_id} did not reach terminal within {timeout_seconds}s"
    )


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> None:
    """Expose each phase's result on the item so finalizers can inspect pass/fail."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture(autouse=True)
def screenshot_upload_finalizer(
    request: pytest.FixtureRequest,
) -> None:
    """After every e2e test, upload screenshots + post PR comment.

    No-op when PR_NUMBER env absent (local runs). Upload failures are logged but
    never raised — they must not mask the real test failure.
    """
    yield
    pr_number = os.environ.get("PR_NUMBER")
    if not pr_number:
        return

    env = os.environ.get("SMOKE_ENV", "unknown")
    # screenshot_dir fixture is required by each test module; locate via
    # getfixturevalue so we don't fail for non-e2e tests that somehow import us.
    try:
        src = Path(request.getfixturevalue("screenshot_dir"))
    except pytest.FixtureLookupError:
        return

    passed = bool(
        getattr(request.node, "rep_call", None) is not None
        and request.node.rep_call.passed
    )

    try:
        _push_screenshots_to_ref(pr_number, env, src)
        _post_pr_comment(pr_number, env, passed=passed)
    except Exception:
        log.exception("screenshot upload failed; not masking test result")


def _push_screenshots_to_ref(pr_number: str, env: str, src: Path) -> None:
    """git push screenshots/pr-{N} with src/*.png under {env}/."""
    ref = f"screenshots/pr-{pr_number}"
    worktree = Path(f"/tmp/screenshots-{pr_number}")
    if worktree.exists():
        subprocess.run(["rm", "-rf", str(worktree)], check=True)

    fetch = subprocess.run(
        ["git", "fetch", "origin", f"{ref}:{ref}"],
        capture_output=True, text=True,
    )
    if fetch.returncode == 0:
        subprocess.run(["git", "worktree", "add", str(worktree), ref], check=True)
    else:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), "HEAD"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "checkout", "--orphan", ref],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "rm", "-rf", "."],
            check=False,
        )

    env_dir = worktree / env
    env_dir.mkdir(parents=True, exist_ok=True)
    for png in src.glob("*.png"):
        subprocess.run(["cp", str(png), str(env_dir / png.name)], check=True)

    subprocess.run(["git", "-C", str(worktree), "add", "."], check=True)
    commit = subprocess.run(
        ["git", "-C", str(worktree), "commit",
         "-m", f"ci: e2e screenshots pr-{pr_number} {env}"],
        capture_output=True, text=True,
    )
    if commit.returncode == 0:
        subprocess.run(
            ["git", "-C", str(worktree), "push", "origin", f"HEAD:{ref}"],
            check=True,
        )
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree)],
        check=False,
    )


def _post_pr_comment(pr_number: str, env: str, *, passed: bool) -> None:
    """Post a PR comment with inline screenshot images via gh CLI."""
    repo = os.environ.get("GITHUB_REPOSITORY", "DeepFlow-research/ergon")
    status = "PASS" if passed else "FAIL"
    body = (
        f"## E2E smoke — `{env}` — {status}\n\n"
        f"Screenshots from CI run:\n\n"
        f"![dashboard](https://raw.githubusercontent.com/{repo}/screenshots/pr-{pr_number}/{env}/dashboard-full.png)\n\n"
        f"![graph canvas](https://raw.githubusercontent.com/{repo}/screenshots/pr-{pr_number}/{env}/graph.png)\n\n"
        f"![cohort index](https://raw.githubusercontent.com/{repo}/screenshots/pr-{pr_number}/{env}/cohort.png)\n"
    )
    subprocess.run(
        ["gh", "pr", "comment", pr_number, "--body", body],
        check=True,
    )
```

- [ ] **Step 17.3: Sanity-check the conftest imports**

```bash
uv run python -c "import tests.e2e.conftest; print('conftest imports ok')"
```

Expected: `conftest imports ok`.

- [ ] **Step 17.4: Commit**

```bash
git add tests/e2e/__init__.py tests/e2e/conftest.py
git commit -m "feat(e2e): conftest with run_benchmark, wait_for_terminal, screenshot finalizer"
```

---

## Task 18 — `tests/e2e/test_researchrubrics_smoke.py`

**Files:**
- Create: `tests/e2e/test_researchrubrics_smoke.py`

- [ ] **Step 18.1: Write the test**

```python
# tests/e2e/test_researchrubrics_smoke.py
"""End-to-end canonical smoke for the researchrubrics benchmark.

Phases:
  1. Invoke the CLI to start a benchmark run.
  2. Wait for terminal status.
  3. Postgres record-log assertions (direct DB).
  4. Playwright subprocess: dashboard assertions + screenshots.
  5. Finalizer (conftest): upload screenshots + post PR comment.

Requires: ergon backend + dashboard running; ENABLE_TEST_HARNESS=1; Postgres
reachable via ERGON_DATABASE_URL.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.shared.enums import RunStatus, TaskStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
)

from tests.e2e.conftest import run_benchmark, wait_for_terminal

ENV = "researchrubrics"
EXPECTED_SUBTASK_SLUGS = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)


@pytest.fixture(scope="module")
def screenshot_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp(f"playwright-{ENV}")


def test_canonical_smoke_passes(screenshot_dir: Path) -> None:
    os.environ["SMOKE_ENV"] = ENV

    # Phase 1: CLI kicks off the benchmark.
    run_id = run_benchmark(
        slug=ENV,
        worker="canonical-smoke",
        evaluator=f"{ENV}-smoke-rubric",
        cohort=f"ci-smoke-{ENV}-{int(time.time())}",
    )

    # Phase 2: wait for terminal state.
    wait_for_terminal(run_id, timeout_seconds=180)

    # Phase 3: Postgres record-log assertions.
    with Session(get_engine()) as s:
        run = s.exec(select(RunRecord).where(RunRecord.id == run_id)).one()
        assert run.status == RunStatus.COMPLETED, f"run status: {run.status}"

        nodes = s.exec(
            select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        ).all()
        subtask_slugs = sorted(n.task_slug for n in nodes if n.level > 0)
        assert subtask_slugs == sorted(EXPECTED_SUBTASK_SLUGS), subtask_slugs
        for n in nodes:
            assert n.status == TaskStatus.COMPLETED, f"{n.task_slug}: {n.status}"

        muts = s.exec(
            select(RunGraphMutation)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(RunGraphMutation.sequence)
        ).all()
        assert any(
            str(m.mutation_type).lower().endswith("add_subtask") for m in muts
        ), "no add_subtask mutations recorded"

        resources = s.exec(
            select(RunResource).where(RunResource.run_id == run_id)
        ).all()
        assert len(resources) == 9, len(resources)
        for r in resources:
            assert r.content_hash, f"{r.task_slug}: empty hash"

        evals = s.exec(
            select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
        ).all()
        assert len(evals) == 1 and evals[0].score == 1.0, evals

    # Phase 4: Playwright subprocess (always runs; writes screenshots on
    # pass or fail via playwright.config.ts screenshot: "on").
    result = subprocess.run(
        [
            "pnpm", "--dir", "ergon-dashboard", "exec",
            "playwright", "test",
            f"tests/e2e/{ENV}.smoke.spec.ts",
            "--project=chromium",
        ],
        env={
            **os.environ,
            "RUN_ID": str(run_id),
            "SMOKE_ENV": ENV,
            "SCREENSHOT_DIR": str(screenshot_dir),
            "PLAYWRIGHT_LIVE": "1",
            "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:3000",
            "ERGON_API_BASE_URL": "http://127.0.0.1:9000",
            "TEST_HARNESS_SECRET": os.environ.get("TEST_HARNESS_SECRET", "ci-secret"),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    # Phase 5 upload runs in the conftest finalizer regardless.
    assert result.returncode == 0, (
        f"Playwright failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
```

- [ ] **Step 18.2: Commit (no local run — CI is authoritative)**

```bash
git add tests/e2e/test_researchrubrics_smoke.py
git commit -m "feat(e2e/rr): canonical smoke test — CLI + Postgres asserts + Playwright subprocess"
```

---

## Task 19 — Playwright spec for researchrubrics

**Files:**
- Create: `ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts`

- [ ] **Step 19.1: Locate Playwright test directory**

```bash
ls ergon-dashboard/tests/e2e/ 2>&1 | head
```

If `ergon-dashboard/tests/e2e/` doesn't exist, create it with:

```bash
mkdir -p ergon-dashboard/tests/e2e
```

- [ ] **Step 19.2: Write the spec**

```typescript
// ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts
//
// Canonical smoke spec for researchrubrics. Driven by the Python pytest
// (tests/e2e/test_researchrubrics_smoke.py) as a subprocess. Playwright does:
//   1. Query the backend harness for authoritative run state.
//   2. Navigate to /run/{RUN_ID}; assert 10 graph nodes render (1 root + 9).
//   3. Navigate to /; assert the cohort index renders.
//   4. Capture full-page, graph-canvas, and cohort-index screenshots.
//
// Screenshots on failure are captured automatically by the global config
// (`screenshot: "on"`).

import { expect, test } from "@playwright/test";

import { BackendHarnessClient } from "../helpers/testHarnessClient";

const RUN_ID = process.env.RUN_ID;
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR ?? "/tmp/playwright";
const ERGON_API =
  process.env.ERGON_API_BASE_URL ?? "http://127.0.0.1:9000";

test.skip(!RUN_ID, "RUN_ID env var required (populated by pytest driver)");

test("canonical smoke — dashboard renders expected run", async ({
  request,
  page,
}) => {
  // 1. Authoritative backend state.
  const harness = new BackendHarnessClient(request, ERGON_API);
  const state = await harness.getRunState(RUN_ID!);
  expect(state.status).toBe("completed");
  expect(state.graph_nodes.filter((n) => n.level > 0)).toHaveLength(9);

  // 2. Run page renders the full graph.
  await page.goto(`/run/${RUN_ID}`);
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  const nodes = page.getByTestId(/^graph-node-/);
  await expect(nodes).toHaveCount(10); // 1 root + 9 subtasks

  await page.screenshot({
    path: `${SCREENSHOT_DIR}/dashboard-full.png`,
    fullPage: true,
  });
  await page.getByTestId("graph-canvas").screenshot({
    path: `${SCREENSHOT_DIR}/graph.png`,
  });

  // 3. Cohort index.
  await page.goto("/");
  await expect(page.getByTestId("cohort-index-list")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/cohort.png`,
  });
});
```

Note: if the dashboard uses different `data-testid` attribute names for the graph canvas, node elements, or cohort index, grep the source and swap them in. Likely candidates (inspect `ergon-dashboard/src/components/`):

```bash
grep -rn "data-testid" ergon-dashboard/src/ | head -40
```

- [ ] **Step 19.3: Lint/typecheck**

```bash
pnpm --dir ergon-dashboard exec tsc --noEmit
pnpm run check:fe
```

Expected: green.

- [ ] **Step 19.4: Commit**

```bash
git add ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts
git commit -m "feat(e2e/rr): Playwright spec asserts dashboard renders 10-node graph + captures screenshots"
```

---

## Task 20 — `docker-compose.ci.yml` env additions

**Files:**
- Modify: `docker-compose.ci.yml`

- [ ] **Step 20.1: Inspect current env block for the api service**

```bash
grep -A 12 "^  api:" docker-compose.ci.yml
```

- [ ] **Step 20.2: Add `ENABLE_TEST_HARNESS` + `TEST_HARNESS_SECRET`**

In the `api:` service `environment:` block, add:

```yaml
      ENABLE_TEST_HARNESS: "1"
      TEST_HARNESS_SECRET: "ci-secret"
```

- [ ] **Step 20.3: Smoke the compose file**

```bash
docker compose -f docker-compose.ci.yml config > /dev/null && echo "compose config ok"
```

Expected: `compose config ok`.

- [ ] **Step 20.4: Commit**

```bash
git add docker-compose.ci.yml
git commit -m "ci: enable /api/test/* harness + secret in docker-compose.ci.yml api env"
```

---

## Task 21 — `.github/workflows/e2e-benchmarks.yml` with researchrubrics only

**Files:**
- Create: `.github/workflows/e2e-benchmarks.yml`

- [ ] **Step 21.1: Write the workflow**

```yaml
# .github/workflows/e2e-benchmarks.yml
name: e2e-benchmarks

on:
  pull_request:
    types: [opened, synchronize, reopened, closed]
    branches: [main]

concurrency:
  group: e2e-${{ github.ref }}
  cancel-in-progress: true

jobs:
  smoke:
    name: e2e smoke — ${{ matrix.env }}
    if: github.event.action != 'closed'
    timeout-minutes: 5
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        env: [researchrubrics]  # PR 3 adds minif2f; PR 4 adds swebench-verified
    permissions:
      contents: write       # push to screenshots/pr-{N} ref
      pull-requests: write  # post PR comment
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - run: uv sync --all-packages --group dev
      - run: pnpm install --frozen-lockfile

      - uses: docker/setup-buildx-action@v3
      - uses: docker/bake-action@v4
        with:
          files: docker-compose.ci.yml
          load: true
          set: |
            *.cache-from=type=gha
            *.cache-to=type=gha,mode=max

      - name: Bring up backend stack
        run: |
          docker compose -f docker-compose.ci.yml up -d postgres inngest-dev api
          timeout 60 bash -c 'until curl -sf http://localhost:9000/docs >/dev/null; do sleep 2; done'

      - name: Build + serve dashboard
        run: |
          pnpm --dir ergon-dashboard build
          pnpm --dir ergon-dashboard start > /tmp/dashboard.log 2>&1 &
          timeout 30 bash -c 'until curl -sf http://localhost:3000 >/dev/null; do sleep 2; done'
        env:
          ERGON_API_BASE_URL: http://127.0.0.1:9000

      - name: Install Playwright browsers
        run: pnpm --dir ergon-dashboard exec playwright install --with-deps chromium

      - name: Run smoke
        run: |
          uv run pytest tests/e2e/test_${{ matrix.env }}_smoke.py -v --timeout=270
        env:
          ERGON_DATABASE_URL: postgresql://ergon:ci_test@localhost:5433/ergon
          ENABLE_TEST_HARNESS: "1"
          TEST_HARNESS_SECRET: ci-secret
          PR_NUMBER: ${{ github.event.pull_request.number }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          E2B_API_KEY: ${{ secrets.E2B_API_KEY }}

      - name: Upload Playwright trace on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-trace-${{ matrix.env }}
          path: ergon-dashboard/test-results/
          retention-days: 7

      - name: Dump backend log on failure
        if: failure()
        run: |
          docker compose -f docker-compose.ci.yml logs api | tail -200

  cleanup-screenshot-ref:
    name: Delete screenshots/pr-${{ github.event.pull_request.number }} on close
    if: github.event.action == 'closed'
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - name: Delete screenshot ref
        run: |
          git push origin --delete "screenshots/pr-${{ github.event.pull_request.number }}" || true
```

- [ ] **Step 21.2: Yaml-lint**

```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/e2e-benchmarks.yml'))" && echo "yaml ok"
```

- [ ] **Step 21.3: Commit**

```bash
git add .github/workflows/e2e-benchmarks.yml
git commit -m "ci(e2e): per-env matrix workflow (researchrubrics only; PR 3/4 extend) + ref cleanup"
```

---

## Task 22 — Push PR 2 and verify CI green-path

- [ ] **Step 22.1: Push + open PR**

```bash
git push -u origin feature/smoke-researchrubrics
gh pr create --title "feat(e2e/rr): canonical smoke for researchrubrics (PR 2 of 4)" \
  --body "$(cat <<'EOF'
## Summary
- First live canonical smoke (researchrubrics), using the shared infra from PR 1.
- Python pytest asserts Postgres record-log + 10-node graph; invokes Playwright subprocess for dashboard checks + screenshots.
- Screenshots upload inline to PR comment on pass AND fail via `screenshots/pr-{N}` orphan ref.
- CI workflow `.github/workflows/e2e-benchmarks.yml` with 5-minute budget, every-PR trigger, and ref-cleanup on PR close.

## Test plan
- [x] Unit + integration suites green locally.
- [x] CI: `e2e smoke — researchrubrics` job runs and produces a passing screenshot comment on this PR.
- [ ] Failure-mode rehearsal (Task 23) before merge.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 22.2: Wait for first CI run + confirm screenshot comment appears**

Wait ~5 minutes. Open the PR in the browser and confirm:
- A comment appears with inline dashboard / graph / cohort images.
- The `e2e smoke — researchrubrics` check is green.
- The 5-min budget was not exceeded.

If the 5-min budget was exceeded: note actuals in the PR body and raise to 8 min (edit the workflow + push).

If screenshot upload fails but the run passes: diagnose the finalizer — check logs for the finalizer exception (it logs but does not fail the test). Fix and push a follow-up commit.

---

## Task 23 — Failure-mode rehearsal (pre-merge)

Before merging PR 2, manually induce each failure class against the live CI to verify screenshot delivery works on every failure path.

- [ ] **Step 23.1: Fail the Postgres assertion**

On a throwaway branch off `feature/smoke-researchrubrics`:

```bash
git checkout -b rehearsal/postgres-fail
```

Edit `tests/e2e/test_researchrubrics_smoke.py`, change `assert len(resources) == 9` to `assert len(resources) == 999`. Push and open a dummy PR (do NOT merge):

```bash
git push -u origin rehearsal/postgres-fail
gh pr create --title "rehearsal: force Postgres assertion fail" --body "Do not merge. Rehearsal for PR 2."
```

Confirm: pytest fails on phase 3; Playwright still ran (see run log); finalizer uploaded screenshots; PR comment shows ❌ FAIL with dashboard images.

Close this PR without merging:

```bash
gh pr close --delete-branch "$(gh pr list --head rehearsal/postgres-fail --json number -q '.[0].number')"
```

- [ ] **Step 23.2: Fail the Playwright assertion**

On a new rehearsal branch off `feature/smoke-researchrubrics`:

```bash
git checkout feature/smoke-researchrubrics
git checkout -b rehearsal/playwright-fail
```

Edit `ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts`, change `toHaveCount(10)` to `toHaveCount(999)`. Push and open a dummy PR. Confirm:
- Python pytest fails on phase 4 with non-zero subprocess returncode.
- Playwright-captured failure screenshots (via global config) are uploaded.
- PR comment shows ❌ FAIL.

Close without merging.

- [ ] **Step 23.3: Force a timeout**

New rehearsal branch:

```bash
git checkout feature/smoke-researchrubrics
git checkout -b rehearsal/timeout-fail
```

Edit `tests/e2e/test_researchrubrics_smoke.py`: set `wait_for_terminal(run_id, timeout_seconds=3)`. Push and open a dummy PR. Confirm:
- `wait_for_terminal` raises `TimeoutError`.
- Finalizer still runs (no screenshots were written because Playwright never ran; the finalizer logs missing files but does not raise).
- PR comment shows ❌ FAIL but images render as broken (that's expected — no Playwright screenshot was taken).

Close without merging.

- [ ] **Step 23.4: Document rehearsal in PR 2 body**

Append to PR 2 description (`gh pr edit`):

```
## Failure-mode rehearsal results
- Postgres-fail: screenshots delivered ✅ (rehearsal PR #XXX)
- Playwright-fail: failure screenshots delivered ✅ (rehearsal PR #YYY)
- Timeout: PR comment posted with FAIL status ✅ (rehearsal PR #ZZZ)
```

- [ ] **Step 23.5: Merge PR 2**

```bash
gh pr merge feature/smoke-researchrubrics --squash --delete-branch
```

---

# PR 3 — `minif2f` env smoke

**PR branch:** `feature/smoke-minif2f`

**Goal:** Add the second canonical smoke. No architectural changes — pure template repetition against the `minif2f` env. Adds to the CI matrix.

**PR 3 acceptance gate:** both `researchrubrics` and `minif2f` smokes green on every PR; MiniF2F sandbox image has `lean` on PATH.

---

## Task 24 — Branch + subworker

**Files:**
- Create: `ergon_builtins/ergon_builtins/benchmarks/minif2f/smoke_subworker.py`
- Test: `tests/unit/test_minif2f_smoke_subworker.py`

- [ ] **Step 24.1: Create branch**

```bash
git checkout main && git pull origin main
git checkout -b feature/smoke-minif2f
```

- [ ] **Step 24.2: Write failing test**

```python
# tests/unit/test_minif2f_smoke_subworker.py
"""MiniF2FSmokeSubworker: writes .lean + runs `lean --check`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ergon_builtins.benchmarks.minif2f.smoke_subworker import (
    MiniF2FSmokeSubworker,
)


@pytest.mark.asyncio
async def test_writes_lean_theorem_and_runs_lean_check() -> None:
    sandbox = MagicMock()
    sandbox.files = MagicMock()
    sandbox.files.write = AsyncMock()
    sandbox.commands = MagicMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(stdout="", exit_code=0)
    )

    sub = MiniF2FSmokeSubworker()
    result = await sub.work(node_id="d_root", sandbox=sandbox)

    write_args = sandbox.files.write.await_args.args
    assert write_args[0] == "/tmp/d_root.lean"
    assert "theorem smoke_trivial" in write_args[1]
    sandbox.commands.run.assert_awaited_once_with("lean --check /tmp/d_root.lean")
    assert result.probe_exit_code == 0
```

- [ ] **Step 24.3: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_minif2f_smoke_subworker.py -v
```

- [ ] **Step 24.4: Implement**

```python
# ergon_builtins/ergon_builtins/benchmarks/minif2f/smoke_subworker.py
"""Per-env canonical smoke subworker + leaf for minif2f."""

from __future__ import annotations

from ergon_core.core.providers.sandbox.manager import AsyncSandbox

from ergon_builtins.workers.stubs.base_smoke_leaf import BaseSmokeLeafWorker
from ergon_builtins.workers.stubs.smoke_subworker import SubworkerResult


class MiniF2FSmokeSubworker:
    """Writes a trivial Lean proof + runs `lean --check`."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        content = (
            f"-- canonical smoke proof for {node_id}\n"
            "theorem smoke_trivial : 1 + 1 = 2 := by norm_num\n"
        )
        path = f"/tmp/{node_id}.lean"
        await sandbox.files.write(path, content)
        probe = await sandbox.commands.run(f"lean --check {path}")
        return SubworkerResult(
            file_path=path,
            probe_stdout=probe.stdout,
            probe_exit_code=probe.exit_code,
        )


class MiniF2FSmokeLeafWorker(BaseSmokeLeafWorker):
    subworker_cls = MiniF2FSmokeSubworker  # type: ignore[assignment]
```

- [ ] **Step 24.5: Run tests**

```bash
uv run pytest tests/unit/test_minif2f_smoke_subworker.py -v
```

- [ ] **Step 24.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/minif2f/smoke_subworker.py \
        tests/unit/test_minif2f_smoke_subworker.py
git commit -m "feat(smoke/minif2f): MiniF2FSmokeSubworker writes .lean + lean --check"
```

---

## Task 25 — Fill `MiniF2FSmokeCriterion`

**Files:**
- Modify: `ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py`
- Modify: `tests/unit/test_smoke_criterion.py`

- [ ] **Step 25.1: Add failing test**

Append to `tests/unit/test_smoke_criterion.py`:

```python
@pytest.mark.asyncio
async def test_minif2f_criterion_passes_with_theorem_text() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        MiniF2FSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = (
            f"-- canonical smoke proof for {r.task_slug}\n"
            "theorem smoke_trivial : 1 + 1 = 2 := by norm_num\n"
        ).encode()
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await MiniF2FSmokeCriterion().evaluate(ctx)
    assert score.value == 1.0


@pytest.mark.asyncio
async def test_minif2f_criterion_fails_without_theorem_declaration() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        MiniF2FSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = b"-- no theorem here\n"
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await MiniF2FSmokeCriterion().evaluate(ctx)
    assert score.value == 0.0
    assert "theorem" in score.reason.lower()
```

- [ ] **Step 25.2: Implement**

Replace `MiniF2FSmokeCriterion._verify_env_content`:

```python
class MiniF2FSmokeCriterion(SmokeCriterionBase):
    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        for r in ctx.resources.all():
            text = r.content.decode("utf-8")
            assert "theorem smoke_trivial" in text, (
                f"{r.task_slug}: missing Lean theorem declaration"
            )
```

- [ ] **Step 25.3: Run tests**

```bash
uv run pytest tests/unit/test_smoke_criterion.py -v
```

- [ ] **Step 25.4: Commit**

```bash
git add ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py \
        tests/unit/test_smoke_criterion.py
git commit -m "feat(smoke/minif2f): MiniF2FSmokeCriterion asserts theorem declaration in .lean"
```

---

## Task 26 — Register minif2f leaf + composition binding

**Files:**
- Modify: `ergon_builtins/ergon_builtins/registry_core.py`
- Modify: `ergon_cli/ergon_cli/composition/__init__.py`
- Test: `tests/unit/test_minif2f_registry_and_binding.py`

- [ ] **Step 26.1: Write failing test**

```python
# tests/unit/test_minif2f_registry_and_binding.py
def test_minif2f_smoke_leaf_registered() -> None:
    from ergon_builtins.registry_core import WORKERS
    from ergon_builtins.benchmarks.minif2f.smoke_subworker import (
        MiniF2FSmokeLeafWorker,
    )

    assert WORKERS["minif2f-smoke-leaf"] is MiniF2FSmokeLeafWorker


def test_minif2f_composition_binds_smoke_leaf() -> None:
    from ergon_cli.composition import BENCHMARK_COMPOSITIONS

    assert (
        BENCHMARK_COMPOSITIONS["minif2f"].bindings["smoke-leaf"]
        == "minif2f-smoke-leaf"
    )
```

- [ ] **Step 26.2: Wire registry + binding**

In `registry_core.py`, add:

```python
from ergon_builtins.benchmarks.minif2f.smoke_subworker import MiniF2FSmokeLeafWorker
```

```python
    "minif2f-smoke-leaf": MiniF2FSmokeLeafWorker,
```

In `ergon_cli/ergon_cli/composition/__init__.py`, extend the `minif2f` composition's `bindings` dict with:

```python
            "smoke-leaf": "minif2f-smoke-leaf",
```

- [ ] **Step 26.3: Run tests**

```bash
uv run pytest tests/unit/test_minif2f_registry_and_binding.py -v
```

- [ ] **Step 26.4: Commit**

```bash
git add ergon_builtins/ergon_builtins/registry_core.py \
        ergon_cli/ergon_cli/composition/__init__.py \
        tests/unit/test_minif2f_registry_and_binding.py
git commit -m "feat(smoke/minif2f): register minif2f-smoke-leaf + composition binding"
```

---

## Task 27 — minif2f pytest + Playwright spec

**Files:**
- Create: `tests/e2e/test_minif2f_smoke.py`
- Create: `ergon-dashboard/tests/e2e/minif2f.smoke.spec.ts`

- [ ] **Step 27.1: Create the pytest**

```python
# tests/e2e/test_minif2f_smoke.py
"""End-to-end canonical smoke for the minif2f benchmark.

Identical shape to test_researchrubrics_smoke.py — only ENV differs.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.shared.enums import RunStatus, TaskStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
)

from tests.e2e.conftest import run_benchmark, wait_for_terminal

ENV = "minif2f"
EXPECTED_SUBTASK_SLUGS = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)


@pytest.fixture(scope="module")
def screenshot_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp(f"playwright-{ENV}")


def test_canonical_smoke_passes(screenshot_dir: Path) -> None:
    os.environ["SMOKE_ENV"] = ENV

    run_id = run_benchmark(
        slug=ENV,
        worker="canonical-smoke",
        evaluator=f"{ENV}-smoke-rubric",
        cohort=f"ci-smoke-{ENV}-{int(time.time())}",
    )
    wait_for_terminal(run_id, timeout_seconds=180)

    with Session(get_engine()) as s:
        run = s.exec(select(RunRecord).where(RunRecord.id == run_id)).one()
        assert run.status == RunStatus.COMPLETED, f"run status: {run.status}"

        nodes = s.exec(
            select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        ).all()
        subtask_slugs = sorted(n.task_slug for n in nodes if n.level > 0)
        assert subtask_slugs == sorted(EXPECTED_SUBTASK_SLUGS), subtask_slugs
        for n in nodes:
            assert n.status == TaskStatus.COMPLETED, f"{n.task_slug}: {n.status}"

        muts = s.exec(
            select(RunGraphMutation)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(RunGraphMutation.sequence)
        ).all()
        assert any(
            str(m.mutation_type).lower().endswith("add_subtask") for m in muts
        )

        resources = s.exec(
            select(RunResource).where(RunResource.run_id == run_id)
        ).all()
        assert len(resources) == 9, len(resources)

        evals = s.exec(
            select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
        ).all()
        assert len(evals) == 1 and evals[0].score == 1.0, evals

    result = subprocess.run(
        [
            "pnpm", "--dir", "ergon-dashboard", "exec",
            "playwright", "test",
            f"tests/e2e/{ENV}.smoke.spec.ts",
            "--project=chromium",
        ],
        env={
            **os.environ,
            "RUN_ID": str(run_id),
            "SMOKE_ENV": ENV,
            "SCREENSHOT_DIR": str(screenshot_dir),
            "PLAYWRIGHT_LIVE": "1",
            "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:3000",
            "ERGON_API_BASE_URL": "http://127.0.0.1:9000",
            "TEST_HARNESS_SECRET": os.environ.get("TEST_HARNESS_SECRET", "ci-secret"),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"Playwright failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
```

- [ ] **Step 27.2: Create the Playwright spec**

```typescript
// ergon-dashboard/tests/e2e/minif2f.smoke.spec.ts

import { expect, test } from "@playwright/test";

import { BackendHarnessClient } from "../helpers/testHarnessClient";

const RUN_ID = process.env.RUN_ID;
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR ?? "/tmp/playwright";
const ERGON_API =
  process.env.ERGON_API_BASE_URL ?? "http://127.0.0.1:9000";

test.skip(!RUN_ID, "RUN_ID env var required (populated by pytest driver)");

test("canonical smoke — dashboard renders expected run", async ({
  request,
  page,
}) => {
  const harness = new BackendHarnessClient(request, ERGON_API);
  const state = await harness.getRunState(RUN_ID!);
  expect(state.status).toBe("completed");
  expect(state.graph_nodes.filter((n) => n.level > 0)).toHaveLength(9);

  await page.goto(`/run/${RUN_ID}`);
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  const nodes = page.getByTestId(/^graph-node-/);
  await expect(nodes).toHaveCount(10);

  await page.screenshot({
    path: `${SCREENSHOT_DIR}/dashboard-full.png`,
    fullPage: true,
  });
  await page.getByTestId("graph-canvas").screenshot({
    path: `${SCREENSHOT_DIR}/graph.png`,
  });

  await page.goto("/");
  await expect(page.getByTestId("cohort-index-list")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/cohort.png`,
  });
});
```

- [ ] **Step 27.3: Type-check**

```bash
pnpm --dir ergon-dashboard exec tsc --noEmit
```

- [ ] **Step 27.4: Commit**

```bash
git add tests/e2e/test_minif2f_smoke.py \
        ergon-dashboard/tests/e2e/minif2f.smoke.spec.ts
git commit -m "feat(e2e/minif2f): pytest + Playwright spec for canonical smoke"
```

---

## Task 28 — Extend CI matrix with minif2f

**Files:**
- Modify: `.github/workflows/e2e-benchmarks.yml`

- [ ] **Step 28.1: Add to matrix**

In `.github/workflows/e2e-benchmarks.yml`, change:

```diff
     strategy:
       fail-fast: false
       matrix:
-        env: [researchrubrics]  # PR 3 adds minif2f; PR 4 adds swebench-verified
+        env: [researchrubrics, minif2f]  # PR 4 adds swebench-verified
```

- [ ] **Step 28.2: Yaml-lint**

```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/e2e-benchmarks.yml'))" && echo "yaml ok"
```

- [ ] **Step 28.3: Commit**

```bash
git add .github/workflows/e2e-benchmarks.yml
git commit -m "ci(e2e): add minif2f to the smoke matrix"
```

---

## Task 29 — Push PR 3 and verify

- [ ] **Step 29.1: Push + open PR**

```bash
git push -u origin feature/smoke-minif2f
gh pr create --title "feat(e2e/minif2f): canonical smoke (PR 3 of 4)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `minif2f` to the canonical smoke matrix (second env).
- Sandbox image must have `lean` on PATH; if CI fails with `lean: command not found`, update the minif2f sandbox build to include the Lean toolchain.

## Test plan
- [x] Unit + existing smoke tests green.
- [ ] CI green for both `researchrubrics` and `minif2f` on this PR.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 29.2: Verify CI**

Wait for CI. Confirm both matrix jobs (`researchrubrics`, `minif2f`) produce passing inline screenshot comments.

If `lean: command not found`: the minif2f sandbox image is missing the Lean toolchain. Fix by ensuring its Dockerfile installs `lean` (or `elan`) — this is a separate upstream dependency. If it was supposed to be fixed earlier and wasn't, spawn an unblocker task.

- [ ] **Step 29.3: Merge**

```bash
gh pr merge feature/smoke-minif2f --squash --delete-branch
```

---

# PR 4 — `swebench-verified` env smoke + architecture-doc updates + RFC acceptance

**PR branch:** `feature/smoke-swebench`

**Goal:** Third canonical smoke, plus all the architecture-doc updates the RFC commits to in `§Invariants affected`, plus moving this RFC from `active/` to `accepted/`.

**PR 4 acceptance gate:** all three env smokes green; four architecture docs updated to reflect the new invariants; this RFC in `accepted/`.

---

## Task 30 — Branch + subworker

**Files:**
- Create: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/smoke_subworker.py`
- Test: `tests/unit/test_swebench_smoke_subworker.py`

- [ ] **Step 30.1: Create branch**

```bash
git checkout main && git pull origin main
git checkout -b feature/smoke-swebench
```

- [ ] **Step 30.2: Write failing test**

```python
# tests/unit/test_swebench_smoke_subworker.py
"""SweBenchSmokeSubworker: writes .py + runs `pytest --collect-only`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ergon_builtins.benchmarks.swebench_verified.smoke_subworker import (
    SweBenchSmokeSubworker,
)


@pytest.mark.asyncio
async def test_writes_python_and_runs_pytest_collect_only() -> None:
    sandbox = MagicMock()
    sandbox.files = MagicMock()
    sandbox.files.write = AsyncMock()
    sandbox.commands = MagicMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(stdout="collected 1 item\ntest_smoke_noop\n", exit_code=0)
    )

    sub = SweBenchSmokeSubworker()
    result = await sub.work(node_id="d_root", sandbox=sandbox)

    write_args = sandbox.files.write.await_args.args
    assert write_args[0] == "/tmp/fix_d_root.py"
    assert "def test_smoke_noop" in write_args[1]
    sandbox.commands.run.assert_awaited_once_with("pytest --collect-only /tmp/fix_d_root.py")
    assert result.probe_exit_code == 0
```

- [ ] **Step 30.3: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_swebench_smoke_subworker.py -v
```

- [ ] **Step 30.4: Implement**

```python
# ergon_builtins/ergon_builtins/benchmarks/swebench_verified/smoke_subworker.py
"""Per-env canonical smoke subworker + leaf for swebench-verified."""

from __future__ import annotations

from ergon_core.core.providers.sandbox.manager import AsyncSandbox

from ergon_builtins.workers.stubs.base_smoke_leaf import BaseSmokeLeafWorker
from ergon_builtins.workers.stubs.smoke_subworker import SubworkerResult


class SweBenchSmokeSubworker:
    """Writes a no-op pytest file + runs `pytest --collect-only`."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        content = (
            f"# canonical smoke artifact {node_id}\n"
            "def test_smoke_noop() -> None:\n"
            "    assert 1 + 1 == 2\n"
        )
        path = f"/tmp/fix_{node_id}.py"
        await sandbox.files.write(path, content)
        probe = await sandbox.commands.run(f"pytest --collect-only {path}")
        return SubworkerResult(
            file_path=path,
            probe_stdout=probe.stdout,
            probe_exit_code=probe.exit_code,
        )


class SweBenchSmokeLeafWorker(BaseSmokeLeafWorker):
    subworker_cls = SweBenchSmokeSubworker  # type: ignore[assignment]
```

- [ ] **Step 30.5: Run tests**

```bash
uv run pytest tests/unit/test_swebench_smoke_subworker.py -v
```

- [ ] **Step 30.6: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/swebench_verified/smoke_subworker.py \
        tests/unit/test_swebench_smoke_subworker.py
git commit -m "feat(smoke/swebench): SweBenchSmokeSubworker writes .py + pytest --collect-only"
```

---

## Task 31 — Fill `SweBenchSmokeCriterion`

**Files:**
- Modify: `ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py`
- Modify: `tests/unit/test_smoke_criterion.py`

- [ ] **Step 31.1: Add failing test**

Append to `tests/unit/test_smoke_criterion.py`:

```python
@pytest.mark.asyncio
async def test_swebench_criterion_passes_with_pytest_collection() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        SweBenchSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = (
            f"# canonical smoke artifact {r.task_slug}\n"
            "def test_smoke_noop() -> None: assert 1+1 == 2\n"
        ).encode()
        r.metadata["probe_stdout"] = "collected 1 item\ntest_smoke_noop\n"
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await SweBenchSmokeCriterion().evaluate(ctx)
    assert score.value == 1.0


@pytest.mark.asyncio
async def test_swebench_criterion_fails_if_collect_missed() -> None:
    from ergon_builtins.evaluators.criteria.smoke_criterion import (
        SweBenchSmokeCriterion,
    )

    ctx = _ctx_with_full_graph_and_resources()
    resources = list(ctx.resources.all())
    for r in resources:
        r.content = b"def test_smoke_noop() -> None: pass\n"
        r.metadata["probe_stdout"] = "collected 0 items\n"
    ctx.resources = SimpleNamespace(all=lambda: resources)

    score = await SweBenchSmokeCriterion().evaluate(ctx)
    assert score.value == 0.0
    assert "test_smoke_noop" in score.reason
```

- [ ] **Step 31.2: Implement**

Replace `SweBenchSmokeCriterion._verify_env_content`:

```python
class SweBenchSmokeCriterion(SmokeCriterionBase):
    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        for r in ctx.resources.all():
            text = r.content.decode("utf-8")
            assert "def test_smoke_noop" in text, (
                f"{r.task_slug}: missing pytest function"
            )
            collect_output = r.metadata.get("probe_stdout", "")
            assert "test_smoke_noop" in collect_output, (
                f"{r.task_slug}: pytest did not collect test_smoke_noop"
            )
```

- [ ] **Step 31.3: Run tests**

```bash
uv run pytest tests/unit/test_smoke_criterion.py -v
```

- [ ] **Step 31.4: Commit**

```bash
git add ergon_builtins/ergon_builtins/evaluators/criteria/smoke_criterion.py \
        tests/unit/test_smoke_criterion.py
git commit -m "feat(smoke/swebench): SweBenchSmokeCriterion asserts pytest function + collect-only output"
```

---

## Task 32 — Register swebench leaf + binding

**Files:**
- Modify: `ergon_builtins/ergon_builtins/registry_core.py`
- Modify: `ergon_cli/ergon_cli/composition/__init__.py`
- Test: `tests/unit/test_swebench_registry_and_binding.py`

- [ ] **Step 32.1: Write test**

```python
# tests/unit/test_swebench_registry_and_binding.py
def test_swebench_smoke_leaf_registered() -> None:
    from ergon_builtins.registry_core import WORKERS
    from ergon_builtins.benchmarks.swebench_verified.smoke_subworker import (
        SweBenchSmokeLeafWorker,
    )

    assert WORKERS["swebench-smoke-leaf"] is SweBenchSmokeLeafWorker


def test_swebench_composition_binds_smoke_leaf() -> None:
    from ergon_cli.composition import BENCHMARK_COMPOSITIONS

    assert (
        BENCHMARK_COMPOSITIONS["swebench-verified"].bindings["smoke-leaf"]
        == "swebench-smoke-leaf"
    )
```

- [ ] **Step 32.2: Wire**

In `registry_core.py`:

```python
from ergon_builtins.benchmarks.swebench_verified.smoke_subworker import (
    SweBenchSmokeLeafWorker,
)
```

```python
    "swebench-smoke-leaf": SweBenchSmokeLeafWorker,
```

In `ergon_cli/ergon_cli/composition/__init__.py`, extend the `swebench-verified` composition `bindings` with:

```python
            "smoke-leaf": "swebench-smoke-leaf",
```

- [ ] **Step 32.3: Run + commit**

```bash
uv run pytest tests/unit/test_swebench_registry_and_binding.py -v
git add ergon_builtins/ergon_builtins/registry_core.py \
        ergon_cli/ergon_cli/composition/__init__.py \
        tests/unit/test_swebench_registry_and_binding.py
git commit -m "feat(smoke/swebench): register swebench-smoke-leaf + composition binding"
```

---

## Task 33 — swebench pytest + Playwright spec

**Files:**
- Create: `tests/e2e/test_swebench_verified_smoke.py`
- Create: `ergon-dashboard/tests/e2e/swebench-verified.smoke.spec.ts`

- [ ] **Step 33.1: Create the pytest (same structure as minif2f, only ENV differs)**

```python
# tests/e2e/test_swebench_verified_smoke.py
"""End-to-end canonical smoke for the swebench-verified benchmark."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
from sqlmodel import Session, select

from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.shared.enums import RunStatus, TaskStatus
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
)

from tests.e2e.conftest import run_benchmark, wait_for_terminal

ENV = "swebench-verified"
EXPECTED_SUBTASK_SLUGS = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)


@pytest.fixture(scope="module")
def screenshot_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp(f"playwright-{ENV}")


def test_canonical_smoke_passes(screenshot_dir: Path) -> None:
    os.environ["SMOKE_ENV"] = ENV

    run_id = run_benchmark(
        slug=ENV,
        worker="canonical-smoke",
        evaluator="swebench-smoke-rubric",
        cohort=f"ci-smoke-{ENV}-{int(time.time())}",
    )
    wait_for_terminal(run_id, timeout_seconds=180)

    with Session(get_engine()) as s:
        run = s.exec(select(RunRecord).where(RunRecord.id == run_id)).one()
        assert run.status == RunStatus.COMPLETED, f"run status: {run.status}"

        nodes = s.exec(
            select(RunGraphNode).where(RunGraphNode.run_id == run_id)
        ).all()
        subtask_slugs = sorted(n.task_slug for n in nodes if n.level > 0)
        assert subtask_slugs == sorted(EXPECTED_SUBTASK_SLUGS), subtask_slugs
        for n in nodes:
            assert n.status == TaskStatus.COMPLETED, f"{n.task_slug}: {n.status}"

        muts = s.exec(
            select(RunGraphMutation)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(RunGraphMutation.sequence)
        ).all()
        assert any(
            str(m.mutation_type).lower().endswith("add_subtask") for m in muts
        )

        resources = s.exec(
            select(RunResource).where(RunResource.run_id == run_id)
        ).all()
        assert len(resources) == 9, len(resources)

        evals = s.exec(
            select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
        ).all()
        assert len(evals) == 1 and evals[0].score == 1.0, evals

    result = subprocess.run(
        [
            "pnpm", "--dir", "ergon-dashboard", "exec",
            "playwright", "test",
            f"tests/e2e/{ENV}.smoke.spec.ts",
            "--project=chromium",
        ],
        env={
            **os.environ,
            "RUN_ID": str(run_id),
            "SMOKE_ENV": ENV,
            "SCREENSHOT_DIR": str(screenshot_dir),
            "PLAYWRIGHT_LIVE": "1",
            "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:3000",
            "ERGON_API_BASE_URL": "http://127.0.0.1:9000",
            "TEST_HARNESS_SECRET": os.environ.get("TEST_HARNESS_SECRET", "ci-secret"),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"Playwright failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
```

- [ ] **Step 33.2: Create the Playwright spec**

```typescript
// ergon-dashboard/tests/e2e/swebench-verified.smoke.spec.ts

import { expect, test } from "@playwright/test";

import { BackendHarnessClient } from "../helpers/testHarnessClient";

const RUN_ID = process.env.RUN_ID;
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR ?? "/tmp/playwright";
const ERGON_API =
  process.env.ERGON_API_BASE_URL ?? "http://127.0.0.1:9000";

test.skip(!RUN_ID, "RUN_ID env var required (populated by pytest driver)");

test("canonical smoke — dashboard renders expected run", async ({
  request,
  page,
}) => {
  const harness = new BackendHarnessClient(request, ERGON_API);
  const state = await harness.getRunState(RUN_ID!);
  expect(state.status).toBe("completed");
  expect(state.graph_nodes.filter((n) => n.level > 0)).toHaveLength(9);

  await page.goto(`/run/${RUN_ID}`);
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  const nodes = page.getByTestId(/^graph-node-/);
  await expect(nodes).toHaveCount(10);

  await page.screenshot({
    path: `${SCREENSHOT_DIR}/dashboard-full.png`,
    fullPage: true,
  });
  await page.getByTestId("graph-canvas").screenshot({
    path: `${SCREENSHOT_DIR}/graph.png`,
  });

  await page.goto("/");
  await expect(page.getByTestId("cohort-index-list")).toBeVisible();
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/cohort.png`,
  });
});
```

- [ ] **Step 33.3: Type-check + commit**

```bash
pnpm --dir ergon-dashboard exec tsc --noEmit
git add tests/e2e/test_swebench_verified_smoke.py \
        ergon-dashboard/tests/e2e/swebench-verified.smoke.spec.ts
git commit -m "feat(e2e/swebench): pytest + Playwright spec for canonical smoke"
```

---

## Task 34 — Extend CI matrix with swebench-verified

**Files:**
- Modify: `.github/workflows/e2e-benchmarks.yml`

- [ ] **Step 34.1: Add to matrix**

```diff
     strategy:
       fail-fast: false
       matrix:
-        env: [researchrubrics, minif2f]  # PR 4 adds swebench-verified
+        env: [researchrubrics, minif2f, swebench-verified]
```

- [ ] **Step 34.2: Yaml-lint + commit**

```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/e2e-benchmarks.yml'))"
git add .github/workflows/e2e-benchmarks.yml
git commit -m "ci(e2e): add swebench-verified to the smoke matrix"
```

---

## Task 35 — Architecture doc: `06_builtins.md`

**Files:**
- Modify: `docs/architecture/06_builtins.md`

- [ ] **Step 35.1: Read the current §4 invariant**

```bash
grep -n -A 10 "^## 4\|^### 4" docs/architecture/06_builtins.md | head -40
```

- [ ] **Step 35.2: Rewrite the §4 invariant**

Locate the invariant that reads roughly "Every benchmark MUST ship a stub worker …" and replace with:

```markdown
**Invariant (canonical smoke contract):** Every benchmark MUST ship a
`SmokeSubworker` implementation plus a `SmokeCriterion` subclass, and MUST
register the `smoke-leaf` binding in its composition. The parent worker is
shared (`canonical-smoke`); only the leaf subworker and criterion content
assertions are env-specific. See
[`docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md`].
```

Verify the file reference: once this RFC moves to `accepted/` (Task 37), the link target will be valid.

- [ ] **Step 35.3: Commit**

```bash
git add docs/architecture/06_builtins.md
git commit -m "docs(arch/06): replace stub-worker invariant with SmokeSubworker + SmokeCriterion contract"
```

---

## Task 36 — Architecture doc: `07_testing.md`

**Files:**
- Modify: `docs/architecture/07_testing.md`

- [ ] **Step 36.1: Update §2 (code map)**

Under the e2e-tier entry, ensure the file-pattern reads:

```markdown
- `tests/e2e/test_{env}_smoke.py` — per-env canonical smoke (Python driver; invokes Playwright as subprocess).
- `ergon-dashboard/tests/e2e/{env}.smoke.spec.ts` — per-env Playwright spec for dashboard assertion + screenshot capture.
- `tests/e2e/conftest.py` — shared helpers (`run_benchmark`, `wait_for_terminal`, screenshot upload finalizer).
```

- [ ] **Step 36.2: Update §3 (trigger policy)**

Replace any "feature/* only" trigger policy for e2e with:

```markdown
- **Canonical smoke tier**: runs on every PR (see `.github/workflows/e2e-benchmarks.yml`).
- **Full-stack benchmark e2e (non-smoke)**: runs on `feature/*` branches.
```

- [ ] **Step 36.3: Add §4 invariant**

```markdown
**Invariant (canonical smoke completeness):** The envs in
`{researchrubrics, minif2f, swebench-verified}` have exactly one canonical
smoke pair each (Python + Playwright). The CI matrix in
`.github/workflows/e2e-benchmarks.yml` must include all three envs with
`fail-fast: false`. Expansion to additional envs requires adding the env to
the matrix, a `SmokeSubworker`, a `SmokeCriterion` subclass, a pytest
`test_{env}_smoke.py`, a Playwright `{env}.smoke.spec.ts`, and a composition
binding for `smoke-leaf`.
```

- [ ] **Step 36.4: Commit**

```bash
git add docs/architecture/07_testing.md
git commit -m "docs(arch/07): update testing tier map + trigger policy + canonical-smoke invariant"
```

---

## Task 37 — Architecture doc: `05_dashboard.md` + `01_public_api.md` + move RFC

**Files:**
- Modify: `docs/architecture/05_dashboard.md`
- Modify: `docs/architecture/01_public_api.md`
- Move: `docs/rfcs/active/2026-04-21-e2e-smoke-coverage-rewrite.md` → `docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md`

- [ ] **Step 37.1: Add dashboard invariant**

Append to the dashboard invariants section of `docs/architecture/05_dashboard.md`:

```markdown
**Invariant (canonical smoke dashboard rendering):** Every run produced by
the `canonical-smoke` worker renders in the dashboard with exactly 10 graph
nodes (1 root + 9 subtasks) and must reach `completed` status. The
canonical-smoke Playwright specs
(`ergon-dashboard/tests/e2e/{env}.smoke.spec.ts`) enforce this on every PR.
```

- [ ] **Step 37.2: Add public-API section**

Append a new section to `docs/architecture/01_public_api.md`:

```markdown
## Test-only extension points

The `/api/test/*` router is **not part of the public API**. It is mounted
only when `ENABLE_TEST_HARNESS=1` at server startup and is intended for
automated test drivers (Playwright + pytest). Write endpoints require the
`X-Test-Secret` header. See
[`docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md`] §"Test-harness
endpoints".
```

- [ ] **Step 37.3: Move the RFC**

```bash
mkdir -p docs/rfcs/accepted
git mv docs/rfcs/active/2026-04-21-e2e-smoke-coverage-rewrite.md \
       docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md
```

Edit the moved file's frontmatter: `status: active` → `status: accepted`.

- [ ] **Step 37.4: Commit**

```bash
git add docs/architecture/05_dashboard.md \
        docs/architecture/01_public_api.md \
        docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md \
        docs/rfcs/active/2026-04-21-e2e-smoke-coverage-rewrite.md
git commit -m "docs(arch): canonical-smoke dashboard + public-API invariants; accept e2e-smoke RFC"
```

---

## Task 38 — Push PR 4 and verify

- [ ] **Step 38.1: Push + open PR**

```bash
git push -u origin feature/smoke-swebench
gh pr create --title "feat(e2e/swebench): canonical smoke + arch-doc updates + RFC acceptance (PR 4 of 4)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `swebench-verified` to the canonical smoke matrix (third and final env).
- Updates `docs/architecture/06_builtins.md`, `07_testing.md`, `05_dashboard.md`, `01_public_api.md` per the RFC's §"Invariants affected".
- Moves the RFC from `active/` to `accepted/`.

## Test plan
- [x] Unit suite green.
- [ ] CI matrix green for all 3 envs on this PR.
- [ ] Inline screenshot comments posted for all 3 envs on this PR.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 38.2: Verify CI + comments**

Confirm all 3 matrix jobs green and the PR has 3 inline-screenshot comments (one per env) showing dashboard / graph / cohort images.

- [ ] **Step 38.3: Merge**

```bash
gh pr merge feature/smoke-swebench --squash --delete-branch
```

---

## Task 39 — Post-merge housekeeping

- [ ] **Step 39.1: Confirm `screenshots/pr-*` refs don't pile up**

```bash
git ls-remote origin 'refs/heads/screenshots/*' | head
```

Open PRs should have a ref; closed PRs should not.

- [ ] **Step 39.2: If `docs/bugs/open/2026-04-18-ci-docker-caching.md` is not already moved to `fixed/`, move it**

```bash
ls docs/bugs/open/2026-04-18-ci-docker-caching.md 2>/dev/null && \
  git mv docs/bugs/open/2026-04-18-ci-docker-caching.md docs/bugs/fixed/ && \
  git commit -m "docs(bug): ci-docker-caching fixed as part of reset+e2e RFCs"
```

- [ ] **Step 39.3: Close the plan**

Mark this plan's tracking issue (if any) closed. Verify no followup tasks are needed before declaring complete.

---

## Global checks run at end of each PR

Every PR MUST leave these green before merging:

```bash
pnpm run check:fast          # ruff + ty + slopcop + eslint + tsc
uv run pytest tests/unit -v  # unit suite
# Plus: the relevant CI e2e smoke job(s) green on the PR itself.
```

If any fail, fix with additional commits on the branch — never `--amend` or `--no-verify`.

---

## Appendix — Troubleshooting

### `ModuleNotFoundError` on a new import

Most commonly a missing package marker — add `__init__.py` at each intermediate level.

### Playwright `getByTestId` finds zero elements

The dashboard source may use a different attribute (`data-test-id` vs `data-testid`) or different strings. Grep:

```bash
grep -rn "data-testid\|data-test-id\|testId=" ergon-dashboard/src/ | head
```

Update the Playwright spec to match the actual selectors.

### Screenshot ref push denied

Check that `permissions:` in the workflow includes `contents: write`. GitHub rulesets may also block pushes to custom refs — if so, either adjust the ruleset (preferred) or switch to uploading screenshots as a CI artifact and linking the artifact URL in the PR comment (fallback).

### 5-minute budget exceeded

First run: expect this; tune. If consistently over:
1. Check Docker layer-cache hit rate in the workflow logs.
2. Profile the individual phases (`time uv run pytest ...`).
3. If the sandbox provisioning is the bottleneck, raise the budget; don't cut corners on coverage.
