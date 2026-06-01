---
status: open  # open | fixed
opened: 2026-05-29
fixed_pr: null
priority: P1  # see per-issue priorities below
invariant_violated: docs/architecture/04_persistence.md  # WAL/projection sync; doc being rewritten
related_rfc: null
---

# Bug: code-intrinsic hostility (footguns independent of stale docs)

This is an umbrella findings + remediation doc. It captures places where the
**code itself** fights a contributor — silent-correctness footguns, leaks, and
fragile assumptions — separate from the (separately tracked) docs/code drift
from the sample-centric refactor. Each issue below is classified by **scope**
so we know whether the fix is a one-line method change, a schema change, a
refactor/deletion, or a design decision.

When any single issue here grows its own repro + fix PR, split it into a
dedicated `docs/bugs/open/` entry and link back here.

Scope legend:

- **method fix** — change the body of one or a few methods; no schema change.
- **schema change** — Alembic migration (add/drop/alter columns or tables).
- **refactor/deletion** — move/merge/delete modules; structural.
- **design decision** — a contract question to settle before coding.
- **tests** — add invariant/roundtrip tests so the bug cannot return.

---

## 1. Persistence: `refine_task` edit is silently dropped on rerun  — P1

### Symptom

Edit a non-running task's description via `refine_task`, then `restart_task`.
The worker executes with the **old** description. The edit appears to "take"
(the dashboard projection column updates) but has no effect on execution and
never reaches the WAL / RL replay.

### Root cause

The projection row stores the task **twice**: a denormalized
`SampleGraphNode.description` column *and* the full authored snapshot in
`SampleGraphNode.task_json` (`persistence/graph/models.py:45,47-55`).

`RuntimeGraphRepository.update_node_field` updates only the column and
appends **no WAL event** (`graph_repository.py:250-277`) — unlike every sibling
mutator (`update_node_status`, `add_edge`, `update_edge_status`) which all append
via `SampleRuntimeEventAppender`.

But execution rebuilds the Task from the **snapshot blob**, not the column:
`task_execution.py:161` passes `node.task_json` into `Task.from_definition(...)`.
So the refined description in the column is never read at rerun, and
`reconstruct_sample_runtime_state_at` (`samples/state.py:257`) never sees the
change because the WAL's `task_snapshot_json` is frozen at materialization
(`materialization.py:66,79`).

The `refine_task` docstring claims "The graph node's description is the single
source of truth -- no definition row to keep in sync"
(`task_management.py:316-317`). That is the bug: there is no definition row, but
there *are* two in-row copies plus a WAL, and they diverge.

### Repro

`refine_task` → `restart_task` on the same node; assert the worker prompt /
`task_json["description"]` reflects the new value. No current test covers this
(grep `update_node_field` finds only call sites, no roundtrip assertion).

### Scope — answering "method, schema, or refactor?"

**Not a schema deletion.** The dual representation is intentional CQRS:

- `sample_graph_nodes` / `sample_graph_edges` = mutable **read model** for fast
  scheduling reads (`persistence/graph/models.py`).
- `sample_*_events` (7 tables) = append-only **WAL** for time-travel replay /
  RL / audit (`persistence/samples/models.py`, replayed by `samples/state.py`).

These serve different masters and both stay. The legacy `run_graph_*` and
definition tables were **already dropped** in migration
`00000003_delete_definition_runtime_columns.py`, so there is no dead table to
remove here.

### The model: WAL is the source of truth, projection is a derived view

The right fix is **event sourcing done properly**: the current state of a task
(and edge) is the **fold of its WAL events**, not an independently-written
projection row. Denormalized columns can never support *arbitrary* attributes a
user attaches to a task — you cannot add a column per unknown key — and writing
them in place destroys the timeline. Reconstructing from the WAL solves both:
any attribute can be mutated as an appended event, and replay-to-timestamp stays
exact.

The codebase is already ~80% there:

- The fold already exists — `SampleRuntimeState.from_events` /
  `reconstruct_sample_runtime_state_at` (`samples/state.py:88,257`). It just
  isn't the authoritative read path yet.
- A generic, timeline-preserving key/value store already exists —
  `SampleAnnotationEventRow` keyed `(target_type, target_id, key)` with
  `annotation.set/updated/deleted` kinds, already folded into an `annotations`
  dict (`state.py:222-232`). Tasks/edges can be annotation targets today.
