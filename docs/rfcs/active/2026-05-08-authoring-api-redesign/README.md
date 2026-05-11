---
status: in-flight engineering doc (decisions accepted; migration in progress)
opened: 2026-05-08
author: charlie + agent
architecture_refs:
  - ../../../architecture/01_public_api.md
  - ../../../architecture/cross_cutting/sandbox_lifecycle.md
supersedes: []
superseded_by: null
---

# Authoring API redesign — collapse Spec types, push sandbox onto Task

> **Note on the "RFC" path.** This doc lives under `docs/rfcs/active/` for
> path continuity, but it is **not** an open proposal. The decisions below
> are accepted; the migration is in progress. Treat it as engineering
> documentation for an in-flight redesign that will graduate into
> `docs/architecture/` once the migration ships.

## Problem

The author-facing surface (`ergon_core.api`) leaks internal lifecycle and
runtime-construction concerns into the type names a contributor has to learn.
A new benchmark/worker/criterion author currently encounters:

- **`TaskSpec` *and* `Task`** — two near-identical frozen models that differ
  only in whether `task_id: UUID` is filled in. The split exists for honest
  reasons (per-run identity allocation, dynamic subtasks, external imports —
  see [`docs/architecture/01_public_api.md`](../../../architecture/01_public_api.md))
  but the type names don't communicate that. The natural reaction is "WTF, why
  are there two?"
- **`WorkerSpec` (binding) vs `Worker` (instance)** — the binding lives in
  `ergon_core.core.domain.experiments`, the instance in `ergon_core.api`. The
  binding exists because workers can't be pre-constructed at definition time:
  every concrete `ReActWorker` subclass mutates `self.tools = ...` inside
  `execute()` after fetching a sandbox. Because instances aren't serializable,
  the framework persists a slug + name + model recipe and reconstructs the
  worker in the rollout container.
- **A `ComponentRegistry` + `ComponentCatalogEntry` table** that exists almost
  entirely to round-trip `worker_slug → (module, qualname)` across processes.
  Authors have to remember to `register_builtins()` in two places (CLI process
  for definition-time validation, container for runtime resolution) — and the
  container actually doesn't need it because the catalog row already carries
  the import path. The whole edifice exists because `Worker` instances aren't
  serializable.
- **Sandbox configured per-experiment** (`ExperimentDefineRequest.sandbox_slug`)
  rather than per-task, blocking heterogeneous DAGs (e.g. research → code →
  review where each step wants a different environment).
- **Workers/evaluators configured as experiment-level pools** rather than
  task-local objects. This makes the simple task graph harder to read:
  a task says what it does and where it runs, but you have to cross-reference
  `Experiment.assignments` / `Experiment.evaluators` to see who runs it and
  how it gets judged.

The thread that runs through all of these: **`Worker.__init__` takes
construction-time state that should be runtime-time state**. Once we fix that,
`WorkerSpec` collapses, the registry/catalog collapses, sandbox-per-task
becomes natural, workers/evaluators can bind directly to `Task`, and the
author surface shrinks to pure nouns.

## Reading order

The doc is split by audience. Read in this order if you're new to the
redesign; otherwise jump to the file your task touches.

