# Tech Plan: Migrate to Graph WAL as Single Source of Truth

**Status:** Draft  
**Depends on:** EVENT_WAL_AUDIT.md §4.2  
**Sequencing:** Independent of 02_INCREMENTAL_PERSISTENCE.md — can be done in parallel or after.  
**Goal:** One WAL captures all DAG state. No dual-write. `RunTaskStateEvent` is retired.

---

## 1. The Problem

Two parallel DAG state systems exist. Neither knows about the other.

### System A: Propagation layer (active — the runtime uses this)

**Files:** `propagation.py`, `RunTaskStateEvent`, `TaskExecutionService`, `TaskPropagationService`, `WorkflowInitializationService`

- `_record_state_event()` writes `RunTaskStateEvent` rows
- `get_current_task_status()` reads the latest event
- `on_task_completed()` checks dependencies and marks newly-ready tasks
- `is_workflow_complete()` / `is_workflow_failed()` check terminal state

**Write sites (exhaustive):**

| Caller | What it writes |
|---|---|
| `WorkflowInitializationService.initialize()` | `_record_state_event(PENDING)` for all tasks |
| `propagation.get_initial_ready_tasks()` | `mark_task_ready()` for root tasks |
| `TaskExecutionService.prepare()` | `mark_task_running()` |
| `TaskExecutionService.finalize_failure()` | `mark_task_failed()` |
| `propagation.on_task_completed()` | `mark_task_completed()` + `mark_task_ready()` for dependents |

**Read sites:**

| Caller | What it reads |
|---|---|
| `propagation.get_current_task_status()` | Latest `RunTaskStateEvent.new_status` |
| `propagation.on_task_completed()` | Status of all dependencies |
| `propagation.is_workflow_complete()` | Status of all tasks |
| `propagation.is_workflow_failed()` | Status of all tasks |
| `runs.py._current_task_statuses()` | All state events for API responses |
| `StateEventsQueries` | Various dashboard/API queries |

### System B: Graph layer (implemented, tested, never wired in)

**Files:** `graph_repository.py`, `graph_dto.py`, `run_graph_*` models

- `WorkflowGraphRepository` — full CRUD with append-only mutation WAL
- `initialize_from_definition()` copies definition DAG into run graph tables
- `update_node_status()`, `add_node()`, `remove_node()`, `add_edge()`, etc.
- `get_annotation_at(sequence)` — point-in-time reconstruction
- `get_mutations(since_sequence)` — incremental replay
- Acyclicity enforcement, referential integrity, actor attribution

**Current usage:** Only `test_graph_repository.py`. Zero call sites in runtime code.

---

## 2. Strategy: Graph-Primary — Replace, Don't Duplicate

Move all DAG state reads and writes to the graph layer. Stop writing `RunTaskStateEvent`.
One source of truth, no dual-write, no divergence risk.

The graph layer already has everything the propagation layer has, plus:
- Sequence-numbered mutation log (point-in-time reconstruction)
- Edge statuses (dependency resolution tracking)
- Actor attribution (who caused each transition)
- Annotation WAL (namespaced metadata with version history)
- Structural invariant enforcement (acyclicity)

The propagation functions (`mark_task_ready`, `on_task_completed`, etc.) keep their
signatures and their dependency-checking logic. What changes is the underlying
storage: instead of writing/reading `RunTaskStateEvent`, they write/read
`RunGraphNode.status` via `WorkflowGraphRepository`.

`RunTaskStateEvent` table stays in the schema (existing data) but nothing writes
to it or reads from it after migration.

---

## 3. The Migration: Write Side

### 3.1 `_record_state_event()` → `graph_repo.update_node_status()`

Current:
```python
def _record_state_event(session, run_id, task_id, new_status, ...):
    evt = RunTaskStateEvent(run_id=run_id, definition_task_id=task_id, ...)
    session.add(evt)
    session.flush()
    return evt
```

After:
```python
def _update_task_status(session, run_id, task_id, new_status, *,
                        graph_repo, graph_lookup, execution_id=None,
                        event_metadata=None) -> None:
    node_id = graph_lookup.node_id(task_id)
    graph_repo.update_node_status(
        session, run_id, node_id, new_status,
        meta=MutationMeta(
            actor="system:propagation",
            reason=event_metadata.get("error") if event_metadata else None,
        ),
    )
```

