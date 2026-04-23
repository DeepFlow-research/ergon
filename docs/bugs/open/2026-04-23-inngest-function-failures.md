---
status: open
opened: 2026-04-23
fixed_pr: null
priority: P1
invariant_violated: null
related_rfc: null
---

# Bug: Four inngest function failures surfaced while bringing up local smoke

Four independent bugs, all blocking or degrading the canonical-smoke end-to-end
loop, surfaced together while running `SMOKE_COHORT_SIZE=1 minif2f` against a
fresh local stack on 2026-04-23.  Each also affects production flows (not
just smoke), which is why they're bundled into one report.

Discovery query (now documented in `CLAUDE.md § Debugging → Inngest function
failures`):

```bash
FROM_TIME=$(date -u -v-15M +%Y-%m-%dT%H:%M:%SZ)
curl -s -X POST http://localhost:8289/v0/gql -H 'Content-Type: application/json' \
  -d "{\"query\":\"query { runs(first: 40, orderBy: [{field: QUEUED_AT, direction: DESC}], filter: { from: \\\"${FROM_TIME}\\\", status: [FAILED] }) { edges { node { function { slug } output } } } }\"}"
```

Counts from one 15-minute window during a single cohort-of-1 submission:

| Count | Function | Layer |
|------:|----------|-------|
| 18 | `ergon-dashboard-handle-graph-mutation` | Dashboard Zod |
| 11 | `ergon-core-cleanup-cancelled-task` | Backend DB |
|  8 | `ergon-core-task-execute` | Backend |
|  3 | `ergon-dashboard-dashboard-task-evaluation-updated` | Dashboard Zod |

The subsections below capture symptom, repro, root cause (where known),
scope, and proposed fix for each.  Any of them can be split into its own
`docs/bugs/open/*.md` when picked up — the grouping is for "discovered
together," not "must be fixed together."

C and D are both instances of the same broken pipeline; § E captures the
systemic fix that subsumes their individual proposed fixes.

---

## A. `ergon-core-task-execute` — stuck subtasks with null `task_id`

### Symptom

Every smoke subtask (`d_root`, `l_1`, `s_a`, `s_b`, etc.) transitions to
`RUNNING` in `run_task_executions` and never progresses.  `error_json` stays
`null`, `completed_at` stays `null`, the parent run sits in `EXECUTING`
indefinitely.  `wait_for_terminal` in the pytest driver eventually trips its
270 s timeout.  Inngest reports `inngest/function.failed` for the
corresponding `task-execute` invocation ~1 s after `task/ready` fires.

### Repro

```bash
bash scripts/smoke_local_up.sh
# export env vars from the script's stanza
SMOKE_COHORT_SIZE=1 scripts/smoke_local_run.sh minif2f
# Watch:
docker compose exec postgres psql -U ergon -d ergon -c \
  "SELECT task_slug, status FROM run_graph_nodes WHERE run_id=<id> ORDER BY level;"
```

Subtasks wedge at `RUNNING` within a few seconds of dispatch.

### Root cause

Inngest error payload (captured via the GraphQL query above):

```
1 validation error for PreparedTaskExecution
task_id
  UUID input should be a string, bytes or UUID object
  [type=uuid_type, input_value=None, input_type=NoneType]
```

Two stacked bugs in `ergon_core/ergon_core/core/runtime/inngest/execute_task.py`:

1. **`TaskExecutionService.prepare(...)` returns `task_id=None`** for subtask
   graph nodes.  `PreparedTaskExecution` is a pydantic model with a non-null
   `task_id: UUID`, so the step output fails Pydantic validation inside
   Inngest.  Root cause of *why* `prepare` produces `None` is not yet
   identified — the `task-execute` payload itself carries a valid
   `payload.task_id`; something in `prepare` either drops it or looks up a
   null-valued column.  Investigation needed.

2. **The `except` handler can't run** because `prepared` is referenced before
   assignment.  `execute_task.py:251-262`:

   ```python
   prepared = await ctx.step.run("prepare-execution", _prepare, ...)   # line 75
   # ... main body ...
   except Exception as exc:                                            # line 251
       error_msg = str(exc)
       logger.exception("task-execute failed task_id=%s: %s", ...)
       await svc.finalize_failure(
           FailTaskExecutionCommand(
               execution_id=prepared.execution_id,                    # NameError
               ...
           )
       )
   ```

   When `step.run("prepare-execution", ...)` raises, `prepared` is never
   bound.  The except block then hits `prepared.execution_id` and raises
   `NameError`, which is what Inngest finally records.  The real error —
   Pydantic's complaint — is buried in an earlier step-run attempt; our own
   handler erases it before it can persist `error_json` or emit
   `TaskFailedEvent`.

### Scope

