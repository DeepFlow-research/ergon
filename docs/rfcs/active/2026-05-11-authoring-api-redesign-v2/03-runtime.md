# 03 — Runtime

> What happens inside the rollout container: how a `Sandbox` subclass
> gets provisioned, how the lifecycle hub tracks live sandboxes, and
> what `WorkerContext` exposes to a running worker — the single public
> runtime surface for v1, with the curated single-target methods most
> workers need. Toolkits or other consumers that need batch ops or
> CLI-tier control reach into the internal services
> (`TaskManagementService` / `TaskInspectionService` /
> `RunResourceRepository`) directly today; promoting those to the
> public surface is deferred (see
> [`09-implementation-plan.md`](09-implementation-plan.md) "What's deferred" and
> [`08-decisions-log.md`](08-decisions-log.md) "Layered public runtime
> API" under Alternatives considered).
>
> See [`01-api-surface.md`](01-api-surface.md) for the
> typed surface this consumes,
> [`02-persistence-layer.md`](02-persistence-layer.md) for
> how the typed objects arrive, and
> [`04-walkthrough.md`](04-walkthrough.md) for the end-to-end trace.

## Sandbox provisioning

There is no allocator, no template registry, no string-keyed dispatch.
Each `Sandbox` subclass owns its own `provision()` and `terminate()`.
The framework calls them through the `SandboxLifecycleHub` (defined in
the next section) so retries, quotas, and shutdown work correctly:

```python
# Inside worker_execute (the canonical path — single Inngest function):
sandbox = await lifecycle_hub.acquire(task.sandbox, run_id=run_id, task_id=task_id)
# acquire(...) calls task.sandbox.provision() (or reattaches an existing
# live sandbox on a retry — see below). After it returns, task.sandbox
# IS sandbox (same instance, _runtime now attached).
try:
    # 1. Run the worker. Collect the terminal WorkerOutput from the stream.
    final_output: WorkerOutput | None = None
    async for chunk in worker.execute(task, context=ctx, sandbox=sandbox):
        if isinstance(chunk, WorkerOutput):
            final_output = chunk
        yield chunk

    # 2. Run all evaluators inline — same job, same sandbox, same process.
    #    The evaluators have full sandbox access for filesystem reads /
    #    command execution, exactly like the worker did.
    for evaluator in task.evaluators:
        outcome = await evaluator.evaluate(
            task=task, worker_output=final_output,
            context=criterion_ctx, sandbox=sandbox,
        )
        await graph_repo.persist_evaluation(
            run_id=run_id, task_id=task_id, outcome=outcome,
        )
finally:
    # 3. Release once worker + inline criteria are both done. This
    #    `worker_execute` job is the sole sandbox-lifetime owner for
    #    `(run_id, task_id)`; there is no other release path.
    await lifecycle_hub.release(sandbox)
```

Author code never imports `SandboxLifecycleHub`. The base
`Sandbox.provision()` / `terminate()` *are* the public contract that
each subclass implements; the hub is the single framework caller of
them. If you're writing a new sandbox subclass you implement
`provision()`; you don't think about the hub.

### Inline criteria, single job, single sandbox owner `[v2: clarified]`

The snippet above is canonical. Three properties of the v2 design lock
in:

1. **One Inngest function per task: `worker_execute`.** It runs the
   worker, runs all evaluators inline, and releases the sandbox.
   There is **no separate `evaluate_task_run` Inngest function**, no
   separate `EvaluateTaskRunRequest` event, no second handler module.
   The full event taxonomy is specified in
   [`06-inngest-event-contracts.md`](06-inngest-event-contracts.md).
2. **Worker-execute is the sole sandbox-lifetime owner for
   `(run_id, task_id)`.** `acquire` happens once at the top, `release`
   happens once in `finally` after both worker and inline criteria
   complete. The `run/cleanup` Inngest function exists strictly as a
   shutdown / failure-recovery backstop — it sweeps live sandboxes a
   crashed pod left behind, but it is **never** the primary release
   path for a successful task.
3. **Criteria see the same sandbox state the worker last left.** No
   serialisation/deserialisation of intermediate state, no sandbox
   handoff across processes. A criterion can `cat` the file the worker
   just wrote, run a verification command, or inspect any sandbox
   resource — same `_runtime`, same filesystem, same process.

This is a deliberate v2 simplification of v1's split. v1 fan-out'd
criteria evaluation into a separate Inngest function for parallelism;
the audit found the parallelism never paid off (criteria for one task
are typically O(1) and fast) and the split forced sandbox-handoff
gymnastics that produced the lifecycle leaks the audit logged. The
walkthrough always specified "criteria run inside `worker.execute()`"
implicitly; v2 makes the framework-side execution explicit and matches.

The audit decision and the rejected alternatives are recorded in
[`08-decisions-log.md`](08-decisions-log.md) "Locked decisions
inherited from v1 audit" — Δ.4 / Δ.5. The full job-graph (what events
fire when, what's idempotent, how retries behave) lives in
[`06-inngest-event-contracts.md`](06-inngest-event-contracts.md).

**Why this collapses so far.** Today's `BaseSandboxManager` was a
process-wide singleton conflating four roles: dispatch on benchmark kind,
hold E2B credentials, manage a `dict[task_id, AsyncSandbox]` pool, and
provide per-sandbox operations keyed by `task_id`. The proposed Sandbox
subclass-per-kind absorbs three of them naturally:

| Concern (today) | Where it lives now |
|---|---|
| "What kind of environment?" | `type(sandbox)` — the class identity |
| "How do I provision this kind?" | `sandbox.provision()` — subclass method |
| "How do I run a command in *this specific* sandbox?" | `sandbox.run_command(cmd)` — binding implicit in object |
| "Where are credentials?" | Read from `settings`/env *inside* `provision()`. **Not** stored as fields (would persist secrets in Postgres). |
| "Where is the live-sandbox pool?" | Optional thin `SandboxLifecycleHub` for retries / quota / shutdown — see below |
| "How do I dispatch by kind?" | No dispatch needed; class identity already tells you |

**Adding a new sandbox kind** is now: subclass `Sandbox`, implement
`provision()` (and `terminate()` if needed). No registration step. No
template-string registry. The class is the contract; the import path
(stored as `_type` in the persisted JSON) is how cross-process resolution
finds it.

```python
class WasmSandbox(Sandbox):
    wasm_module: str
    memory_limit_mb: int = 512

    async def provision(self) -> None:
        runtime = await spawn_wasm_runtime(
            module=self.wasm_module,
            memory_mb=self.memory_limit_mb,
        )
        object.__setattr__(self, "_runtime", runtime)
```

That's it — usable in any `Task(sandbox=WasmSandbox(wasm_module="..."))`
immediately. A third-party package can ship its own `WasmSandbox`
without touching `ergon_core` or `ergon_builtins`.

## `SandboxLifecycleHub` — the small thing that survives

The one role of the old singleton manager that doesn't fold into the
subclass is **process-wide live-sandbox tracking**, used for:

- Reconnection across job retries (retried task should re-attach to its
  existing live sandbox, not `provision()` a fresh one),
- Process-wide concurrency / quota (cap on simultaneous live sandboxes),
- Graceful-shutdown teardown (terminate every live sandbox when the
  container exits).

These are real concerns but they're tiny and *kind-agnostic*. A small
`SandboxLifecycleHub` instance owned by the rollout container handles
them with three methods:

```python
class SandboxLifecycleHub:
    """Process-wide registry of live sandboxes. Knows nothing about kinds.

    Lives at `ergon_core/core/infrastructure/sandbox/lifecycle.py`.
    One instance per rollout container process; constructed at
    container startup and disposed at shutdown.
    """

    # In-process map keyed by (run_id, task_id). Survives within a
    # single rollout container; does NOT survive pod restart (the
    # underlying e2b/Docker handle is rebuilt fresh on the next
    # acquire after restart, which is the correct behaviour — a
    # restarted pod can't reattach to a sandbox the previous pod
    # held).
    _live: dict[tuple[UUID, UUID], Sandbox]

    async def acquire(
        self, sandbox: Sandbox, *, run_id: UUID, task_id: UUID,
    ) -> Sandbox:
        """Get a live `Sandbox` for `(run_id, task_id)`.

        Lookup order:
        1. If `(run_id, task_id)` is already in `_live`, return that
           instance — same in-process retry, sandbox is already up.
        2. Otherwise call `sandbox.provision()`, register
           `_live[(run_id, task_id)] = sandbox`, return it.

        Cross-process retry (Inngest re-fires the worker_execute job
        on a new pod) does NOT reattach — the new pod's hub has an
        empty `_live`, so step 2 runs and `provision()` creates a
        fresh underlying sandbox. The old pod's sandbox leaks until
        shutdown — that's the v1 trade-off; the alternative is
        out-of-process state (Postgres-backed registry of live
        sandbox_ids + e2b reattachment), which is deferred. Same
        leak window we have today.

        Raises whatever `sandbox.provision()` raises (no wrapping —
        the framework wants the original error chain visible).
        """

    async def release(self, sandbox: Sandbox) -> None:
        """Terminate the sandbox and remove it from `_live`. Idempotent
        — release on an already-released sandbox is a no-op (lets
        worker_execute call it in a `finally:` without race-checking)."""

    async def terminate_all(self) -> None:
        """Container-shutdown hook. Calls `release()` on every entry in
        `_live`. Best-effort — exceptions are logged and swallowed so
        one stuck sandbox can't block shutdown of the rest."""
```

It does **not** know about Lean vs Python vs Wasm. It just calls
`sandbox.provision()` / `sandbox.terminate()` and uses
`(run_id, task_id)` as the registry key. Replaceable for tests with
a one-line stub. Author code never sees it.

The `(run_id, task_id)` key is deliberate — it's the same composite
identity the runs row uses, so "the sandbox for this task" has one
canonical lookup. No `sandbox_id` plumbing through Inngest payloads
is needed for reattach: the lookup key is already on the job's
payload. The `sandbox.sandbox_id` (from `_runtime.sandbox_id` once
provisioned) is still useful as a debug/tracing handle but is not
the lifecycle key.

## Worker runtime API: WorkerContext

Inside `worker.execute(task, *, context, sandbox)`, every interaction
with the run graph (spawning subtasks, cancelling siblings, listing
descendants, looking up resources produced upstream, …) flows through
`WorkerContext`. It is the single public runtime surface for v1.

`WorkerContext` carries the **curated** set of single-target methods
(spawn / cancel / refine / restart, plus own-scope inspection and
resource discovery) — each one a direct delegate to a method on an
internal application-layer service. Operations that don't fit the
curation rule (batch / predicate / cross-scope inspection / CLI-tier
materialisation) stay on the internal services and are reached by
direct import for the rare consumer that needs them. There is no
public service-class tier between the worker and the implementation.

### Curation rule for `WorkerContext` methods

A method is added to `WorkerContext` if and only if:

- it is **single-target** (operates on exactly one task or one resource —
  no batch, no `predicate=` parameter, no scope keyword that fans out),
  AND
- it is **high-frequency** (used by ≥2 in-tree workers, or expected to
  be used by most workers as a matter of course).

Everything else lives on the internal services
(`TaskManagementService`, `TaskInspectionService`,
`RunResourceRepository`) only. Workers that need batch / predicate /
materialisation ops import the service directly:

```python
from ergon_core.core.application.tasks.management import TaskManagementService
# ...
await TaskManagementService(...).cancel_all_matching(predicate=...)
```

That escape hatch is the same import path `ergon_builtins.tools.*` and
`ergon_cli.commands.workflow` use today. We don't enforce a public /
internal boundary on it for v1 — see
[`08-decisions-log.md`](08-decisions-log.md) "Layered public runtime
API" under Alternatives considered for the rationale and what we'd
need to see to revisit.

When in doubt: leave it off `WorkerContext`. Adding to the facade is a
deliberate API commitment; *not* adding is reversible.

### The v1 WorkerContext surface

```python
class WorkerContext(BaseModel):
    """Runtime handle for a worker execution. Curated single-target
    operations on the run graph; drop to internal services for batch
    or CLI-tier ops."""

    # ── Identity (read-only fields) ────────────────────────────────
    run_id: UUID
    task_id: UUID                     # this worker's task
    execution_id: UUID
    definition_id: UUID

    # ── Internal services (PrivateAttr; framework-set at job start) ──
    _task_mgmt:      TaskManagementService    = PrivateAttr()
    _task_inspect:   TaskInspectionService    = PrivateAttr()
    _resource_repo:  RunResourceRepository    = PrivateAttr()

    # ── Mutation: single-target, parent-on-child only ───────────────
    async def spawn_task(
        self, task: Task, *, depends_on: tuple[UUID, ...] = (),
    ) -> SpawnedTaskHandle:
        """Spawn one child task under this worker. The task must already
        carry its concrete `task.worker`, `task.sandbox`, and
        `task.evaluators` object bindings.

        Fire-and-forget only in v1: returns a `SpawnedTaskHandle` with
        the new `task_id` immediately, parent continues. Workers that
        need to wait for a child poll via `context.get_task(handle.task_id)`
        in a loop — or, more commonly, fan out a batch of children and
        examine results once all are terminal. Synchronous
        `await_completion=True` semantics (parent's sandbox lifecycle
        during the wait, Inngest wait-for-event integration) is
        deferred — see [`08-decisions-log.md#future-work`](08-decisions-log.md#future-work).
        """
        return await self._task_mgmt.add_subtask(
            run_id=self.run_id, parent_task_id=self.task_id,
            task=task, depends_on=depends_on,
        )

    async def cancel_task(self, task_id: UUID) -> None:
        """Cancel one descendant of this worker's task. Raises
        ContainmentViolation if task_id is not a descendant of self.task_id."""
        self._assert_descendant(task_id)
        await self._task_mgmt.cancel_task(run_id=self.run_id, task_id=task_id)

    async def refine_task(self, task_id: UUID, *, description: str) -> None:
        """Update the description of one descendant. Allowed on any
        status except RUNNING. Pairs with restart_task."""
        self._assert_descendant(task_id)
        await self._task_mgmt.refine_task(
            run_id=self.run_id, task_id=task_id, description=description,
        )

    async def restart_task(self, task_id: UUID) -> None:
        """Reset one terminal descendant back to PENDING and re-dispatch."""
        self._assert_descendant(task_id)
        await self._task_mgmt.restart_task(run_id=self.run_id, task_id=task_id)

    # ── Inspection: own-scope, single-call ──────────────────────────
    def subtasks(self) -> Iterable[SubtaskInfo]:
        """Direct children of this worker's task."""
        return self._task_inspect.list_subtasks(
            run_id=self.run_id, parent_task_id=self.task_id,
        )

    def descendants(self, *, max_depth: int = 3) -> Iterable[SubtaskInfo]:
        """BFS over this worker's subtree, up to max_depth."""
        return self._task_inspect.descendants(
            run_id=self.run_id, parent_task_id=self.task_id, max_depth=max_depth,
        )

    def get_task(self, task_id: UUID) -> SubtaskInfo:
        """Fetch one task in this run by id. Allowed targets:
        `self.task_id` (this worker's own task) or any descendant of
        `self.task_id`. Anything outside that subtree raises
        `ContainmentViolation` — same rule as the mutation methods,
        for consistency. Reading your own row is the common case
        (e.g. when you need `instance_key` to construct a child Task);
        reading a descendant is how you poll a child's status."""
        if task_id != self.task_id:
            self._assert_descendant(task_id)
        return self._task_inspect.get_subtask(
            run_id=self.run_id, task_id=task_id,
        )

    def resources(
        self, *, scope: Literal["own", "children", "descendants", "run"] = "own",
    ) -> Iterable[RunResourceView]:
        """Resources produced in the requested scope, newest first."""
        # Per-scope dispatch onto the existing RunResourceRepository methods.
        ...
```

That's it for `WorkerContext`. `plan_subtasks` (batch),
`cancel_all_matching` (batch + predicate), `get_resource_by_content_hash`
(rare lookup), `next_actions` (CLI-shaped) — all stay on the internal
services. Workers that need them import the service explicitly.

`SubtaskInfo` and `RunResourceView` (and the corresponding service
classes' other return types) are the same internal DTOs the services
return today, **with `node_id` fields renamed to `task_id`** as
part of the schema migration (see
[`../2026-05-08-authoring-api-redesign/05-migration.md` §14.C](../2026-05-08-authoring-api-redesign/05-migration.md#14c--internal-dto-reshape)). v1
doesn't promote them into `ergon_core.api.types` — that's a follow-up
to do alongside any future "promote the internal services to the
public API" work.

### `_assert_descendant` and `ContainmentViolation`

The mutation methods (`cancel_task`, `refine_task`, `restart_task`)
and the inspection method `get_task` (when the target ≠ `self.task_id`)
all run a containment check before delegating. The check is a single
synchronous SQL query against `run_graph_nodes.parent_task_id`,
implemented as a recursive CTE so depth is bounded by the database,
not by Python:

```python
class WorkerContext(BaseModel):
    ...

    def _assert_descendant(self, task_id: UUID) -> None:
        """Raise ContainmentViolation if `task_id` is not in the subtree
        rooted at self.task_id. Sync — issues one CTE query against
        run_graph_nodes via the inspection service. Self is *not* a
        descendant of self; callers that want to allow self must check
        explicitly (see get_task)."""
        if not self._task_inspect.is_descendant(
            run_id=self.run_id,
            ancestor_task_id=self.task_id,
            candidate_task_id=task_id,
        ):
            raise ContainmentViolation(
                target=task_id,
                ancestor=self.task_id,
                run_id=self.run_id,
            )
```

`TaskInspectionService.is_descendant(run_id, *, ancestor_task_id,
candidate_task_id) -> bool` is the new method this requires —
implemented as a Postgres recursive CTE walking
`parent_task_id`, with an early-exit `WHERE candidate_task_id = ANY(...)`.
The same CTE shape backs `descendants(...)` and `is_descendant(...)`
so there's one query template, two callers. (Today's
`graph.traversal.descendants` is a Python BFS; v1 keeps it as a
fallback for SQLite tests but uses the CTE in Postgres — the
mechanical change is folded into step 16a.)

`ContainmentViolation` is a public exception in `ergon_core.api.errors`
— signature pinned in
[`01-api-surface.md`](01-api-surface.md#public-exceptions). Inherits
from `RuntimeError` (not bare `Exception`) so `except RuntimeError:`
blocks behave reasonably.

Workers should not generally catch this — hitting it is a logic bug
in the worker, not a recoverable runtime condition. The public class
exists so toolkits that wrap `WorkerContext` methods in `try/except`
have a typed exception to surface in their structured tool result.

### Framework-side WorkerContext construction

Author code never constructs a `WorkerContext` — the framework wires
one up at the top of every `worker_execute` job and passes it into
`worker.execute(...)`. The construction has two phases because the
PrivateAttrs that carry service references aren't part of the
public field schema:

```python
# Inside worker_execute (framework code, not author code):
context = WorkerContext._for_job(
    run_id=payload.run_id,
    task_id=payload.task_id,
    execution_id=payload.execution_id,
    definition_id=payload.definition_id,
    task_mgmt=task_mgmt_service,
    task_inspect=task_inspect_service,
    resource_repo=resource_repo,
)
```

`WorkerContext._for_job` is the framework-only constructor. It builds
the public-fields instance and uses `object.__setattr__` to populate
the service PrivateAttrs in one call:

```python
@classmethod
def _for_job(
    cls,
    *,
    run_id: UUID, task_id: UUID, execution_id: UUID, definition_id: UUID,
    task_mgmt: TaskManagementService,
    task_inspect: TaskInspectionService,
    resource_repo: RunResourceRepository,
) -> "WorkerContext":
    """Framework-only constructor. Authors never call this."""
    instance = cls(
        run_id=run_id, task_id=task_id,
        execution_id=execution_id, definition_id=definition_id,
    )
    object.__setattr__(instance, "_task_mgmt", task_mgmt)
    object.__setattr__(instance, "_task_inspect", task_inspect)
    object.__setattr__(instance, "_resource_repo", resource_repo)
    return instance
```

Same shape as `Task.from_definition` (two-phase: pydantic validation
of public fields, then PrivateAttr injection). Same reason: the
framework needs to wire runtime state that doesn't belong in the
JSON schema; the constructor convention is "public-fields ctor →
classmethod that adds runtime state."

### Containment

`WorkerContext`'s mutation methods (`cancel_task`, `refine_task`,
`restart_task`) check that the target `task_id` is a descendant of
`self.task_id` before delegating, raising `ContainmentViolation`
otherwise. This kills a class of bug that today's
`SubtaskLifecycleToolkit` documents as a TODO:

> "cancel_task, refine_task, and get_subtask accept a node_id from the
> LLM and do not yet verify containment (i.e. that the target is a
> descendant of parent_node_id). The service layer checks status guards
> but not subtree membership."

**The containment check lives on `WorkerContext`, not on the internal
services.** A consumer that imports `TaskManagementService` directly
opts out of the check (the service trusts the (run_id, task_id) it
receives). That's fine for the workflow CLI (operating with explicit
admin intent) and for any toolkit that knows what it's doing; it's the
same shape as today.

### Deciding what to call

| Use case | Where |
|---|---|
| "Spawn one child task." | `WorkerContext.spawn_task(...)` |
| "Cancel one specific descendant by id." | `WorkerContext.cancel_task(...)` |
| "Update one descendant's description." | `WorkerContext.refine_task(...)` |
| "Restart one terminal descendant." | `WorkerContext.restart_task(...)` |
| "List my direct children." | `WorkerContext.subtasks()` |
| "List BFS up to depth N." | `WorkerContext.descendants(max_depth=N)` |
| "Look up a task by id (must be in my subtree)." | `WorkerContext.get_task(id)` |
| "List resources I / my children / my subtree / the run produced." | `WorkerContext.resources(scope=...)` |
| "Cancel every running descendant." | `from ... import TaskManagementService; await svc.cancel_all_running_in_subtree(...)` |
| "Atomically create a sub-DAG of 5 tasks with deps." | `from ... import TaskManagementService; await svc.plan_subtasks(...)` |
| "Look up resource by content hash." | `from ... import RunResourceRepository; await repo.get_by_content_hash(...)` |
| "Materialize a resource into my sandbox." | `from ... import RunResourceRepository, SandboxResourcePublisher; ...` |

The bottom four are exactly the import shape `ergon_builtins.tools.*`
and `ergon_cli.commands.workflow` use today.

### Where the implementation lives

| WorkerContext method group | Backing implementation |
|---|---|
| `spawn_task` / `cancel_task` / `refine_task` / `restart_task` | `ergon_core/core/application/tasks/management.py` (`TaskManagementService`) |
| `subtasks` / `descendants` / `get_task` | `ergon_core/core/application/tasks/inspection.py` (`TaskInspectionService`) |
| `resources(scope=...)` | `ergon_core/core/application/resources/` (`RunResourceRepository`) |
| (process-wide) `SandboxLifecycleHub` | `ergon_core/core/infrastructure/sandbox/lifecycle.py` |

The application-layer modules are reachable by direct import — there
is no boundary test enforcing public-only access. That deliberate
porousness is the v1 simplification; see
[`08-decisions-log.md`](08-decisions-log.md) for what we'd need to see
before adding the firewall.

## Dynamic spawning: what changes (almost nothing)

Workers can spawn child tasks at runtime — fan-out research questions,
recursive decomposition, tree-search candidates, etc. The two-table
identity model (see
[`02-persistence-layer.md#identifier-model`](02-persistence-layer.md#identifier-model-two-tables-one-identity))
makes this a small delta on the static path rather than a parallel
codepath. **The `worker_execute` job body is identical for static and
dynamic tasks**; only the row's *origin* differs.

### What a worker sees

`WorkerContext.spawn_task(...)` (signature in
[`#the-v1-workercontext-surface`](#the-v1-workercontext-surface) above)
is the v1 path for spawning a single child. Workers that need to
materialise a sub-DAG (multiple children with dependencies between
them) in a single transaction import `TaskManagementService` and call
`plan_subtasks` directly — that batch op stays on the internal service
by the curation rule.

**One sandbox + one worker per task is invariant in v1.** A spawned task
is just a new task — the framework provisions a fresh sandbox via
`task.sandbox.provision()` exactly the way it does for static tasks. The
parent and child have independent sandbox runtimes, independent
filesystems, independent lifecycles. There is no API surface for sharing
or reusing the parent's sandbox (see
[`08-decisions-log.md#future-work`](08-decisions-log.md#future-work) on
multi-agent / multi-sandbox patterns).

`task.worker` is a concrete, serializable `Worker` object. There is no
separate `worker=` argument and no experiment-level worker pool to
validate against. That is an intentional object-first choice: if a
child task has different execution behavior, the task says so directly.
The modularity story moves up into Python factories that construct
variants of the task graph, not down into string bindings in the runtime
model.

**v1 is fire-and-forget only.** `spawn_task` returns a
`SpawnedTaskHandle` carrying the new `task_id` immediately; the
parent continues. Workers that want to wait on a child's result
poll `context.get_task(handle.task_id)` until its status is terminal
and then read its output. A synchronous `await_completion=True`
mode (parent blocks until the child terminates, child output
returned inline) is deferred — see
[`08-decisions-log.md#future-work`](08-decisions-log.md#future-work)
for the open questions (parent's sandbox lifecycle during the wait,
Inngest wait-for-event integration, interaction with workers
holding in-memory state).

If a worker genuinely needs to spawn something, it constructs a full
`Task` with its own `worker`, `sandbox`, and `evaluators`. That makes the
dynamic child identical in shape to a static task: no inherited worker,
no hidden evaluator pool, no separate sandbox parameter.

### What the framework does on `spawn_task`

```python
async def spawn_task(self, task, *, depends_on=()):
    # 1. Allocate a fresh task_id — no definition row to inherit from.
    new_task_id = uuid4()

    # 2. Insert one run_graph_nodes row. The worker, sandbox, and
    #    evaluators are whatever task carries — there are no separate
    #    runtime parameters or pool lookups.
    await graph_repo.insert_dynamic_node(
        run_id=self.run_id,
        task_id=new_task_id,
        parent_task_id=self.task_id,                  # links child to parent
        task_json=task.model_dump(),                  # full pydantic JSON, _type discriminator + worker + sandbox + evaluators + payload
        depends_on=depends_on,                        # composite-FK edges into (run_id, dep_task_id)
    )

    # 3. Dispatch worker_execute for (run_id, new_task_id). Same Inngest
    #    event as static. Fire-and-forget — return the handle and let
    #    the parent decide whether/how to wait via get_task().
    return await dispatch_worker_execute(self.run_id, new_task_id)
```

### What `worker_execute` sees (unchanged)

```python
node = graph_repo.node(session, run_id=payload.run_id,
                                task_id=payload.task_id)      # RunGraphNodeView, .task pre-inflated

task   = node.task
worker = task.worker
# Identical to the static path. The job body cannot tell the difference,
# and does not need to. The underlying task_json was either copied from
# experiment_definition_tasks at run-launch (static) or written inline at
# spawn (dynamic) — same shape, same reconstruction (inside graph_repo).
```

This is the payoff of making `Task` object-bound: dynamic spawning adds
**zero new branches** to the runtime. The run row stores a full task
snapshot; `worker_execute` inflates the task and calls `task.worker`.
One new method on `WorkerContext` writes a row; the rest of the system
already handles it.

### Identity recap for dynamic tasks

| Property | Static | Dynamic |
|---|---|---|
| `task_id` born at | experiment-define | spawn (`uuid4()`) |
| `experiment_definition_tasks` row exists? | yes | no |
| `run_graph_nodes` row written by | `run_started` (copy from defs) | `WorkerContext.spawn_task` (inline) |
| `parent_task_id` | NULL (or static parent if any) | parent's `task_id` |
| `task_json` on the row | copied at run-launch | written at spawn |
| Worker JSON store | inline in `task_json.worker` | inline in `task_json.worker` |
| Sandbox provisioning | fresh runtime via `task.sandbox.provision()` | identical — fresh runtime, never shared with parent |
| `worker_execute` reads | `run_graph_nodes` row only | identical |
| `from_definition` shape | identical | identical |

### Constraints

1. **No static dependent on a dynamic task.** Static dependencies are
   declared at experiment-define time and reference
   `experiment_definition_tasks.id` values that exist at that time.
   Dynamic task ids don't exist at define time, so any static-on-dynamic
   edge would block forever. Validator at experiment-define rejects this
   trivially (static deps reference task slugs from `build_instances`,
   dynamic tasks have no define-time slug); runtime check on edge
   insertion prevents anyone smuggling one in. Static-on-static,
   dynamic-on-static, and dynamic-on-dynamic all work normally.

2. **Dynamic children may carry their own evaluators.** Most spawned
   children pass `evaluators=()` because they're internal strategy
   steps — the parent task is what gets scored, not its sub-decisions.
   But if a child should be independently scored, it carries the
   concrete evaluator objects directly, exactly like a static task.

3. **One sandbox + one worker per task — no exceptions in v1.** A
   spawned child is a new task in every respect: it carries its own
   `task.sandbox` instance and the lifecycle hub provisions a fresh
   runtime for it. Parent and child filesystems / runtimes / lifecycles
   are fully independent. We are not shipping any opt-in sharing,
   reattachment, or snapshot/clone primitive in this redesign. Sharing is
   genuinely tricky (concurrency on the runtime, lifecycle coupling,
   filesystem mutation races, cross-process reattachment, interaction
   with future synchronous-wait semantics), and any future work on it
   will be designed together with the broader "multiple agents per task"
   question rather than smuggled in as an addendum here. See
   [`08-decisions-log.md#future-work`](08-decisions-log.md#future-work).

### What this surfaces that needs a follow-up

- **Backpressure / runaway spawning.** A buggy worker can fork-bomb a
  run. Need configurable per-run / per-parent / depth caps. Probably a
  small `GraphSpawnGovernor` analogous to `SandboxLifecycleHub`. Out of
  scope for this redesign; flagged in
  [`08-decisions-log.md#open-questions`](08-decisions-log.md#open-questions).
- **Cancellation cascade.** Already handled by
  `TaskManagementService.cancel_task` (descendants cancelled). Generalizes
  cleanly to whatever depth dynamic spawning produces.

### What this kills in the existing code

- The current slug-based worker resolution (`registry.workers[slug]`) in
  `add_subtask` dies with the registry; a spawned task carries the
  concrete `Task.worker` object directly.
- The "subtask has no `task_payload`/`sandbox`/`evaluators`"
  implicit-inheritance pattern dies. Every spawned `Task` carries its own
  config explicitly, same as a static `Task`. There is no longer a
  privileged "subtask" subtype with implicit-inheritance semantics — a
  dynamic task is just a `Task` written to the runs row by a worker
  instead of by the run-launcher.
- **Containment-check TODOs in `subtask_lifecycle_toolkit.py` close**
  *for tools that route through `WorkerContext`.* Today the toolkit
  notes that `cancel_task`, `refine_task`, and `get_subtask` accept a
  `node_id` from the LLM and don't verify it's a descendant of the
  manager's task. The new `WorkerContext.cancel_task` /
  `refine_task` / `get_task` enforce that check before delegating, so
  any toolkit that switches to the facade methods inherits the check.
  Toolkits that keep importing `TaskManagementService` directly are on
  their own for containment, same as today.

(`TaskManagementService`, `TaskInspectionService`, and
`RunResourceRepository` themselves stay as they are, including their
existing public-when-imported availability to `ergon_builtins.tools.*`
and `ergon_cli.commands.workflow`. Promoting them to a public service
tier with an enforced boundary is deferred — see
[`08-decisions-log.md`](08-decisions-log.md) "Layered public runtime
API".)
