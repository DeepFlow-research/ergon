# Post-PR-8 Drift Audit (2026-05-16)

After PR 8 (lifecycle CLI cleanup) landed, this audit checks whether the
remaining v2-stack plans (PR 9, 10a/b/c, 11, 12) still reflect the current
state of the code, or whether they have drifted in the same way PR 8's plan
had (which required ~290 lines of reconciliation before implementation).

**Methodology:** six parallel Explore agents, one per plan, each given the
plan path plus a checklist of high-yield drift sources (file paths, class
existence, sync/async signatures, public API shape, migration ids, deletion
target status). Reports were then triaged here to separate *genuine drift*
from *current-state-as-starting-point* (where the agent flagged what a
PR proposes to do *as if* it were already done).

## TL;DR

| PR | Genuine drift verdict | Blocking? | Reconciliation effort |
|----|----|----|----|
| 9 (dynamic subtasks) | **MAJOR** | Yes — frozen WorkerContext contradicts RFC | Medium — unfreeze + add PrivateAttr |
| 10a (SWEBench) | **MINOR** | No — mostly "this is the work" | Light — one prerequisite extraction |
| 10b (ResearchRubrics) | **MEDIUM** | Yes — Criterion base class wrong shape | Medium — micro-PR to convert ABC → BaseModel + ABC |
| 10c (GDPEval) | **MINOR** | No — mostly "this is the work" | Light |
| 11 (deletion gate) | **MINOR** | No — but only valid after 9/10a-c | Light — sync xfail names |
| 12 (walkthrough CI) | **MAJOR** | Yes — missing infra | Medium — needs test driver + exports |

Three plans need real reconciliation work before implementation:
- **PR 9** — both design questions resolved (Path A: unfreeze `WorkerContext`).
- **PR 10b** — design question resolved (Path A: `Criterion` becomes `BaseModel + ABC`).
- **PR 12** — needs Inngest test driver scaffolding; no design call, just infra.

The benchmark migration plans (10a/10c) and deletion gate (11) are mostly fine
but have a handful of name/signature drift items that should be corrected
in-place when each PR is picked up.

### Design calls resolved against RFC (`/docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/`)

1. **PR 9 `WorkerContext` mutability** → RFC `03-runtime.md` (lines 299–313, 457–501)
   and `01-api-surface.md` (lines 288–451): `WorkerContext(BaseModel)` with
   `PrivateAttr` for `_task_mgmt` / `_task_inspect` / `_resource_repo`. **NOT
   frozen.** Framework injects via `_for_job` classmethod using
   `object.__setattr__`. The current `model_config = {"frozen": True}` is itself
   drift that needs to be undone.
2. **PR 10b `Criterion` base class** → RFC `01-api-surface.md` line 120 and lines
   1030–1082: `class Criterion(BaseModel, ABC)`. Mandatory because all public
   types follow the `_type`-discriminator serialization pattern. Current pure
   ABC shape is drift; conversion needs to happen before PR 10b lands.

---

## PR 9 — Dynamic Subtasks (MAJOR drift)

### What the plan assumes that isn't true

| Plan says | Reality |
|---|---|
| `WorkerContext` is mutable with injected `_task_mgmt` / `_task_inspect` services | `WorkerContext` is a **frozen Pydantic BaseModel** (`model_config = {"frozen": True}`) |
| `WorkerContext.spawn_task(task, depends_on=()) → SpawnedTaskHandle` | Method doesn't exist; `SpawnedTaskHandle` doesn't exist |
| `ContainmentViolation` error in `api/errors.py` | Doesn't exist |
| `TaskManagementService.add_subtask(*, run_id, parent_task_id, task, depends_on)` | Actual signature: `add_subtask(session, command: AddSubtaskCommand)` — uses a command object |
| `Task` model has `created_by` field (added in PR 7) | PR 7 added `created_by` to **Benchmark**, not to Task. Misread of PR 7 scope |
| `WorkflowGraphRepository.descendants_by_parent(...)` | Method doesn't exist (the SQL CTE in the plan is correct but needs to be added) |
| `TaskInspectionService.descendant_ids(...)` | Method doesn't exist |