- `event_type` is a **free-form indexed `str`** (`samples/models.py:33,49`), not
  an enum column — so new event kinds need **no migration**.

Current state = **immutable authored base** (`task.added` snapshot: worker,
sandbox, evaluators, dependencies) ⊕ a small set of **typed editable fields**
(`description`, `assigned_worker_slug`) ⊕ an **`attributes` map under a reserved
namespace** for arbitrary user KV. The authored base never changes, so you can
always tell authored-vs-mutated and replay any point in time. The projection's
`task_json` becomes the **cached fold output** — updated only by applying the
event, never written directly — so scheduling reads stay O(1) while the WAL
remains authoritative.

**Safety constraint:** do NOT blind-merge arbitrary user keys onto `task_json`.
A user setting an attribute named `worker` or `evaluators` must not corrupt
execution. Arbitrary KV lives in the reserved `attributes` namespace; only the
typed editable fields may override structural snapshot fields.

### Scope — answering "method, schema, or refactor?"

Still **not a schema change** (event kinds are free-form strings; reuse existing
tables). In order:

1. **design decision** — settle two sub-questions:
   - **Where do arbitrary attributes live?** (a) reuse `sample_annotation_events`
     with `target_type="task"|"edge"` (cheapest — fold path already implemented),
     or (b) add `task.attribute_changed` / `edge.attribute_changed` kinds for
     clean semantic separation from out-of-band annotations. Lean (b) if
     attributes are conceptually *task fields*, (a) if they're metadata/labels.
   - **Edges:** do edges need arbitrary attributes, or just status (+ a label)?
     Keep the pattern symmetric but don't build the full edge attribute surface
     without a real use case.
2. **refactor (small, central)** — route every projection write through one
   helper that appends the WAL event *and* applies it to the projection in the
   same transaction, so "projection without WAL" (issue 1) and "projection
   diverges from replay" (issue 4) become inexpressible. Make the editable-field
   set + `attributes` overlay the fold contract in `state.py`.
3. **method fix** — `update_node_field` appends an editable-field event (and, for
   arbitrary keys, an attribute/annotation event) via the helper above; point
   `task_execution.py:161` at the fold output (cached `task_json`) so refinements
   actually reach the worker.
4. **tests** — see issue 4 (roundtrip + mutator-completeness).

**Effort:** still no migration. It's one design decision + a small central
refactor (the single write helper + fold contract) + the method fix + tests —
call it 1–2 days, and it dissolves issues 1 and 4 together.

---

## 2. Persistence: in-memory context sequence counter — P1

### Symptom

