# 04 — Persistence

## 1. Purpose

The persistence layer owns durable state for runs, tasks, graph mutations,
context events, resources, evaluations, and telemetry. Postgres is the
single source of truth; all in-memory structures (the dashboard store,
runtime caches) are derived views that can be rebuilt from the database at
any time. Disaster recovery is Postgres backups — not log replay.

The layer is intentionally split into two shapes. **Mutable tables** carry
the current state of a run and serve fast indexed reads for scheduling and
rehydration. **Append-only logs** carry the history of how the run reached
that state, and exist for audit, debugging, and RL trajectory extraction.
The mutable tables are the operational truth; the mutation log is a diary,
not a recovery source.

## 2. Core abstractions

The graph repository (`WorkflowGraphRepository`) is the only writer for
graph state. Everything else — runtime workers, services, dashboards —
either reads the mutable rows or submits mutations through the repository.

Design-load-bearing facts:

- **Mutable state** lives in the run graph node/edge tables plus the
  per-attempt execution, evaluation, and resource tables. These are the
  scheduling read path.
- **Append-only logs** are the mutation log (every graph state change) and
  the context event log (one row per message in a generation turn). These
  are audit / RL material.
- **Annotations** are a namespaced metadata table attached to nodes and
  edges. Core reserves the `"payload"` namespace; every other namespace is
  an extension seam (see §5).
- **Definition-side rows** (`ExperimentDefinitionTask` and its dependency
  table) are immutable after creation. Runtime reads them to seed the
  initial graph and never mutates them.
- **`RunTaskStateEvent` is legacy.** The table is frozen. New code MUST
  NOT read or write it; rehydration of legacy runs is the only permitted
  read.

See the Code map below for where each table lives.

## 3. Control flow

### Writes

All graph state changes go through `WorkflowGraphRepository`:

```
runtime / worker
      |
      v
WorkflowGraphRepository.apply_mutation(meta=MutationMeta(actor, reason), ...)
      |
      | 1. append new row to the mutation log (sequence += 1)
      | 2. update the corresponding node / edge row
      | 3. return the applied mutation
      v
Postgres (single transaction)
      |
      v
DashboardEmitter.graph_mutation(...)   (out-of-transaction, best effort)
```

### Initial graph construction

At run-creation time, the initialization service reads the definition-side
rows and eagerly creates every statically-declared node and edge. Task
payloads are attached as annotations in the core-reserved `"payload"`
namespace.

### Manager-spawned subtasks (dynamic graph growth)

The graph is append-only at the row level: new nodes and edges can enter
after initialization without slot reservation. Manager workers grow the
graph by submitting mutations through `WorkflowGraphRepository` under a
`MutationMeta(actor="manager-worker", reason="manager_decision")`. The
runtime then fires Inngest `TaskReadyEvent`s for any no-deps roots of the
new subgraph; those nodes are routed through the same execution path as
statically-declared nodes.

There is no pre-allocation of capacity or reservation of slots. Every
dynamic node is a normal node row committed inside the same mutation-log
transaction as the originating `node.added` entry.

### Reads

- Runtime reads the mutable node/edge rows for scheduling decisions.
- Dashboard rehydration reads a full run snapshot composed from the
  mutable tables directly. It does NOT replay the mutation log; the
  mutable tables are the read path.
  ([`ergon_core/core/api/runs.py:343`](../../ergon_core/ergon_core/core/api/runs.py).)
- RL extraction consumes the mutation log and context event log in
  sequence order to reconstruct trajectories.

## 4. Invariants

- **Mutation log is append-only with dense, monotonic sequence.** Every
  DAG state change writes a new row; no gaps, no updates, no deletes. Old
  and new values round-trip so the diary is reconstructible, but
  consumers treat this as audit / RL material rather than the recovery
  source of truth. Enforced by `WorkflowGraphRepository`.
- **All graph state writes go through `WorkflowGraphRepository`** with a
  `MutationMeta(actor=..., reason=...)`. Raw `session.add` on live state
  is an anti-pattern (see §6).
- **`RunTaskStateEvent` is frozen.** No new writes. Reads permitted only
  for legacy-run rehydration. New code uses the mutation log plus node
  status instead.
- **Alembic revisions are the only schema-change path.** Every migration
  ships in a reviewed PR. The revision chain is preserved and NOT
  squashed: each revision documents the intent of its PR, and the chain
  is the audit trail for schema evolution. Migrations are LLM-generated
  (autogen or authored by hand) and reviewed like any other code.
- **Context events are forever-append today.** No pruning job exists and
  none is planned in the near term; retention is "keep everything". Per-run
  TTL is an open question (see §7).
- **Event ordering within a turn is deterministic.** The tuple
  (run_id, task_id, turn_id, event_index) is unique for context events.
- **Namespace `"payload"` on annotations is core-reserved.** All other
  namespaces are available for extension code.

