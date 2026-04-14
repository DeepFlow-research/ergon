# Fix Plan: Dashboard Snapshot Parity + Generation Logging

**Status:** Draft  
**Related docs:**
- `docs/event-wal/02_INCREMENTAL_PERSISTENCE.md` — generation turn persistence (generation logging fix lives here)
- `docs/event-wal/STATE_UNIFICATION_PLAN.md` — graph WAL as single source of truth (upstream dependency)

**Goal:** After a page reload, `GET /runs/{run_id}` returns exactly the same run state that the live WebSocket stream would have built — including dynamic tasks, generation turns, and the timeline. Postgres is the single source of truth; the in-memory socket store is a read-through cache.

---

## 1. Problem Statement

The dashboard has two paths to run state:

| Path | Source | Used when |
|------|--------|-----------|
| REST snapshot | `GET /runs/{run_id}` → `build_run_snapshot` → PG | Page load / reload |
| Live stream | WebSocket `graph:mutation`, `task:status`, `generation:turn` events | While the run is active |

These two paths currently diverge in four ways. After reload, the user sees an incomplete or empty dashboard.

---

## 2. The Four Gaps

### Gap 1 — Dynamic tasks invisible on reload

**Root cause:** `build_run_snapshot` reads only `ExperimentDefinitionTask` (the static workflow definition). Dynamic nodes — spawned at runtime and stored in `RunGraphNode` with `definition_task_id IS NULL` — are never queried.

**Live stream behaviour:** Every `graph:mutation node.added` event (including dynamic nodes) is applied via `applyGraphMutation`, keyed by `RunGraphNode.id`.

**Impact:** After reload, the task DAG is missing any nodes added dynamically. The graph renders the skeleton from the definition only.

### Gap 2 — Canonical task key is inconsistent

**Root cause:** The REST snapshot currently keys the task map by `ExperimentDefinitionTask.id`. The live stream keys every task (static and dynamic) by `RunGraphNode.id` — because `graph:mutation` events use `target_id = RunGraphNode.id`. These are different UUIDs.

**Impact:** Even for static tasks, `executionsByTask`, `resourcesByTask`, and `evaluationsByTask` built from the REST snapshot may not match task IDs the frontend uses after applying live mutations. The per-task data panels are unreliable.

**Decision:** Use `RunGraphNode.id` as the canonical task key everywhere — in the snapshot task map, in execution/resource/evaluation keying, and in all helper functions. This aligns with the live stream and with the graph layer's identity model.

### Gap 3 — `generation_turns_by_task` is never populated

**Root cause:** `RunSnapshotDto.generation_turns_by_task` has `default_factory=dict` and `build_run_snapshot` never sets it. `RunGenerationTurn` rows are not loaded in the snapshot builder at all.

**Impact:** The generation turns panel is structurally impossible to populate on reload — always blank regardless of what's in PG.

### Gap 4 — `GET /runs/{run_id}/mutations` endpoint does not exist

**Root cause:** `RunGraphMutation` rows are written to PG by `WorkflowGraphRepository` on every mutation, but there is no FastAPI route that reads them. The frontend Timeline feature calls `/api/runs/{runId}/mutations` which proxies to this missing endpoint.

**Impact:** The Timeline tab always 502s. The mutation scrubber cannot function.

---

## 3. The Fix — Two Phases

These are separated because Phase 1 is entirely backend API changes (no breaking changes, no new infrastructure) and Phase 2 is a larger architectural change to the worker interface already planned in `02_INCREMENTAL_PERSISTENCE.md`.

---

## Phase 1: Snapshot Parity (immediate)

All changes are in `ergon_core/ergon_core/core/api/runs.py` except where noted.

### 1.1 Replace `_build_task_tree` with a node+edge-based builder

**Drop `ExperimentDefinitionTask` from the task map entirely.**

`initialize_from_definition()` in `WorkflowGraphRepository` already copies every definition task into `RunGraphNode` when a run starts. So for any initialized run, all tasks — static and dynamic — already exist as `RunGraphNode` rows with `task_key`, `description`, `status`, and `assigned_worker_key`. There is no information in `ExperimentDefinitionTask` that isn't already on the node.