No `RunTaskStateEvent` created. The graph mutation log IS the state event log.
`update_node_status()` already records old_value/new_value, timestamp, actor,
sequence number — strictly more information than `RunTaskStateEvent` captured.

### 3.2 `mark_task_ready/running/completed/failed()` — same logic, different store

```python
def mark_task_ready(session, run_id, task_id, *,
                    graph_repo, graph_lookup):
    _update_task_status(
        session, run_id, task_id, TaskExecutionStatus.PENDING,
        graph_repo=graph_repo, graph_lookup=graph_lookup,
    )

def mark_task_running(session, run_id, task_id, execution_id, *,
                      graph_repo, graph_lookup):
    _update_task_status(
        session, run_id, task_id, TaskExecutionStatus.RUNNING,
        graph_repo=graph_repo, graph_lookup=graph_lookup,
    )

def mark_task_completed(session, run_id, task_id, execution_id, *,
                        graph_repo, graph_lookup):
    _update_task_status(
        session, run_id, task_id, TaskExecutionStatus.COMPLETED,
        graph_repo=graph_repo, graph_lookup=graph_lookup,
    )

def mark_task_failed(session, run_id, task_id, error, *,
                     execution_id=None, graph_repo, graph_lookup):
    _update_task_status(
        session, run_id, task_id, TaskExecutionStatus.FAILED,
        graph_repo=graph_repo, graph_lookup=graph_lookup,
        event_metadata={"error": error},
    )
```

Note: `graph_repo` and `graph_lookup` are now **required**, not optional.
Every caller must provide them. This is the "no half-measures" version —
if you're writing state, you're writing it to the graph.

### 3.3 `on_task_completed()` — plus edge resolution

Same dependency-checking logic, but also updates edge statuses:

```python
def on_task_completed(session, run_id, definition_id, task_id, execution_id, *,
                      graph_repo, graph_lookup):
    mark_task_completed(session, run_id, task_id, execution_id,
                        graph_repo=graph_repo, graph_lookup=graph_lookup)

    # ... existing: find candidate dependents, check all deps completed ...

    for candidate_id in newly_ready:
        # Update resolved edges
        for dep_id in dep_task_ids:
            edge_id = graph_lookup.edge_id(session, run_id, dep_id, candidate_id)
            if edge_id:
                graph_repo.update_edge_status(
                    session, run_id, edge_id, "satisfied",
                    meta=MutationMeta(actor="system:propagation"),
                )
        mark_task_ready(session, run_id, candidate_id,
                        graph_repo=graph_repo, graph_lookup=graph_lookup)

    session.commit()
    return newly_ready
```

### 3.4 Workflow initialization

```python
class WorkflowInitializationService:
    def initialize(self, command):
        with get_session() as session:
            # ... existing: load definition, load tasks ...

            # Replace per-task _record_state_event with graph initialization
            graph_repo = WorkflowGraphRepository()
            graph_repo.initialize_from_definition(
                session, command.run_id, command.definition_id,
                initial_node_status=TaskExecutionStatus.PENDING,
                initial_edge_status="pending",
                meta=MutationMeta(actor="system:workflow_init"),
            )

            # Build lookup for subsequent calls
            graph_lookup = GraphNodeLookup(session, command.run_id)

            # Mark run as EXECUTING (unchanged — this is on RunRecord, not the graph)
            run_record.status = RunStatus.EXECUTING
            run_record.started_at = utcnow()

            # Find initial ready tasks (now reads from graph)
            ready_ids = get_initial_ready_tasks(
                session, command.run_id, command.definition_id,
                graph_repo=graph_repo, graph_lookup=graph_lookup,
            )
            session.commit()
```

---

## 4. The Migration: Read Side

### 4.1 `get_current_task_status()` — read from graph node

Current:
```python
def get_current_task_status(session, run_id, task_id) -> str | None:
    stmt = (
        select(RunTaskStateEvent.new_status)
        .where(RunTaskStateEvent.run_id == run_id,
               RunTaskStateEvent.definition_task_id == task_id)
        .order_by(RunTaskStateEvent.created_at.desc())
        .limit(1)
    )
    return session.exec(stmt).first()
```

After:
```python
def get_current_task_status(session, run_id, task_id, *,
                            graph_lookup) -> str | None:
    node_id = graph_lookup.node_id(task_id)
    if node_id is None:
        return None
    node = session.exec(
        select(RunGraphNode.status).where(
            RunGraphNode.id == node_id,
            RunGraphNode.run_id == run_id,
        )
    ).first()
    return node
```