Under Inngest step **replay** (the engine's normal behavior on retry), worker
context events can collide on the unique `(task_attempt_id, sequence)`
constraint or restart their sequence at 0, corrupting the per-execution context
stream. Also a slow memory leak on long-lived API processes.

### Root cause

`ContextEventService` assigns `sequence` from a **process-local dict**, not the
DB (`context/service.py:33,39-40,118`). The module docstring states the
load-bearing assumption — "safe because each execution runs in a single Inngest
invocation" (`context/service.py:3-4`) — which Inngest replay does not
guarantee. `_sequence_counters` and `_active_turn_ids` are keyed by
`execution_id` and never popped (unbounded growth).

It also `session.commit()`s inside the service (`context/service.py:121`),
contradicting the repository-layer "caller owns the transaction" convention
(`test_repository_layer_conventions.py` `test_no_commit_inside_repository`).

### Scope

- **method fix** — derive the next sequence from
  `SELECT COALESCE(MAX(sequence), -1) + 1 WHERE task_attempt_id = ?` inside the
  same session/transaction; drop the in-memory `_sequence_counters`. Resolve
  `turn_id` from the persisted tail rather than `_active_turn_ids`, or scope
  both dicts to a single `persist`-batch object that is discarded after use.
- **design decision (small)** — confirm commit ownership: either keep the
  internal commit and document this service as a transaction owner, or push the
  commit to the caller/job to match the convention.
- **tests** — replay simulation: persist N chunks, replay the same chunks, assert
  no `IntegrityError` and a contiguous sequence.

**Effort:** method fix + tests. No schema change.

---

## 3. Sandbox: `BaseSandboxManager.create()` leaks on partial failure — P2

### Symptom

If `_install_dependencies` or `_verify_setup` raises, the E2B sandbox stays
**alive and billing** on the remote and a stale entry remains in the
class-level `_sandboxes` singleton.

### Root cause

`create()` registers the sandbox in class-level state and then runs setup steps
with **no cleanup-on-failure** (`manager.py:327-351`). `_create_directory_structure`
*does* wrap-and-terminate on failure earlier in the same method, so the
inconsistency is self-evident in one function.

### Scope

This sits on top of a larger structural question, so two paths:

- **If `BaseSandboxManager` stays** (smoke/materialization path): **method fix** —
  wrap the three setup calls in `try/except` that calls `terminate(...)` and
  removes the `_sandboxes` entry before re-raising. Mirror the existing
  directory-structure handling. + a **test** asserting terminate-on-setup-failure.
- **Bigger question (refactor/deletion):** the live v2 execution path uses
  object-bound `Sandbox` + `E2BSandboxRuntime` and never touches this manager,
  so we maintain two sandbox stacks. Decide whether to **delete**
  `BaseSandboxManager` and migrate smoke/materialization to the v2 runtime. That
  is a separate refactor RFC; until then, apply the method fix so the legacy path
  doesn't leak.

**Effort:** method fix is small; the consolidation is a refactor RFC, tracked
separately.

---

## 4. Cross-cutting: the projection↔WAL sync invariant is unenforced — P1

### Symptom

Issue 1 was possible because nothing asserts that projection mutations and WAL
appends stay in lockstep, or that WAL replay reproduces the live projection.

### Scope — **tests** (+ a small **refactor** to make the invariant hard to break)

1. **roundtrip test** — materialize a sample, drive a representative sequence of
   `RuntimeGraphRepository` mutations (status, field, edges, dynamic spawn),
   then assert `reconstruct_sample_runtime_state_at(...)` equals the live
   projection (status per node, edge statuses, task snapshots).
2. **mutator-completeness test** — reflect over `RuntimeGraphRepository` public
   mutators and assert each appends at least one WAL event (would have failed on
   `update_node_field` today).
3. **refactor (optional, recommended)** — route every projection write through a
   single private helper that takes the projection change *and* the WAL row
   together, so "update projection without WAL" is not expressible. This is the
   structural guard that makes issue 1 unrepeatable.

---

## 5. Lower-severity hostility (track, fix opportunistically)

- **Stringly-typed graph state machine** (`status.py` literals; edges have no FK
  to nodes; acyclicity only in `graph_repository._check_no_cycle:544`). Legal
  transitions are reconstructed from scattered boolean guards in `lifecycle.py`
  / `task_management.py`. **Scope:** design decision (enum + documented
  transition table) + refactor; defer unless we touch the scheduler.
- **God modules** — `sample_lifecycle.py` (931, class misnamed `WorkflowService`
  mixing orchestration with CLI inspection), `graph_repository.py` (645),
  `task_management.py` (634). `lifecycle.py:168` carries a TODO that propagation
  "would benefit from being a service or repository method." **Scope:** refactor;
  split orchestration from inspection/query helpers. Defer; not a correctness bug.

---

## Summary table

| # | Issue | Priority | Scope |
|---|-------|----------|-------|
| 1 | `refine_task` edit dropped on rerun | P1 | event-source the fold: design decision + central write helper + method fix + tests (no schema change) |
| 2 | In-memory context sequence counter | P1 | method fix + tests |
| 3 | Sandbox `create()` partial-failure leak | P2 | method fix now; deletion is a separate refactor RFC |
| 4 | Projection↔WAL sync unenforced | P1 | tests + small refactor (single write helper) |
| 5 | Stringly-typed state machine; god modules | P3 | refactor / design decision; defer |

**Headline answer to "is persistence just a method update?":** No, but it's not
a migration either. The principled fix is to **make current state the fold of
the WAL** (authored base ⊕ typed editable fields ⊕ a namespaced `attributes`
map), with the projection demoted to a derived cache written through a single
helper. That is **one design decision + a small central refactor + a method fix
+ invariant tests** — and it supports mutating arbitrary user attributes without
destroying the timeline. The schema is fine: the dual projection/WAL model is
intentional, event kinds are free-form strings, and the legacy tables are
already gone.