Replace `_build_task_tree` with a new function that takes only nodes and edges:

```python
def _build_task_map(
    nodes: list[RunGraphNode],
    edges: list[RunGraphEdge],
    worker_by_binding: dict[str, ExperimentDefinitionWorker],
    task_timestamps: dict[UUID, tuple[datetime | None, datetime | None]],
) -> tuple[dict[str, RunTaskDto], str, int, int, int, int, int]:
    """Build the flat task map from graph nodes and edges.

    Returns (task_map, root_node_id, total, total_leaf, completed, failed, running).
    """
    if not nodes:
        return {}, "", 0, 0, 0, 0, 0

    # Build initial task map — all nodes start as leaves at level 0
    task_map: dict[str, RunTaskDto] = {}
    for node in nodes:
        nid = str(node.id)
        worker = worker_by_binding.get(node.assigned_worker_key or "")
        started_at, completed_at = task_timestamps.get(node.id, (None, None))
        task_map[nid] = RunTaskDto(
            id=nid,
            name=node.task_key,
            description=node.description,
            status=node.status,
            parent_id=None,
            child_ids=[],
            depends_on_ids=[],
            is_leaf=True,
            level=0,
            assigned_worker_id=str(worker.id) if worker else None,
            assigned_worker_name=node.assigned_worker_key,
            started_at=started_at,
            completed_at=completed_at,
        )

    # Wire parent/child and dependency edges (same logic as applyEdgeAdded)
    for edge in edges:
        src = str(edge.source_node_id)
        tgt = str(edge.target_node_id)
        source_task = task_map.get(src)
        target_task = task_map.get(tgt)
        if source_task is None or target_task is None:
            continue

        if target_task.parent_id is None:
            # parent → child edge
            task_map[tgt] = target_task.model_copy(
                update={"parent_id": src, "level": source_task.level + 1}
            )
            task_map[src] = source_task.model_copy(
                update={"child_ids": [*source_task.child_ids, tgt], "is_leaf": False}
            )
        elif target_task.parent_id != src:
            # dependency edge
            task_map[tgt] = target_task.model_copy(
                update={"depends_on_ids": [*target_task.depends_on_ids, src]}
            )

    # Find root (no parent), compute counts from leaves
    root_id = next((t.id for t in task_map.values() if t.parent_id is None), "")
    total = len(task_map)
    leaves = [t for t in task_map.values() if t.is_leaf]
    total_leaf = len(leaves)
    completed = sum(1 for t in leaves if t.status == "completed")
    failed = sum(1 for t in leaves if t.status == "failed")
    running = sum(1 for t in leaves if t.status == "running")

    return task_map, root_id, total, total_leaf, completed, failed, running
```

`build_run_snapshot` now loads nodes and edges instead of definition tasks and dependencies:

```python
nodes_stmt = select(RunGraphNode).where(RunGraphNode.run_id == run_id)
nodes = list(session.exec(nodes_stmt).all())

edges_stmt = select(RunGraphEdge).where(RunGraphEdge.run_id == run_id)
edges = list(session.exec(edges_stmt).all())
```

No `ExperimentDefinitionTask`, no `ExperimentDefinitionTaskDependency`, no definition-to-node ID mapping step.

`_current_task_statuses` is also eliminated — status is already on each `RunGraphNode` row, read directly in `_build_task_map`.

### 1.2 Fix execution, resource, and evaluation keying

**Always use `ex.node_id`:**

```python
execution_task_map: dict[UUID, UUID] = {
    ex.id: ex.node_id for ex in executions if ex.node_id is not None
}
```

The `if ex.node_id is not None` guard exists because `RunTaskExecution.node_id` is a nullable column. It is nullable for three reasons:
1. The legacy `TelemetryRepository.create_task_execution()` path never sets `node_id` — only `definition_task_id`.
2. `GraphNodeLookup.node_id()` can return `None` if called before the graph is initialized.
3. Historical rows in the database predate the `node_id` column.

The new execution service paths (`_prepare_node`, `_prepare_definition`) always set `node_id`, so executions from current code will always have it. Executions where `node_id IS NULL` are legacy rows; they will not appear in `execution_task_map` and their turns will be silently dropped from `generation_turns_by_task`. This is acceptable for now.