Every workflow where `prepare` returns `task_id=None`.  Observed on every
smoke subtask.  Likely affects any production benchmark whose
subtask-graph-node row has the right shape to trip the same lookup path —
needs investigation to know for sure.  The NameError bug, separately,
silently hides *every* pre-prepare failure across all task-execute runs,
not just this one case.

### Proposed fix

Two changes, one cheap and one that needs investigation:

1. **Defensive except block (cheap, do immediately).**  Pull the identifiers
   the failure handler needs out of `payload` (which *is* guaranteed bound
   at line 59) before entering the try block, or guard with
   `if 'prepared' in locals()`.  Preferred form: hoist `execution_id: UUID |
   None = None` and `node_id` above the try, assign inside, branch on
   presence when finalizing.  This alone won't fix the stuck-subtask bug,
   but it ensures the *real* failure is surfaced via `error_json` /
   `TaskFailedEvent` on every future regression.

2. **Fix the null `task_id` from prepare (investigation needed).**  Read
   `TaskExecutionService.prepare` + `PrepareTaskExecutionCommand` handling;
   find where `task_id` is sourced for subtask graph nodes.  Likely a
   graph-node column lookup that's returning null when the node was dynamically
   added by `add_subtask` rather than statically defined.  Write a unit test
   that drives `prepare` against a dynamically-spawned node row and asserts
   `result.task_id is not None`.

---

## B. `ergon-core-cleanup-cancelled-task` — enum rejects `CANCELLED`

### Symptom

Every cleanup-cancelled-task invocation fails with:

```
(psycopg2.errors.InvalidTextRepresentation) invalid input value
for enum taskexecutionstatus: "CANCELLED"
LINE 1: UPDATE run_task_executions SET status='CANCELLED' WHERE ...
```

Task rows that should be marked cancelled remain in whatever state they held
when the parent workflow cancelled.  Dashboard widgets relying on cancelled
status misreport the cohort.

### Repro

Any workflow that triggers `TASK_CANCEL` or `RUN_CANCEL`.  During the smoke
session, we observed 11 failures in 15 minutes — triggered by Inngest's
`cancel=[...RUN_CANCEL, *TASK_CANCEL]` wiring on `execute_task_fn` firing
whenever a run fails (bug A above).

### Root cause

The Postgres enum `taskexecutionstatus` was created without `CANCELLED`.
The application-side `TaskExecutionStatus` enum (likely in
`ergon_core/core/persistence/shared/enums.py` — confirm) includes
`CANCELLED`, but the migration that CREATE TYPE'd the DB enum omitted it (or
added values later were never ALTER TYPE ADD VALUE'd into the live DB).

### Scope

Every cancellation.  Stale state for operators who cancel a run from the
dashboard or CLI.  Downstream visualizations show tasks frozen in
non-terminal state when they should be cancelled.

### Proposed fix

Alembic migration: `ALTER TYPE taskexecutionstatus ADD VALUE IF NOT EXISTS
'CANCELLED';`.  Must run outside a transaction (Postgres restriction on enum
mutation) — use `op.execute` with `autocommit_block` or put it in a
one-shot migration with the `transactional = False` pattern Alembic
supports.  Add a unit test that exercises each enum value end-to-end against
real Postgres (not sqlite, not mock).

---

## C. `ergon-dashboard-handle-graph-mutation` — missing `task_key` / `assigned_worker_key`

### Symptom

Dashboard returns HTTP 500 for every `dashboard/graph.mutation` event:

```
[
  { "expected": "string", "code": "invalid_type",
    "path": ["task_key"],
    "message": "Invalid input: expected string, received undefined" },
  { "expected": "string", "code": "invalid_type",
    "path": ["assigned_worker_key"],
    "message": "Invalid input: expected string, received undefined" }
]
```

Dashboard graph UI doesn't reflect dynamic add/remove/reassign events.
Every subtask mutation (smoke spawns 9 per run) is silently dropped by the
dashboard — the tree stays frozen at its initial state.

### Repro

Run any workflow that spawns subtasks.  18 failures from one minif2f run.

### Root cause

Same class as the `task_tree={}` bug the sub-agent just fixed in
`start_workflow.py` — the backend emits a `dashboard/graph.mutation` payload
that doesn't match the dashboard's Zod schema.  Investigation needs to find:

- the emitter (likely `ergon_core/core/dashboard/emitter.py::graph_mutation`
  or similar)
- the dashboard Zod schema
  (`ergon-dashboard/src/lib/contracts/events.ts` — search for graph.mutation
  / `parseDashboardGraphMutation*`).

The emitter is passing fields under different names — probably `task_slug`
instead of `task_key` and `assigned_worker_slug` instead of
`assigned_worker_key`.  The emitter-side contract file
(`ergon_core/core/dashboard/event_contracts.py`) uses `slug`; dashboard
expects `key`.  One side needs to change (or the contract file should
declare both aliases, matching the `name` / `name_field` alias trick already
used for `TaskTreeNode`).