### Design decision — RESOLVED via RFC

The RFC answers this. From `03-runtime.md` §"Worker runtime API: WorkerContext"
(lines 299–313) and §"Framework-side WorkerContext construction" (lines 457–501),
plus `01-api-surface.md` §"The unifying pattern: one class per concept, runtime
as PrivateAttr" (lines 288–451):

> `WorkerContext(BaseModel)` has public fields `(run_id, task_id, execution_id,
> definition_id)` and **PrivateAttr fields** `_task_mgmt`, `_task_inspect`,
> `_resource_repo` holding service references. The framework explicitly injects
> these via `object.__setattr__` in a `_for_job` classmethod.

So **Path A** is the RFC-mandated direction: `WorkerContext` is a `BaseModel`
with `PrivateAttr` for services, **not** frozen. The current frozen config is
itself a drift item that needs to be removed.

### Reconciliation work before PR 9

1. **Drop `model_config = {"frozen": True}`** from `WorkerContext` (it contradicts
   the RFC). Add `PrivateAttr` fields for `_task_mgmt`, `_task_inspect`, and
   `_resource_repo`.
2. **Add `_for_job` classmethod** on `WorkerContext` that injects service
   references via `object.__setattr__` (RFC's two-phase construction pattern).
3. **Drop the `Task.created_by` assumption** — if dynamic spawns need spawner
   identity, record it on the graph node or audit metadata, not on Task.
4. **Add `WorkflowGraphRepository.descendants_by_parent`** and
   **`TaskInspectionService.descendant_ids`** as PR 9 tasks (the SQL CTE in the
   plan is fine; just needs to be implemented, not assumed-existing).
5. **Resolve `add_subtask` signature drift** — either extend the command-object
   pattern to accept a `Task` instance, or add a thin wrapper on `WorkerContext`
   that builds the command. Plan should pick one and update Task 2 accordingly.

---

## PR 10a — SWEBench Migration (MINOR drift)

The audit agent flagged "SWEBench still uses TaskSpec" as drift, but that's
just the starting point PR 10a converts from. Real items:

| Plan says | Reality | Severity |
|---|---|---|
| Shared `ManagerBackedSandboxRuntime` at `ergon_builtins/sandbox/_manager_backed.py` | Doesn't exist yet — currently inlined in `minif2f/sandbox.py` | Verify: is this PR 10a's task to extract, or assumed-already-done? |
| Worker factory pattern `make_swebench_worker()` in `workers.py` | Currently `SWEBenchReactWorker` class in `worker_factory.py` | Likely PR 10a's renaming task — verify wording |
| Toolkit is Pydantic `BaseModel` with `tools(sandbox, task)` | Currently regular class with `__init__(sandbox, workdir)`, `get_tools()` | Likely PR 10a's conversion — verify |
| Sandbox subdirectory rename to avoid module shadowing | Need: `git mv swebench_verified/sandbox swebench_verified/sandbox_template` first | Prerequisite step to call out in plan |

### Reconciliation work before PR 10a

Light — read the plan's Task 1 carefully and confirm it explicitly proposes
the extraction of `_ManagerBackedSandboxRuntime` from MiniF2F (audit agent
read it as if the adapter already existed; the plan likely says "create it").
If the plan does propose creating it as part of PR 10a, treat the audit's
"missing" flag as informational, not drift.

---

## PR 10b — ResearchRubrics Migration (MINOR-MEDIUM drift)

The audit flagged real drift items that affect plan correctness:

| Plan says | Reality | Severity |
|---|---|---|
| `JudgeCriterion` becomes a Pydantic `Criterion` subclass with `judge_model` field | Base `Criterion` is **pure ABC** (`class Criterion(ABC)`), not `BaseModel + ABC` | Real drift, design RESOLVED below |
| `ResearchRubricsBenchmark.__init__` accepts `worker_factory`/`sandbox_factory`/`evaluator_factory` kwargs | Currently takes only `limit`/`name`/`description`/`metadata` | Real — needs adding in PR 10b |
| Depends on PR 10a's `_ManagerBackedSandboxRuntime` adapter | Natural sequencing — not drift |

### Design decision — RESOLVED via RFC

The RFC answers this. From `01-api-surface.md` line 120 (file tree) and
§"Criterion class signature — locked [v2: locked]" (lines 1030–1082):

> ```python
> class Criterion(BaseModel, ABC):
>     type_slug: ClassVar[str]
>     required_packages: ClassVar[list[str]] = []
>
>     @abstractmethod
>     async def evaluate(self, context: CriterionContext) -> CriterionOutcome: ...
>
>     @classmethod
>     def from_definition(cls, criterion_json: TaskDefinitionJson) -> "Criterion": ...
> ```

So **Path A** is the RFC-mandated direction: `Criterion` must be
`class Criterion(BaseModel, ABC)` to support the `_type` discriminator
serialization pattern used across all public types. The current pure-ABC shape
is itself a drift item.

This is **architectural** — it affects every existing `Criterion` subclass
(rubric criteria, builtins, tests). It probably warrants its own micro-PR (or
becomes Task 0 of PR 10b) rather than being snuck in as part of the
`ResearchRubricsJudgeCriterion` work.

### Reconciliation work before PR 10b

1. **Convert `Criterion` base from pure ABC to `class Criterion(BaseModel, ABC)`**.
   Audit every existing subclass; most likely they all pass identity fields via
   `__init__` today and will need to be converted to `BaseModel` field
   declarations. Could be its own micro-PR before 10b lands.
2. **Add factory kwargs** (`worker_factory`, `sandbox_factory`,
   `evaluator_factory`) to `ResearchRubricsBenchmark.__init__` mirroring the
   MiniF2F pattern.
3. **Land PR 10a first** (natural dependency for the shared
   `_ManagerBackedSandboxRuntime` adapter).

---

## PR 10c — GDPEval Migration (MINOR drift)

Same pattern as 10a — most of what the agent flagged as drift is the work the
PR proposes to do (TaskSpec → Task). Real items to verify when picking up PR 10c:

| Plan says | Reality | Severity |
|---|---|---|
| `make_gdpeval_worker()` factory in `workers.py` | Currently `GDPEvalReactWorker(ReActWorker)` class in `worker_factory.py` | Likely the work — verify wording |
| Toolkit as Pydantic `BaseModel` | Currently regular class | Likely the work — verify wording |
| `GDPEvalBenchmark.__init__` accepts factory kwargs | Currently only takes dataset/split/limit | Real — needs adding in PR 10c |
| `GDPEvalSandbox(Sandbox)` subclass | Doesn't exist | Likely the work |
| Smoke fixture missing GDPEval row | Confirmed missing | Real — PR 10c should add |

### Reconciliation work before PR 10c

Light — same as 10a. Read Task 1 carefully to confirm the plan proposes the
sandbox subclass creation and factory pattern adoption as PR 10c work
(not assumed-already-done).

---

## PR 11 — Deletion Final Schema (MINOR drift)

The audit agent's "MAJOR DRIFT" verdict conflates "deletion targets still
exist" (the point of PR 11) with actual drift. Real drift items:

| Plan says | Reality | Severity |
|---|---|---|
| `Worker.from_buffer` is a PR 11 deletion target | Already deleted | Drop from plan |
| `Worker.validate` rename to `validate_runtime_deps` is a PR 11 task | Already renamed (PR 5) | Drop from plan |
| Test xfail symbol names in `test_dead_path_audit.py` match `_worker_from_payload_bridge`, etc. | Actual xfails use different symbol names (e.g., `legacy_worker_from_payload`, `_prepare_legacy_graph_native`, `execute_task`) | Sync the symbol names |
| Plan still lists `saved_specs` package as deletion target | Still exists today; verify whether 9/10 should have removed it | Cross-check after PRs 9/10 land |

### Reconciliation work before PR 11

Trivial — sync the symbol names in the plan's xfail flip checklist against
what's actually in `test_dead_path_audit.py` and `test_v2_final_state_ledger.py`
at the time PR 11 is picked up. Drop already-completed items
(`Worker.from_buffer`, `Worker.validate` rename) from the deletion list.

The PR 11 deletion gate itself is only valid AFTER PRs 9 and 10a/b/c have
landed — that's natural sequencing, not drift.

---

## PR 12 — Walkthrough CI (MAJOR drift)

| Plan says | Reality |
|---|---|
| `from ergon_core.api import launch_run` | `launch_run` lives in `ergon_core.core.application.experiments.launch`, **not** re-exported from `ergon_core.api` |
| Synchronous Inngest test driver with `inngest_driver.run_until_terminal()`, `step_invocations_for_function()`, `events_for()` | **No such driver exists** in the codebase |
| `await read_run(run_id)` | Only `read_run_state()` exists |
| `ergon_core/tests/integration/` directory holds new tests | Directory doesn't exist (only `ergon_core/tests/unit/`) |

### Reconciliation work before PR 12

Three concrete prerequisites:

1. **Export `launch_run` from `ergon_core.api`** — either re-export it from
   `ergon_core/api/__init__.py` or update every plan reference to import from
   the internal module.
2. **Scaffold the synchronous Inngest test driver** — research Inngest's
   testing library (likely `inngest.SDK()` or a test-mode client) and build
   the wrapper helper (`run_until_terminal`, `step_invocations_for_function`,
   `events_for`) in `ergon_core/tests/integration/conftest.py` BEFORE Task 1
   can run. This is a substantial prerequisite, not a quick rename.
3. **Decide on `read_run()` vs `read_run_state()`** — either alias the
   existing helper, or update the plan to use the existing name.

The plan's overall architecture (fixture-driven happy-path → variant
walkthrough) is sound; only the tooling layer is missing.