One indexed lookup instead of `ORDER BY created_at DESC LIMIT 1` on the event table.
Arguably faster.

### 4.2 `is_workflow_complete()` / `is_workflow_failed()` — read from graph nodes

```python
def is_workflow_complete(session, run_id) -> bool:
    statuses = session.exec(
        select(RunGraphNode.status).where(RunGraphNode.run_id == run_id)
    ).all()
    if not statuses:
        return True
    return all(s == TaskExecutionStatus.COMPLETED for s in statuses)

def is_workflow_failed(session, run_id) -> bool:
    statuses = session.exec(
        select(RunGraphNode.status).where(RunGraphNode.run_id == run_id)
    ).all()
    return any(s == TaskExecutionStatus.FAILED for s in statuses)
```

Simpler than the current version — no need to look up definition task IDs first,
because graph nodes are already per-run.

### 4.3 `runs.py._current_task_statuses()` — read from graph nodes

Current: queries `RunTaskStateEvent` and deduplicates to find latest status per task.

After:
```python
def _current_task_statuses(session, run_id) -> dict[UUID, str]:
    nodes = session.exec(
        select(RunGraphNode.definition_task_id, RunGraphNode.status)
        .where(RunGraphNode.run_id == run_id)
    ).all()
    return {defn_id: status for defn_id, status in nodes if defn_id is not None}
```

No deduplication needed — `RunGraphNode.status` is always the current value.

### 4.4 `StateEventsQueries` — replace with graph queries

`StateEventsQueries` in `queries.py` has three methods:
- `list_by_run()` → `get_mutations(run_id)` on the graph repo
- `get_by_task()` → `get_mutations(run_id)` filtered by `target_id`
- `get_by_event_type()` → `get_mutations(run_id)` filtered by `mutation_type`

Or: deprecate `StateEventsQueries` and replace callers with direct graph repo queries.

---

## 5. The Node ID Lookup (unchanged from before)

```python
# ergon_core/core/runtime/services/graph_lookup.py

class GraphNodeLookup:
    """Maps definition_task_id → run_graph_node.id for one run.
    Also caches edge lookups.
    """

    def __init__(self, session: Session, run_id: UUID) -> None:
        node_rows = session.exec(
            select(RunGraphNode.id, RunGraphNode.definition_task_id)
            .where(RunGraphNode.run_id == run_id)
        ).all()
        self._nodes: dict[UUID, UUID] = {
            defn_id: node_id for node_id, defn_id in node_rows if defn_id is not None
        }

        edge_rows = session.exec(
            select(RunGraphEdge.id, RunGraphEdge.source_node_id, RunGraphEdge.target_node_id)
            .where(RunGraphEdge.run_id == run_id)
        ).all()
        self._edges: dict[tuple[UUID, UUID], UUID] = {
            (src, tgt): eid for eid, src, tgt in edge_rows
        }

    def node_id(self, definition_task_id: UUID) -> UUID | None:
        return self._nodes.get(definition_task_id)

    def edge_id_by_nodes(self, source_node_id: UUID, target_node_id: UUID) -> UUID | None:
        return self._edges.get((source_node_id, target_node_id))

    def edge_id(self, source_defn_id: UUID, target_defn_id: UUID) -> UUID | None:
        src = self.node_id(source_defn_id)
        tgt = self.node_id(target_defn_id)
        if src is None or tgt is None:
            return None
        return self.edge_id_by_nodes(src, tgt)
```

Batch-loads both nodes and edges in two queries at construction time.
No per-edge queries during `on_task_completed()`.

---

## 6. What Gets Retired

### Stop writing:
- `_record_state_event()` — deleted, replaced by `_update_task_status()`
- `RunTaskStateEvent` rows — no new rows created after migration

### Stop reading:
- `get_current_task_status()` via `RunTaskStateEvent` — reads `RunGraphNode.status` instead
- `_current_task_statuses()` via state events — reads graph nodes instead
- `StateEventsQueries` — deprecated, replaced by graph repo queries

### Keep in schema but freeze:
- `run_task_state_events` table — existing data preserved for historical runs
- `RunTaskStateEvent` model — kept for backward compatibility with old data reads, but not imported by propagation code