### Scope

Every dynamic task graph mutation on every run.  Dashboard freezes at the
initial tree.  Smoke runs' 9-leaf DAG never renders its spawned children.

### Proposed fix

**Superseded by § E — systemic fix.** The scoped fix would be: rename
dashboard-side `task_key` → `task_slug` and `assigned_worker_key` →
`assigned_worker_slug` in two files (`graphMutations.ts:21,26,30` +
`graphMutationReducer.ts:204,211,279`) plus tests.  ~5 line edits.  But
that patches one symptom; § E fixes the whole drift class at once.

---

## D. `ergon-dashboard-dashboard-task-evaluation-updated` — missing criterion fields

### Symptom

Dashboard returns HTTP 500 for every `dashboard/task.evaluation_updated`
event:

```
[
  { path: ["evaluation","criterionResults",0,"id"],
    message: "Invalid input: expected string, received undefined" },
  { path: ["evaluation","criterionResults",0,"stageNum"],
    message: "expected number, received undefined" },
  { path: ["evaluation","criterionResults",0,"stageName"], ... },
  { path: ["evaluation","criterionResults",0,"criterionNum"], ... },
  { path: ["evaluation","criterionResults",0,"criterionDescription"], ... }
]
```

Evaluation results never render on the dashboard.  For smoke, this means
criterion scores are invisible even though they're correctly persisted in
`run_task_evaluations`.

### Repro

Any run that produces an evaluation.  3 failures from one minif2f run.

### Root cause

Same class as B.  `DashboardTaskEvaluationUpdatedEvent` in
`ergon_core/core/dashboard/event_contracts.py` embeds an `evaluation: dict`
(opaque); whatever builds that dict doesn't populate
`criterionResults[].{id, stageNum, stageName, criterionNum,
criterionDescription}`.  Dashboard Zod expects those fields on every
`criterionResults` row.

The backend sender is in
`ergon_core/core/runtime/inngest/evaluate_task_run.py` (`dashboard_emitter.
task_evaluation_updated` at line 211 per `grep -rn`).  It builds the
`evaluation` dict from… the `RunTaskEvaluationDto`, presumably.  Check
whether the DTO has these fields and is just passing them through, or
whether they exist on the eval record but aren't serialized into the
criterion-results list.

### Scope

Every evaluation on every run.  Silent for operators — dashboard just
doesn't update the score panel.

### Proposed fix

**Superseded by § E — systemic fix.** The scoped fix would be: replace
the `evaluation: dict[str, Any]` placeholder on
`DashboardTaskEvaluationUpdatedEvent` with a proper pydantic DTO that
carries `criterionResults[].{id, stageNum, stageName, criterionNum,
criterionDescription}`, thread those fields through the emitter in
`evaluate_task_run.py:211`.  But doing so in isolation just moves the
drift problem — the hand-written dashboard Zod is the real liability.

---

## E. Systemic: pydantic → Zod codegen is broken; two schema sources have drifted

### Symptom

Bugs C and D above are both **"dashboard hand-wrote a Zod schema that
disagrees with what the backend pydantic actually emits."**  Neither is
a semantic problem; both are drift between two parallel sources of
truth.  The `task_tree={}` bug that the sub-agent just fixed in
`start_workflow.py` was the *third* instance of the same class.  This
keeps happening because the type pipeline that was *supposed* to prevent
it is broken on three dimensions.

### Repro

Grep: `find . -name "*.py" -exec grep -l 'dict\[str, Any\]' {} \;` on
dashboard event contracts returns several opaque fields.  Try
`pnpm run generate:contracts` in `ergon-dashboard/` — step 1
(`generate:contracts:schemas`) fails because
`scripts/export_contract_schemas.py` does not exist in the repo.

### Root cause

The pipeline that *should* give end-to-end type safety:

```
Python pydantic model (source of truth)
  → scripts/export_contract_schemas.py               → events/schemas/*.schema.json
  → pnpm exec json-schema-to-zod                     → events/<Name>.ts  (generated Zod)
  → dashboard imports from "@/generated/events"      → parser used at runtime
```

Three independent failures stack:

1. **The exporter script is missing.**  `package.json:12` references
   `scripts/export_contract_schemas.py`; that file is not in the repo.
   Either never committed or deleted.  Tracked `.schema.json` files
   under `ergon-dashboard/src/generated/events/schemas/` are stale
   snapshots — no one can regenerate them.