| # | File | What it owns | Read this when |
|---|---|---|---|
| 1 | [`01-api-surface.md`](01-api-surface.md) | Public types (`Worker`, `Task`, `Sandbox`, `Criterion`, `Rubric`, `Benchmark`) + the design principles that produced them (PrivateAttr pattern, "subclass for kind, field for config", "framework calls only base methods") | Touching anything in `ergon_core.api` or any `ergon_builtins` worker / sandbox / toolkit |
| 2 | [`02-persistence-and-identity.md`](02-persistence-and-identity.md) | The `from_definition` convention, typed repos, `RunGraphNodeView`, the two-table identity model, what gets killed (registry, `definition_task_id`, `node_id`) | Touching the persistence layer, the runs/definitions schema, or anything that reads/writes `task_json` / `worker_json` |
| 3 | [`03-runtime.md`](03-runtime.md) | What happens inside a `worker_execute` job: `Sandbox.provision()` per subclass, `SandboxLifecycleHub`, the `WorkerContext` runtime API (curated single-target methods, with the rest reached by direct internal-service import), `WorkerContext.spawn_task` and its constraints, the "one sandbox + one worker per task" invariant | Touching the rollout container, sandbox lifecycle, or dynamic spawning |
| 4 | [`04-walkthrough.md`](04-walkthrough.md) | The canonical 5-stage trace: linear DAG, 4 tasks, 4 workers, end-to-end. **Single source of truth** for "what running looks like." Stage 6 shows two example consumer tools — the curated `WorkerContext` path and the v1 escape hatch (direct internal-service import). | Want a concrete example to pin the abstractions to; auditing a particular stage |
| 5 | [`05-migration.md`](05-migration.md) | The phased implementation plan (4 phases, ~18 steps), the [Schema and contract reference](05-migration.md#schema-and-contract-reference-for-step-14) which pins every table / Inngest payload / internal DTO shape for step 14 (read this before touching the schema rewrite), the [core deduplication audit](05-migration.md#core-deduplication-audit) pairing every public addition with the core counterpart it deletes/thins, the [deletion checklist](05-migration.md#deletion-checklist-reviewer) the reviewer runs before merge, and the [What's deferred](05-migration.md#whats-deferred-not-phase-5--not-v1) note explaining what an earlier draft tried to land and was rolled back | Implementing or tracking work; verifying no parallel implementations were left behind |
| 6 | [`06-decisions-log.md`](06-decisions-log.md) | Alternatives considered, open questions, smells, future work. **The one doc designed to churn** as decisions resolve. | Asking "why did we choose this?" or "what's still open?" |

The cross-references go in **one direction**: `04`/`05`/`06` link into
`01`/`02`/`03`. Reference docs never link down to migration or decisions.
That asymmetry is what stops the doc from drifting back into the
self-inconsistent shape it had as a single 1958-line file.

## Status overview

**Single PR, no backward compatibility.** Ergon has no external
contributors yet; the redesign ships as one cohesive break rather than a
phased rollout. The "phases" below are work-order *within* the PR (later
phases assume earlier ones are in place), not a release sequence.

| Phase | What it lands | State |
|---|---|---|
| 1 | Worker becomes serializable; `WorkerSpec` + `ComponentRegistry` die; `Experiment` lifted into `ergon_core.api` (class definition moves; no re-export shim); `Task.worker` / `Task.evaluators` become direct object bindings | Not started |
| 2 | Sandbox subclass-per-kind; `SandboxSpec` + per-benchmark managers die | Not started |
| 3 | Task unification + two-table identity model + `WorkerContext` curated methods (`spawn_task`, `cancel_task`, `subtasks`, etc.) | Not started |
| 4 | Criterion cleanup (proxy methods + Rubric weights) | Not started |

See [`05-migration.md`](05-migration.md) for the per-step breakdown and
[`06-decisions-log.md`](06-decisions-log.md) for what's still open.

## What this redesign does to existing invariants

References to [`docs/architecture/01_public_api.md`](../../../architecture/01_public_api.md):

- **"`Worker.__init__` takes required keyword-only kwargs"** — invariant
  changes. Workers are pydantic models with declared fields; `tools` no
  longer appears as a kwarg at all.
- **"Workers MUST NOT own per-task environment setup"** — strengthened.
  Today the architecture doc says setup belongs to `BaseSandboxManager`;
  this redesign pushes setup directly into the relevant `Sandbox`
  subclass's `provision()` method (one subclass per environment kind:
  `LeanSandbox.provision()`, `PythonSandbox.provision()`, etc.) and
  removes the per-benchmark sandbox manager subclasses entirely. There is
  no allocator, template registry, or singleton manager — `type(sandbox)`
  is the dispatch.