### Remove from TelemetryRepository:
- `record_state_event()` method
- `get_state_events()` method (or keep for legacy reads only)

---

## 7. What This Enables

Same as before — one WAL captures everything:

1. **Every node status transition** with sequence numbers, timestamps, actor, old/new values
2. **Every edge resolution** — pending → satisfied
3. **Point-in-time reconstruction** — `get_mutations(since_sequence=N)` or `get_annotation_at(sequence=N)`
4. **Single source of truth** — no divergence between two parallel systems
5. **Ready for dynamic workflow mutation** — the graph layer already supports `add_node()`, `remove_node()`, `add_edge()` at runtime, which `RunTaskStateEvent` never could

Combined with incremental persistence (Redis → PG):

```
Given run_id and a point in time:
  1. Graph mutations → DAG topology and every task's status
  2. RunGenerationTurn rows → every turn every agent completed
  3. RunStreamEvent rows → every token/tool event at sub-turn granularity
  4. Thread messages → every inter-agent message
  5. RunTaskEvaluation → every evaluation score

= Complete, lossless reconstruction of a multi-agent execution.
```

---

## 8. What We Don't Know

1. **Sequence number contention under concurrency.** `_next_sequence()` uses `SELECT MAX + 1`.
   Under concurrent task completions this could gap or collide. Options: (a) PG
   `GENERATED ALWAYS AS IDENTITY`, (b) `SELECT ... FOR UPDATE`, (c) accept gaps.
   Recommendation: (c) — gaps are harmless for ordering and don't affect correctness.

2. **Performance of `is_workflow_complete()` reading graph nodes vs state events.**
   The graph version scans `run_graph_nodes WHERE run_id = ?` — should be comparable
   to the current version which scans `run_task_state_events WHERE run_id = ?` and
   deduplicates. Probably faster (fewer rows, no dedup). But worth measuring.

3. **Dashboard compatibility.** The Next.js dashboard reads state events via the API.
   The API endpoints in `runs.py` need to return the same shape — but sourced from
   graph nodes instead of state events. The DTO shape (`RunTaskStatusDto` or equivalent)
   shouldn't change; only the query backing it changes.

4. **Existing test compatibility.** `test_propagation.py` tests the mark_* functions
   and verifies `RunTaskStateEvent` rows. These tests need to be rewritten to verify
   `RunGraphNode.status` and `RunGraphMutation` rows instead.

---

## 9. Implementation Order

### Phase 1: Wire graph initialization + build lookup (1 day)

1. Call `graph_repo.initialize_from_definition()` in `WorkflowInitializationService`
2. Implement `GraphNodeLookup` (batch-loads nodes and edges)
3. Test: after workflow start, graph tables are populated

### Phase 2: Migrate writes (2 days)

1. Replace `_record_state_event()` with `_update_task_status()` (graph write)
2. Make `graph_repo` + `graph_lookup` required params on all `mark_*` functions
3. Update `on_task_completed()` to update edge statuses
4. Wire through all service callers (`TaskExecutionService`, `TaskPropagationService`, `WorkflowInitializationService`)
5. Stop importing `RunTaskStateEvent` in propagation code

### Phase 3: Migrate reads (1 day)

1. Rewrite `get_current_task_status()` to read `RunGraphNode.status`
2. Rewrite `is_workflow_complete()` / `is_workflow_failed()` to read graph nodes
3. Rewrite `runs.py._current_task_statuses()` to read graph nodes
4. Deprecate or remove `StateEventsQueries`

### Phase 4: Update tests + cleanup (1 day)

1. Rewrite `test_propagation.py` to verify `RunGraphNode.status` and `RunGraphMutation` rows
2. Remove `record_state_event()` from `TelemetryRepository`
3. Add migration test: graph mutations contain all the information state events used to carry
4. Verify existing e2e and integration tests still pass

---

## 10. File Map

### ADD — new files

```
ergon_core/ergon_core/core/runtime/services/graph_lookup.py
    - GraphNodeLookup class (batch-loaded node + edge mapping)

tests/state/test_graph_migration.py
    - graph initialized on workflow start
    - mark_* writes graph mutations (not state events)
    - edge statuses updated on dependency resolution
    - point-in-time reconstruction from graph mutations
    - is_workflow_complete/failed reads from graph nodes
    - _current_task_statuses reads from graph nodes
```

### MODIFY — existing files