**Schema tightening (not in Phase 1):** Once `STATE_UNIFICATION_PLAN.md` retires the `RunTaskStateEvent` propagation path, `TelemetryRepository.create_task_execution()` can be updated to require `node_id`. The DB column stays nullable for historical rows, but the application-layer type becomes `node_id: UUID` (non-optional). This is tracked alongside the type-tightening work in `02_INCREMENTAL_PERSISTENCE.md` §6.3.

`_task_keyed_executions` and `_task_keyed_resources` key by `str(ex.node_id)` — matching the task map keys from step 1.1.

`_task_keyed_evaluations` currently keys by `str(ev.definition_task_id)`. Since evaluations link to definition tasks (not nodes), a secondary lookup is needed to remap:

```python
# Built from nodes loaded in step 1.1
defn_to_node: dict[UUID, UUID] = {
    n.definition_task_id: n.id
    for n in nodes
    if n.definition_task_id is not None
}
```

Then in `_task_keyed_evaluations`: key by `str(defn_to_node.get(ev.definition_task_id))` instead of `str(ev.definition_task_id)`.

### 1.4 Populate `generation_turns_by_task`

Load `RunGenerationTurn` rows for the run and group by the task's `node_id` via the execution lookup:

```python
# In build_run_snapshot, after loading executions:

gen_turns_stmt = (
    select(RunGenerationTurn)
    .where(RunGenerationTurn.run_id == run_id)
    .order_by(RunGenerationTurn.task_execution_id, RunGenerationTurn.turn_index)
)
gen_turns = list(session.exec(gen_turns_stmt).all())

gen_turns_by_task: dict[str, list[RunGenerationTurnDto]] = defaultdict(list)
for turn in gen_turns:
    task_key = execution_task_map.get(turn.task_execution_id)
    if task_key is None:
        continue
    gen_turns_by_task[str(task_key)].append(
        RunGenerationTurnDto(
            id=str(turn.id),
            task_execution_id=str(turn.task_execution_id),
            worker_binding_key=turn.worker_binding_key,
            turn_index=turn.turn_index,
            prompt_text=turn.prompt_text,
            raw_response=turn.raw_response,
            response_text=turn.response_text,
            tool_calls=turn.tool_calls_json,
            tool_results=turn.tool_results_json,
            policy_version=turn.policy_version,
            has_logprobs=turn.token_ids_json is not None,
            created_at=turn.created_at.isoformat() if turn.created_at else None,
        )
    )
```

Then pass `generation_turns_by_task=dict(gen_turns_by_task)` to `RunSnapshotDto(...)`.

### 1.5 Add `GET /{run_id}/mutations` endpoint

```python
@router.get("/{run_id}/mutations", response_model=list[RunGraphMutationDto])
def get_mutations(run_id: UUID) -> list[RunGraphMutationDto]:
    """Return the append-only mutation log for a run, ordered by sequence.

    Used by the Timeline scrubber to replay DAG state at any point in time.
    """
    with get_session() as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        stmt = (
            select(RunGraphMutation)
            .where(RunGraphMutation.run_id == run_id)
            .order_by(RunGraphMutation.sequence)
        )
        mutations = list(session.exec(stmt).all())

    return [
        RunGraphMutationDto(
            id=str(m.id),
            run_id=str(m.run_id),
            sequence=m.sequence,
            mutation_type=m.mutation_type,
            target_type=m.target_type,
            target_id=str(m.target_id),
            actor=m.actor,
            old_value=m.old_value,
            new_value=m.new_value,
            reason=m.reason,
            created_at=m.created_at.isoformat(),
        )
        for m in mutations
    ]
```

`RunGraphMutationDto` needs adding to `schemas.py`. Its field names and types must match the frontend's `GraphMutationDtoSchema` in `graphMutations.ts` exactly.

### Phase 1 file map