## 5. Extension points

- **Graph annotations — user metadata seam.** The generic
  `WorkflowGraphRepository.set_annotation(target_id, namespace, value)`
  entry point is a first-class public extension surface for user-written
  experiment code. Attach arbitrary structured metadata to nodes and
  edges — manager/worker debate transcripts, refinement history,
  experiment-specific scheduler hints, anything that benefits from being
  co-located with the graph but does not belong in the mutation log. The
  pattern is:

  ```python
  repo.set_annotation(
      target_id=node_id,
      namespace="my_experiment.debate",
      value={"round": 2, "transcript": [...]},
  )
  ```

  Claim a unique namespace per extension. Core reserves `"payload"`;
  everything else is yours. This is NOT an internal helper — third-party
  experiment code is expected to write annotations.

- **Dynamic subgraph injection via the subtask lifecycle toolkit.** Any
  worker (including custom managers supplied by an experiment) can grow
  the live DAG. The contract: the toolkit translates worker intent into
  `WorkflowGraphRepository` mutations under a
  `MutationMeta(actor="manager-worker", reason="manager_decision")`, and
  the runtime fires Inngest `TaskReadyEvent`s for new roots. Extensions
  that need to steer scheduling at runtime should prefer this path over
  hand-rolled graph writes.

- **New mutation kinds.** Extend the mutation payload discriminator with
  a new variant and a corresponding method on `WorkflowGraphRepository`.
  Do not inline ad-hoc JSON blobs into existing mutation kinds.

- **New tables.** Add an Alembic revision under the migrations tree.
  Downstream consumers (dashboard, RL extraction) must be updated in the
  same PR or behind a feature flag.

- **Custom snapshot views.** Compose on top of the run-snapshot builder;
  do not duplicate the rehydration logic.

## 6. Anti-patterns

- **Writing to `RunTaskStateEvent`.** The table is frozen legacy. Any new
  write is a regression; use the mutation log plus node status.
- **Bypassing `WorkflowGraphRepository` for graph writes.** All writes
  MUST append to the mutation log; raw `session.add` on a graph node or
  `UPDATE run_graph_node SET status = ...` breaks the audit trail and
  desynchronises consumers.
- **Reading state by replaying the mutation log in the runtime hot path.**
  The mutation log is audit and RL material. Scheduling and rehydration
  read the mutable tables. Replay-as-read is slow and defeats the split.
- **Schema changes without an Alembic revision.** Even additive changes
  must have a migration so environments converge. Squashing the existing
  revision chain is also forbidden — each revision is documentation for
  the PR that introduced it.
- **Overloading annotation namespace `"payload"` from user code.** Pick a
  unique namespace; `"payload"` is reserved for task payloads written by
  the initialization service.
- **Emitting a dashboard event from inside the DB transaction.** The
  emitter is best-effort and out-of-band; coupling it to commit semantics
  risks transaction rollback leaving the dashboard with phantom state.

## 7. Follow-ups

Open questions and in-flight work that touch this layer:

- **Context event retention shape.** Forever-append is the intentional
  default today, but a per-run user-configurable TTL is expected
  eventually. No RFC exists yet; when drafted it will cover retention
  policy, optional tiered storage, and interaction with RL trajectory
  extraction. Track as a future RFC rather than a bug.
- **`RunTaskStateEvent` deletion.** An RFC is in flight to remove the
  legacy table outright. Until it lands, the frozen-table invariant
  stands; on merge, drop the legacy entry from §2 and the matching
  anti-pattern bullet.
- **Production migration policy.** The system is local-only today, so
  there is no formal rule on who runs Alembic against a shared
  environment. When a hosted deployment appears, this section will gain
  a deployment-time policy (who runs `alembic upgrade head`, rollback
  expectations, staging parity).

## Code map

Compact reference for where the tables and services live. Not load-bearing
for the design argument above — here as onboarding material.

| Concern | Location |
|---|---|
| Graph node / edge / annotation / mutation models | `ergon_core/core/persistence/graph/models.py` |
| Run / execution / evaluation / resource / thread models | `ergon_core/core/persistence/telemetry/models.py` |
| Context event model | `ergon_core/core/persistence/context/models.py` |
| Experiment definition models | `ergon_core/core/persistence/definitions/` |
| Graph repository (sole writer) | `ergon_core/core/persistence/graph/` (`WorkflowGraphRepository`) |
| Initial graph construction | `ergon_core/core/runtime/services/workflow_initialization_service.py` |
| Subtask lifecycle toolkit | `ergon_builtins/tools/subtask_lifecycle_toolkit.py` |
| Task management service (dynamic subtask entry) | `ergon_core/core/runtime/services/task_management_service.py` |
| Run snapshot builder | `ergon_core/core/api/runs.py` (`build_run_snapshot`) |
| Alembic revisions | `ergon_core/migrations/versions/` |