---

## Recommended order of operations

Given current state of the world (and RFC-resolved design calls):

1. **Before starting PR 9:** unfreeze `WorkerContext` and add `PrivateAttr` fields
   for services (per RFC `03-runtime.md`). Then rewrite PR 9's Task 2 / 2b / 3
   sections to match the unified pattern. ~30-60 minutes of plan editing.
2. **Before starting PR 10a:** quick read of the plan's Task 1 to confirm the
   `_ManagerBackedSandboxRuntime` extraction is explicitly scoped to PR 10a
   (not assumed pre-existing). Likely no edit needed.
3. **Before starting PR 10b:** convert `Criterion` ABC → `BaseModel + ABC` per
   RFC `01-api-surface.md` line 1054. This touches every existing subclass and
   could be its own micro-PR ("PR 10b-prep" or "Task 0 of PR 10b"). Once done,
   PR 10b's `JudgeCriterion` Pydantic conversion is a one-line subclass
   declaration.
4. **Before starting PR 10c:** same quick re-read as 10a; likely no edits.
5. **Before starting PR 11:** sync xfail symbol names; drop completed items
   (`Worker.from_buffer`, `Worker.validate` rename). ~15 minutes.
6. **Before starting PR 12:** scaffold the Inngest test driver and re-export
   `launch_run` from `ergon_core.api`. This is a meaningful prerequisite —
   could be its own micro-PR or rolled into PR 12.

Net additional reconciliation work: ~3-5 hours total, plus two micro-PRs that
could land independently:
- **micro-PR-A:** `Criterion` ABC → `BaseModel + ABC` (architectural prep for PR 10b).
- **micro-PR-B:** Inngest test driver scaffolding + `launch_run` re-export (prep for PR 12).

The `WorkerContext` unfreeze + `PrivateAttr` work fits naturally into PR 9
itself rather than a separate micro-PR — it's part of the dynamic-spawning
infrastructure.