```
ergon_core/ergon_core/core/api/runs.py
    - _build_task_tree(): deleted
    - _current_task_statuses(): deleted (status now read directly from RunGraphNode in _build_task_map)
    + _build_task_map(nodes, edges, worker_by_binding, task_timestamps): new, replaces both
    ~ _task_keyed_executions(): always use ex.node_id
    ~ _task_keyed_resources(): execution_task_map keyed by node_id
    ~ _task_keyed_evaluations(): remap via defn_to_node lookup
    ~ build_run_snapshot(): load RunGraphNode + RunGraphEdge instead of ExperimentDefinitionTask + deps
    ~ build_run_snapshot(): build defn_to_node map for evaluation remapping
    ~ build_run_snapshot(): execution_task_map keyed by node_id
    ~ build_run_snapshot(): load RunGenerationTurn, populate generation_turns_by_task
    + GET /{run_id}/mutations endpoint

ergon_core/ergon_core/core/api/schemas.py
    + RunGraphMutationDto (matches GraphMutationDtoSchema in the frontend)
```

---

## Phase 2: Generation Logging (incremental turn persistence)

**Status: Already implemented.** `02_INCREMENTAL_PERSISTENCE.md` has been fully shipped. This section is kept for context on why Phase 1 alone gives partial parity and what the implemented system provides.

### Why Phase 1 alone gives only partial parity

Phase 1 populates `generation_turns_by_task` from whatever `RunGenerationTurn` rows exist in PG at snapshot time. If turns were still batch-written post-completion, reload during a live run would return `generation_turns_by_task: {}` because no rows would exist yet.

### What the implemented system delivers

`Worker.execute()` is an async generator. The runtime calls `GenerationTurnRepository.persist_single()` for each yielded `GenerationTurn` and notifies `DashboardEmitter.on_turn_persisted()` immediately after each commit. This means:

- Each turn is in PG the moment it completes — before the next turn starts
- `generation:turn` socket events are emitted per-turn (not batched post-completion)
- Reload at any point during execution shows all turns completed so far
- Worker crash loses at most one in-flight turn; prior turns are marked `execution_outcome="failure"` via `mark_execution_outcome()`

With Phase 2 already in place, Phase 1's population of `generation_turns_by_task` from PG achieves full live parity immediately — there is no gap between PG state and the socket stream for generation turns.

---

## 4. Sequencing

```
Phase 2 (generation logging) — DONE (02_INCREMENTAL_PERSISTENCE.md shipped)
  ✓ Worker.execute() async generator
  ✓ Per-turn persist_single() in worker_execute_fn
  ✓ Per-turn generation:turn dashboard event via repository listener
  ✓ execution_outcome tracking + crash recovery

Phase 1 (snapshot parity) — implement now
  ├── 1.1  Replace _build_task_tree with _build_task_map(nodes, edges)
  ├── 1.2  Fix execution/resource/evaluation keying to use node_id
  ├── 1.3  Dynamic nodes included automatically (no special handling)
  ├── 1.4  Populate generation_turns_by_task
  └── 1.5  Add mutations endpoint
```

Phase 2 is already done. Phase 1 can ship immediately and independently — no new infrastructure required.

---

## 5. Invariant to Verify

After both phases, this test should pass:

```
1. Start a run
2. Fetch GET /runs/{run_id} mid-execution (REST snapshot)
3. Fetch sync:run from socket (in-memory store)
4. Assert: tasks maps are equal (same keys, same statuses)
5. Assert: generationTurnsByTask is equal (same turns)
6. Assert: GET /runs/{run_id}/mutations returns non-empty list
7. Reload the page and assert the UI matches the live view
```

---

## 6. What This Doesn't Change

- **`sync:run`** — still serves the in-memory store. Its role is "fast first paint for runs the server has seen since startup." REST snapshot is the authoritative fallback.
- **Socket event stream** — no changes. `graph:mutation`, `task:status`, `generation:turn` etc. are unchanged.
- **Frontend** — no changes required. `deserializeRunState` already reads `generationTurnsByTask`; `deserializeTask` already accepts the `RunTask` shape. The mutations proxy route already exists. Once the backend is correct, the frontend works.
- **`STATE_UNIFICATION_PLAN.md`** — Phase 1 works regardless of whether that migration has happened. `RunGraphNode.status` is already being written (it's how `_current_task_statuses` works today). That plan improves the write path, not the read path we're fixing here.