- **"Workers are never instantiated at config time"** — *reversed*. After
  this redesign, workers are fully serializable and ARE instantiated at
  config time. The runtime deserializes them in the container instead of
  reconstructing from a slug + recipe.
- **"`type_slug` is a keyed identifier" (across CLI, onboarding, registry)** —
  weakened. Slugs survive only at the CLI as human-friendly aliases; they
  are no longer load-bearing for runtime resolution.

References to [`cross_cutting/sandbox_lifecycle.md`](../../../architecture/cross_cutting/sandbox_lifecycle.md):

- **"Per-task default" sandbox lifecycle** — formalized. Today this is
  the default behavior; with `Task.sandbox` carrying the typed subclass,
  "one sandbox per Task, `provision()`-ed from `Task.sandbox`,
  `terminate()`-d when the task settles" becomes a checkable invariant
  rather than ad-hoc convention.

New invariants this redesign introduces:

- **One class per domain concept.** No `*Spec` parallel hierarchies.
  Where a type has both static config and runtime capabilities (currently
  `Task` and `Sandbox`; potentially others in future), the config lives
  in public pydantic fields and the runtime lives in a `_runtime: T |
  None` `PrivateAttr`, exposed through proxy methods or properties that
  raise if the runtime hasn't been attached. Pattern is in-tree
  precedent: `CriterionContext`.
- **Public-API model classes are pydantic-serializable, end-to-end.**
  Every author-constructed object (Benchmark, Task, Sandbox, Worker,
  Criterion, Rubric) round-trips through JSON without external context.
  Class identity travels as a `_type: "module:qualname"` discriminator in
  the dump.
- **Worker `execute()` receives all runtime resources as parameters,
  non-optional.** `task: Task`, `context: WorkerContext`, `sandbox:
  Sandbox` — no `None`, no fetching from process-level singletons, no
  mutation of `self`, no closure-capture of sandboxes during construction.
- **`Task` declares its own environment.** The runtime owns provisioning;
  the worker and criterion both receive the live `Sandbox` from that task.
- **One sandbox + one worker per task (v1).** Spawned children get fresh
  sandboxes. Sharing/reuse deferred to a later redesign — see
  [`06-decisions-log.md#future-work`](06-decisions-log.md#future-work).
- **`WorkerContext` is the public runtime surface.** It carries the
  curated single-target methods (`spawn_task`, `cancel_task`,
  `refine_task`, `restart_task`, `subtasks`, `descendants`, `get_task`,
  `resources`) — each delegating directly to an internal
  `core.application.*` service. Operations that fail the curation rule
  (batch / predicate / cross-scope / CLI-tier) stay on the internal
  services and are reached by direct import — same as today. An
  earlier draft promoted those services to a public service tier
  (`GraphMutator` / `GraphInspector` / `ResourceInspector`) with an
  enforced `ergon_builtins → core.application` boundary; that was
  rolled back as scope creep — see
  [`06-decisions-log.md`](06-decisions-log.md) "Layered public runtime
  API" under Alternatives considered, and
  [`05-migration.md`](05-migration.md) "What's deferred". Curation
  rule and v1 surface in
  [`03-runtime.md#worker-runtime-api-workercontext`](03-runtime.md#worker-runtime-api-workercontext).
  (`SandboxLifecycleHub` is *not* part of the public surface — it
  lives in `ergon_core/core/infrastructure/sandbox/` and only the
  rollout container calls it.)

## Out of scope

These are real concerns but they don't block this redesign:

- Dashboard event schema changes (downstream, mechanical).
- RL trajectory format changes (the RL loop reads from `RunContextEvent`,
  not from `Worker` instances directly — unaffected).
- Inngest event-shape backward compat. Every payload changes shape
  in lockstep with the schema rewrite — see
  [`05-migration.md` §14.B](05-migration.md#14b--inngest-payloads)
  for the per-payload table. We have no in-flight events at upgrade
  time (no production traffic), so the rollout is "drop the queue,
  redeploy."