2. **Pydantic escape hatches — `dict[str, Any]` on multiple events.**
   `DashboardTaskEvaluationUpdatedEvent.evaluation: dict[str, Any]`,
   `DashboardWorkflowStartedEvent.task_tree: dict[str, Any]`, and others
   export as `{type: object, additionalProperties: true}` → Zod
   generates `z.any()` → validates nothing.  Even if the exporter is
   restored, these types contribute zero safety until they're tightened
   to proper nested pydantic DTOs.

3. **Parallel hand-written Zod in `lib/contracts/events.ts`.**  The
   dashboard keeps a *second* strict parser per event type —
   `parseDashboardTaskEvaluationUpdatedData` at `events.ts:310`,
   `parseDashboardGraphMutationData` at `events.ts:421`, etc.  These
   were written by hand with field expectations the backend never
   actually committed to.  Inngest handlers use the strict parser; it's
   the drift surface.  The generated schemas are ignored at runtime.

### Scope

Every `dashboard/*` event.  Any time the backend adds or renames a
field, one of: (a) the generated schema silently accepts it via
`z.any()`, (b) the hand-written parser silently rejects it, (c) both.
The failure mode is always "dashboard 500s, backend is fine, no shared
test exercises the boundary."  Recurring symptom, no structural fix.

### Proposed fix

Four-step restore-and-tighten:

1. **Restore `scripts/export_contract_schemas.py`.**  Walk every
   `InngestEventContract` subclass under
   `ergon_core.core.dashboard.event_contracts`, call
   `model.model_json_schema()`, write to the path named in
   `ergon-dashboard/src/generated/events/schemas/manifest.json`.
   Probably ~40 lines.  If git history has a prior version, resurrect
   it; otherwise write a fresh one.  First run will likely show diffs
   against currently-tracked schemas, proving the drift.

2. **Tighten pydantic — no `dict[str, Any]` on dashboard events.**
   Audit every `Dashboard*Event`; replace opaque-dict fields with real
   nested DTOs.  Candidates found:

   - `DashboardTaskEvaluationUpdatedEvent.evaluation` →
     proper `DashboardTaskEvaluationDto` (criteria results etc.)
   - `DashboardWorkflowStartedEvent.task_tree` →
     proper `TaskTreeNode` recursive model (one already exists in the
     same file but is currently unused here)
   - any other `dict[str, Any]` / `Any` leaks surfaced while auditing

3. **Regenerate, delete hand-written parsers.**  Run
   `pnpm run generate:contracts`.  Delete every hand-authored
   `parseDashboard*Data` in `lib/contracts/events.ts` and the
   parallel hand-written Zod in
   `features/graph/contracts/graphMutations.ts`.  Route every dashboard
   consumer through `@/generated/events/*` so there is one source of
   truth.

4. **CI check.**  Add a job to `ci-fast.yml` that runs
   `pnpm run generate:contracts` and fails the build if it produces a
   diff against tracked files.  Now any backend type change that
   forgets to regenerate fails in PR, not in prod.

After this lands, bugs C and D are solved by construction and every
future dashboard contract change is covered.  Ongoing cost: two commands
(`pnpm run generate:contracts && git add src/generated`) whenever a
`Dashboard*Event` type changes.

### Risk

The strict hand-written parsers may have caught *other* drifts that
haven't surfaced yet — deleting them and regenerating could unmask
those.  Mitigation: do step 2 (tighten) thoroughly; the generated Zod
is only as good as the pydantic source.  Run the full e2e smoke suite
before landing step 3.

---

## Ordering / priority

1. **A1 (defensive except block)** — trivial, do first.  Makes every future
   `task-execute` failure actually write `error_json`, which lets the next
   investigator see what's really going wrong without doing the GraphQL
   dance.
2. **A2 (node_id / task_id unification)** — highest-value root cause;
   unblocks smoke entirely.  Plan in `README.md § Open refactors`.
3. **B (CANCELLED enum)** — migration-only; unblocks any future cancel flow.
4. **E (contract-gen pipeline)** — fixes C and D by construction, plus every
   future dashboard-contract drift of the same class.  Four sub-steps
   (restore exporter → tighten pydantic → regenerate + delete hand-written
   → CI check); step 1 is fastest and surfaces the blast radius.  Smoke's
   pytest assertions pass without this (they hit DB directly) but the
   Playwright dashboard-state assertions will fail until E lands.

C and D are not listed separately — § E subsumes them.

## Not in scope of this report

- The `task_tree={}` bug in `start_workflow.py` — already patched in a
  separate change (same class as C and D).
- The uvicorn logger swallowing issue — mitigated by adding
  `logging.basicConfig` to `app.py`; no separate bug file since the
  Inngest-GraphQL path is now the preferred debug surface anyway (see
  `CLAUDE.md`).
- The smoke criterion firing before children complete — by design; the
  smoke parent worker should `await` its subtree before returning.  Tracked
  as a smoke-fixture fix, not a core bug.