```
# ── Propagation (the big change) ─────────────────────────

ergon_core/ergon_core/core/runtime/execution/propagation.py
    - delete _record_state_event()
    + add _update_task_status() (writes to graph via graph_repo)
    ~ mark_task_ready/running/completed/failed: graph_repo + graph_lookup now required
    ~ on_task_completed: add edge status updates
    ~ get_current_task_status: read from RunGraphNode.status
    ~ is_workflow_complete / is_workflow_failed: read from RunGraphNode.status
    ~ get_initial_ready_tasks: use graph_repo + graph_lookup
    - remove all RunTaskStateEvent imports

# ── Services (wire graph_repo + lookup) ───────────────────

ergon_core/ergon_core/core/runtime/services/workflow_initialization_service.py
    + call graph_repo.initialize_from_definition()
    + create GraphNodeLookup
    + pass to get_initial_ready_tasks
    - remove _record_state_event calls

ergon_core/ergon_core/core/runtime/services/task_execution_service.py
    + create graph_repo + lookup in prepare() and finalize_failure()
    + pass to mark_task_running() and mark_task_failed()

ergon_core/ergon_core/core/runtime/services/task_propagation_service.py
    + create graph_repo + lookup in propagate() and propagate_failure()
    + pass to on_task_completed()

# ── API reads ─────────────────────────────────────────────

ergon_core/ergon_core/core/api/runs.py
    ~ _current_task_statuses(): read from RunGraphNode instead of RunTaskStateEvent
    - remove RunTaskStateEvent import

ergon_core/ergon_core/core/persistence/queries.py
    - deprecate StateEventsQueries (or rewrite to query graph mutations)

# ── Repository cleanup ────────────────────────────────────

ergon_core/ergon_core/core/persistence/telemetry/repositories.py
    - remove record_state_event() method
    - remove get_state_events() method (or keep for legacy data access)

# ── Tests ─────────────────────────────────────────────────

tests/state/test_propagation.py
    ~ rewrite assertions: check RunGraphNode.status and RunGraphMutation rows
    ~ instead of checking RunTaskStateEvent rows
```

### UNCHANGED

```
ergon_core/ergon_core/core/runtime/services/graph_repository.py   # already complete
ergon_core/ergon_core/core/persistence/graph/models.py            # already complete
ergon_core/ergon_core/core/runtime/services/graph_dto.py          # already complete
tests/state/test_graph_repository.py                              # still passes

ergon_core/ergon_core/core/runtime/inngest/*.py                   # no changes needed
ergon_core/ergon_core/core/persistence/telemetry/models.py        # RunTaskStateEvent stays (frozen)
```

### FROZEN (kept but unused after migration)

```
RunTaskStateEvent model          — kept in schema, no new writes
run_task_state_events table      — existing data preserved
StateEventsQueries               — deprecated, callers rewritten
TelemetryRepository.record_state_event()  — removed
TelemetryRepository.get_state_events()    — removed or kept for legacy reads
```

---

## 11. Interaction with Incremental Persistence Plan

These two plans are independent. They touch different layers:

- **Incremental persistence** touches: worker interface, TurnSink, Redis, `worker_execute.py`, `RunGenerationTurn`
- **State unification** touches: propagation functions, services, `RunGraphMutation`, `WorkflowGraphRepository`

No file conflicts. They can be implemented in parallel or in either order.

Once both are done, the combined result is: lossless reconstruction of DAG state +
per-turn agent behavior + token-level forensics, all from PG alone.

---

## 12. Open Questions

1. **Sequence number gaps under concurrency.** Accept them (recommendation) or switch
   to PG-native `IDENTITY` column. Gaps don't affect correctness — ordering is still
   total within a run.

2. **Legacy data migration.** Old runs have `RunTaskStateEvent` rows but no graph rows.
   Options: (a) backfill: write a one-time script that replays state events into graph
   tables for historical runs, (b) leave them: old runs use the old query path, new runs
   use graph. Recommendation: (b) for now. Backfill is a nice-to-have, not blocking.

3. **`definition_task_id` on `RunGraphNode` is nullable.** Nodes added dynamically at
   runtime (future: dynamic workflow mutation) won't have a definition task ID. The
   lookup handles this (`if defn_id is not None`), but `get_current_task_status()` needs
   to work for both definition-backed and dynamically-added tasks. Worth verifying the
   query handles both cases.
