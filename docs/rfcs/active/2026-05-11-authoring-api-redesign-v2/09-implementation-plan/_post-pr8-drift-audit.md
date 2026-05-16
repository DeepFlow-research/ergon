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
| 9 (dynamic subtasks) | **MAJOR** | Yes — architectural assumption wrong | Medium — needs design decision |
| 10a (SWEBench) | **MINOR** | No — mostly "this is the work" | Light — one prerequisite extraction |
| 10b (ResearchRubrics) | **MINOR-MEDIUM** | No, but depends on 10a + design call | Light + one design decision |
| 10c (GDPEval) | **MINOR** | No — mostly "this is the work" | Light |
| 11 (deletion gate) | **MINOR** | No — but only valid after 9/10a-c | Light — sync xfail names |
| 12 (walkthrough CI) | **MAJOR** | Yes — missing infra | Medium — needs test driver + exports |

Two plans need real reconciliation work before implementation (PR 9 and PR 12).
The benchmark migration plans (10a/b/c) and deletion gate (11) are mostly fine
but have a handful of name/signature drift items that should be corrected
in-place when each PR is picked up.

---

## PR 9 — Dynamic Subtasks (MAJOR drift)

### What the plan assumes that isn't true

| Plan says | Reality |
|---|---|
| `WorkerContext` is mutable with injected `_task_mgmt` / `_task_inspect` services | `WorkerContext` is a **frozen Pydantic BaseModel** |
| `WorkerContext.spawn_task(task, depends_on=()) → SpawnedTaskHandle` | Method doesn't exist; `SpawnedTaskHandle` doesn't exist |
| `ContainmentViolation` error in `api/errors.py` | Doesn't exist |
| `TaskManagementService.add_subtask(*, run_id, parent_task_id, task, depends_on)` | Actual signature: `add_subtask(session, command: AddSubtaskCommand)` — uses a command object |
| `Task` model has `created_by` field (added in PR 7) | PR 7 added `created_by` to **Benchmark**, not to Task. Misread of PR 7 scope |
| `WorkflowGraphRepository.descendants_by_parent(...)` | Method doesn't exist (the SQL CTE in the plan is correct but needs to be added) |
| `TaskInspectionService.descendant_ids(...)` | Method doesn't exist |

### Design decision required

The plan's `WorkerContext.spawn_task(...)` API only works if `WorkerContext` is
mutable or holds service references. Two paths:

- **Path A:** Make `WorkerContext` mutable (breaks the frozen invariant, requires
  Pydantic config change, opens question of thread-safety in worker bodies).
- **Path B:** Keep `WorkerContext` immutable; provide spawn via a separate
  `WorkerFacade`-style object passed alongside (cleaner, but the plan's API
  shape needs a rewrite).

### Reconciliation work before PR 9

1. Pick A or B above; rewrite Task 2 / Task 2b / Task 3 of the plan accordingly.
2. Drop the `Task.created_by` assumption — if dynamic spawns need spawner
   identity, record it on the graph node or audit metadata, not on Task.
3. Add `WorkflowGraphRepository.descendants_by_parent` and
   `TaskInspectionService.descendant_ids` as PR 9 tasks (the SQL CTE is fine).
4. Decide whether `add_subtask` keeps the command-object pattern or accepts a
   `Task` instance directly.

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
| `JudgeCriterion` becomes a Pydantic `Criterion` subclass with `judge_model` field | Base `Criterion` is an **ABC**, not a `BaseModel` — Pydantic conversion is blocked by base class | Major (design call) |
| `ResearchRubricsBenchmark.__init__` accepts `worker_factory`/`sandbox_factory`/`evaluator_factory` kwargs | Currently takes only `limit`/`name`/`description`/`metadata` | Real — needs adding in PR 10b |
| Depends on PR 10a's `_ManagerBackedSandboxRuntime` adapter | Natural sequencing — not drift |

### Reconciliation work before PR 10b

1. **Decide on `Criterion` base class.** Either:
   - Keep `ResearchRubricsJudgeCriterion` as a regular subclass of the ABC `Criterion` (drop the Pydantic-model claim from the plan), or
   - Convert `Criterion` itself to a `BaseModel` (architecture change — likely out of scope for PR 10b).
2. Rewrite Task 4 ("Judge Criterion conversion") to match whichever path is chosen.
3. Land PR 10a first (natural dependency).

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

Given current state of the world:

1. **Before starting PR 9:** make the WorkerContext mutability decision (A vs
   B above), then rewrite PR 9's Task 2 / 2b / 3 sections. ~30-60 minutes of
   plan editing.
2. **Before starting PR 10a:** quick read of the plan's Task 1 to confirm the
   `_ManagerBackedSandboxRuntime` extraction is explicitly scoped to PR 10a
   (not assumed pre-existing). Likely no edit needed.
3. **Before starting PR 10b:** decide whether `Criterion` becomes Pydantic
   (architectural) or stays an ABC (rewrite Task 4 of plan).
4. **Before starting PR 10c:** same quick re-read as 10a; likely no edits.
5. **Before starting PR 11:** sync xfail symbol names; drop completed items.
   ~15 minutes.
6. **Before starting PR 12:** scaffold the Inngest test driver. This is a
   meaningful prerequisite — could be its own micro-PR or rolled into PR 12.

Net additional reconciliation work: ~2-4 hours total, mostly concentrated in
PR 9 (design decision) and PR 12 (test driver scaffolding).
