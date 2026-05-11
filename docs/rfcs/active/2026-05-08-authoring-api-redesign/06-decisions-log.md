# 06 — Decisions log

> Living document. Update as decisions resolve, smells get triaged, and
> future work crystallizes into follow-up redesigns. The reference docs
> ([`01-api-surface.md`](01-api-surface.md),
> [`02-persistence-and-identity.md`](02-persistence-and-identity.md),
> [`03-runtime.md`](03-runtime.md)) are the *current* shape; this doc
> captures the *why* and the *what's still open*.

## Alternatives considered

### Keep `WorkerSpec`, just rename it to `WorkerBinding`

Cosmetic. Doesn't address the underlying smell (workers can't be
pre-constructed because of `self.tools = ...` mutation). User would still
encounter the binding/instance distinction; the rename only makes the name
slightly more honest. Rejected — fixes naming without fixing structure.

### Keep the registry, just fix the catalog UX

Make `register_builtins` automatic via a decorator at class-definition time.
Removes the manual bootstrap step but leaves the parallel slug-as-identity
layer mirroring Python's import system. Rejected — Python already provides a
global string identity for any class (`module:qualname`); a parallel registry
is duplicate machinery unless we want versioning/aliasing, which we don't
appear to be using.

### One `Task`, identity in `WorkerContext.task_id` only

Discussed and rejected — `task.task_id` reads more naturally; tasks should
own their own ID; the value object should be self-identifying. The unified
`PrivateAttr` pattern preserves `task.task_id` as the access path, so this
alternative is moot.

### Two-class `TaskSpec` / `Task` (with or without inheritance)

Earlier draft of this redesign proposed keeping the two-class split,
optionally with `class Task(TaskSpec)` inheritance to remove field
duplication. Superseded by the unified `PrivateAttr` pattern, which
collapses to one class without losing the "definition-time has no ID,
runtime does" invariant. Inheritance approach kept as a fallback if the
PrivateAttr pattern proves too magic in code review.

### Generic phantom-typed `Task[Phase]` with `Defined`/`Live` markers

```python
Task[Defined]   # task_id is structurally absent
Task[Live]      # task_id present
```

Considered. Pydantic's relationship with phantom generics is rough —
runtime validation of phantom params requires custom validators, the type
system only enforces at static-check time, and pydantic v2 doesn't preserve
phantom params through `model_dump`/`model_validate`. The PrivateAttr
pattern gets the same "two phases of one type" semantics with simpler
machinery.

### "Live" subclass at runtime: `LiveSandbox(Sandbox)`

Same conceptual split as today's Spec/Live but with inheritance instead of
sibling classes. Better than today (gives `LiveSandbox <: Sandbox`
substitutability) but still two classes for one concept. Author code now
has to know "do I receive a `Sandbox` or a `LiveSandbox`" — the latter
which only exists at runtime. Loses the "one class, you always know which
one you're holding" property of the PrivateAttr pattern.

### Per-benchmark sandbox managers stay; `Task.sandbox` is just a slug

Half-measure. Keeps the per-benchmark manager subclasses
(`MiniF2FSandboxManager`, `SWEBenchSandboxManager`, …) but lets a Task
pick which one. Rejected because the per-benchmark managers are mostly
per-template setup scripts wearing the wrong hat — the install logic is
template-specific, not benchmark-specific. Better to consolidate into one
generic manager dispatching on template.

### Tools as a `Benchmark.toolkit_for(sandbox, task)` method

Considered in the discussion. Right idea but too opinionated for the
framework — it forces every worker to use a "list of pydantic-ai Tool"
abstraction. Workers should be free to use the sandbox however they want
(raw `run_command`, hand-coded shell scripts, no-LLM workflows). Rejected
in favor of the framework giving workers `sandbox: Sandbox` and letting
each worker construct its own tools (or none).

### Layered public runtime API: `WorkerContext` facade + `GraphMutator` / `GraphInspector` / `ResourceInspector`

Designed in detail (curation rule, `.for_worker(context)` constructors,
containment-by-construction, public-`SubtaskSpec` shape, public exception
types), then **rolled back as scope creep for v1**. The design moved
three new public classes into `ergon_core.api`, enforced an
`ergon_builtins → ergon_core.core.application.*` import boundary, added
new boundary tests, and required migrating the three in-tree consumers
(`subtask_lifecycle_toolkit.py`, `graph_toolkit.py`, the workflow CLI)
onto the new public surface. ~6 migration steps for purely speculative
external consumers we don't have. The justification was "expose the
escape-hatch as a supported public path" — but until someone outside
this repo asks for it, the escape hatch is one porous import away
(`from ergon_core.core.application.tasks import TaskManagementService`),
which is what `ergon_builtins.tools.*` does today and will continue to
do. `WorkerContext` ships as the single public runtime surface with the
curated facade methods (`spawn_task`, `cancel_task`, `subtasks()`, …);
batch ops, predicate-based ops, and CLI-tier surfaces stay on the
internal services and are reached by direct import when needed.

When a real third-party consumer arrives — or when an in-tree refactor
genuinely needs the architectural firewall — promote the internal
services to `ergon_core.api`, add the boundary test, and migrate the
three in-tree consumers in a follow-up redesign. The design is preserved
in the git history of this folder and in
[`05-migration.md`](05-migration.md)'s "What's deferred" section so the
follow-up doesn't have to rederive it.

### Fat `WorkerContext` only (predecessor to the rolled-back layered API)

Put every graph mutation, inspection, and resource discovery method
directly on `WorkerContext` and call it done. ~15-20 methods on a single
class, every worker sees the manager-only mutation surface
(`refine_task`, `restart_task`, `cancel_all_*`) whether they need it or
not. Rejected at the time in favour of the layered API; with the
layered API now also rejected (above), the v1 outcome is *neither*
extreme. `WorkerContext` carries the **curated** facade (single-target +
high-frequency only — ~7 methods) and batch / predicate / advanced ops
stay on the internal services. The "fidelity escape hatch" use case is
served by direct internal-service imports, the same way it works today.

## Smells the walkthrough surfaces

These are gaps the abstract design doesn't expose but the concrete trace
in [`04-walkthrough.md`](04-walkthrough.md) does. Each is a real thing we
need to either solve, document as a known-limitation, or punt to a
follow-up redesign.

**1. Cross-task data handoff is undefined.** `code` task `dependency_task_slugs=("research",)` is a *scheduling* edge — it tells the runtime "wait for research to finish." It does not tell the framework "the coder needs research's output." Today this works because `SandboxResourcePublisher` writes files from one task's sandbox to a shared blob store and the next task's sandbox mounts them. But that's an implicit contract: the benchmark has to know that workers write to `/workspace/final_output/` and other tasks read from there. **Open question: should `Task` or `Worker` declare its inputs/outputs explicitly?** e.g. `Task(..., inputs=("findings.md",), outputs=("solution.py",))` so the runtime can fail-fast if a dependency hasn't produced what its dependent expects. Not in this redesign's scope but worth flagging.

**2. Heterogeneous sandboxes break naive file passing.** `research` uses `research-e2b`, `code` uses `python-3.13`. Files written in E2B aren't visible in the Python sandbox unless the runtime explicitly stages them. `SandboxResourcePublisher` already does this via Postgres-backed `RunResource` blobs, but it relies on the worker writing to `/workspace/final_output/` — a sandbox-specific path convention. **The path convention isn't on `Sandbox` or `Task`; it's a hidden contract.** Could be a `Sandbox.output_path: str` field, or a `task.publish_files(...)` helper. Flag for follow-up.

**3. `instance_key` is repeated four times in `build_instances`.** Every Task in an instance has the same `instance_key`. The outer dict already keys by instance — having `Task.instance_key` is redundant. **Deferred.** Keeping it in v1 avoids coupling this authoring API migration to a benchmark/definition-writer contract change. The cleanup is small, but it touches every `Task(...)` constructor and the materialization path; land it as a follow-up once the object-bound Task model is implemented.

**4. `assignments` lives on `Experiment` but `dependency_task_slugs` lives on `Task`.** The DAG structure is split across two places. A new contributor reading the experiment can't see "who runs `code`" without cross-referencing two dicts. **Resolved by object-first task binding.** `Task.worker` is now a direct `Worker` object; `Experiment.assignments` deletes. The earlier modularity rationale ("same benchmark, swap the team") is still achievable through normal Python composition: benchmark factories accept different worker objects and construct otherwise identical task graphs.

**5. `Rubric` is bound at the experiment level, not the task level.** All four tasks share the same `default` Rubric with the same criteria. If you want different criteria per task ("the coder's output gets style-checked, the reviewer's output gets length-checked") you need to declare multiple evaluator binding keys and remember which task uses which. **Resolved by object-first task binding.** `Task.evaluators: tuple[Evaluator, ...]` directly carries the Rubric or any future evaluator kind. Shared rubrics are ordinary Python variables reused across tasks, not framework binding keys.

**6. `WorkerContext` is now thin enough to question.** ~~After the cleanup it carries `(run_id, definition_id, execution_id)` — three UUIDs and that's it.~~ **Resolved by promoting the curated facade methods directly onto `WorkerContext`.** `WorkerContext` carries the IDs *and* the small high-frequency-use method surface (`spawn_task`, `cancel_task`, `refine_task`, `restart_task`, `subtasks()`, `descendants()`, `get_task()`, `resources(scope=...)`) — each delegating directly to the internal `TaskManagementService` / `TaskInspectionService` / `RunResourceRepository`. It is no longer thin — but it's also not bloated, because the curation rule (single-task ops only; everything batch-y or rare stays on the internal service and is reached by direct import) keeps it bounded. `CriterionContext` remains thin; the question of whether it collapses to kwargs is independent and still open below.

**7. `Worker` as pydantic model: where does private state live?** A `ReActWorker` might want a lazy-initialized HTTP client or a model resolver cached after first use. The pattern: declare as `PrivateAttr`, initialize in `model_post_init` or lazily inside `execute`. **Document as a worker-author convention** — not a blocker, but the redesign should state which pattern to use so contributors don't reach for `__init__` overrides (which break model_validate round-tripping).

**8. `_type` discriminator is everywhere.** Every persisted Worker, Task, Sandbox, Benchmark, Evaluator, Criterion carries a `_type: "module:qualname"` field. That's a lot of repetition in the JSON columns. **Could hoist** to a wrapper envelope (`{kind: "worker", impl: "...", config: {...}}`) at the persistence layer, but that adds a layer of indirection on read. I'd live with it — the JSON is debug-friendly, deserialization is one-liner, and you can always grep `"_type":` to find class references in the DB.

**9. `Benchmark` is still a subclass-only abstraction.** Workers, Tasks, Sandboxes, Criteria are all instances now. `Benchmark` is the lone exception — you subclass it because `build_instances()` is data-generation logic, not declarative config. **Is that right?** Probably yes — benchmarks have real code (HuggingFace dataset loading, jsonl parsing, `task_payload_model` declaration), not just config. But the asymmetry is real and worth naming. Not a blocker.

**10. Sandbox setup payload is `dict[str, Any]`.** Each template's setup script knows its own payload schema, but the type is opaque at the boundary. **Could parametrize `Sandbox` with a payload type the way `Task` is parametrized with `PayloadT`** — `Sandbox[LeanPayload]` where `LeanPayload` is the template-specific config model. More machinery but tighter authoring. ~~Defer.~~ **Resolved by Phase 2.** Sandbox is now a typed subclass per kind; subclass-specific config lives as typed pydantic fields on the subclass (e.g. `LeanSandbox(lean_version=...)`). There is no `setup_payload: dict[str, Any]` anywhere. Smell #10 is closed.

The first two are known limitations to document around resource handoff.
`instance_key` is a follow-up cleanup, not a blocker for this redesign.
The rest are follow-up redesigns or known-limitations to document.

## Open questions

- **Is the PrivateAttr pattern too magic?** It works in `CriterionContext`
  today, but generalizing it to `Task` and `Sandbox` as the canonical way
  these types model their two phases is a bigger commitment. Risk: a new
  contributor constructs `Task(...)` and is confused that
  `task.task_id` raises. Mitigation: clear docstring, error message that
  names the materialization callsite, and the fact that author code never
  *needs* `task_id` at definition time (the framework is the only consumer).
  Worth a code-review sanity check before committing. *@charlie*
- ~~**Where does `Experiment` live in the public API?**~~ — *resolved
  (re-export pattern rolled back).* `Experiment` is the composition
  root authors construct around a benchmark definition — every benchmark
  constructor calls it directly, and it sits alongside `Benchmark`,
  `Task`, `Worker`, `Sandbox` in the authoring contract. It belongs in
  `ergon_core.api`, not in an internal module that authors happen to
  reach into. **The class definition moves to
  `ergon_core/api/experiment.py`** as part of step 4, and
  `ergon_core/core/domain/experiments/experiment.py` is **deleted**.
  An earlier draft of this entry kept the class defined in
  `core.domain.experiments` and added a re-export shim in
  `api/experiment.py` — that was rejected as
  worst-of-both-worlds (the class is publicly imported but lives at
  an internal path; new readers have to chase the re-export to find
  the real definition). The lift also makes the
  `requires_sandbox` `@model_validator(mode="after")` (see "Worker
  → Sandbox compatibility checking" below) live where it naturally
  belongs — on the public type, in the public package — rather than
  being defined on a class whose canonical home is private.

  `DefinitionHandle` and `ExperimentValidationService` stay in
  `core/domain/experiments/`: the handle is purely internal (return
  shape of `persist_definition`, held as `Experiment._persisted`
  `PrivateAttr` for the runtime side), and the validation service is
  a service that operates on the public `Experiment` instance from
  `definition_writer` — services keep living next to the application
  layer that calls them. See
  [`01-api-surface.md`](01-api-surface.md#foundational-change-c--experiment-lifts-into-the-public-api)
  for the lifted-class sketch and
  [`05-migration.md`](05-migration.md) audit row #6 + step 4 for the
  callsite migration. Boundary tests in
  `tests/unit/api/test_public_api_imports.py`,
  `tests/unit/architecture/test_public_api_boundaries.py`, and
  `tests/unit/architecture/test_public_api_target_structure.py`
  treat `Experiment`, `WeightedCriterion`, and `Sandbox` as part of
  the public surface, and assert that the old
  `core.domain.experiments.experiment` path no longer exists.
- ~~**`"none"` template semantics**~~ — *resolved by deletion.* No
  `"none"` template ships in this redesign. A sandbox that satisfies the
  type contract while no-op'ing `run_command` is a lie that makes call
  sites look uniform while making behavior surprising. Genuinely
  zero-environment tasks become possible later via a generic-Docker
  template (basic Python, no special setup) where
  `sandbox.run_command(...)` actually works. Until then,
  `Task.sandbox: Sandbox` is satisfiable by every in-tree benchmark with
  the templates we already have.
- **`Sandbox` IO methods on the base — contract or convenience?**
  `run_command` / `write_file` / `read_file` / `list_files` aren't called
  by the framework itself; only workers and criteria call them. They're
  on the base today as a convenience surface that every sandbox we'll
  ship implements identically. The day a non-IO sandbox kind appears
  (e.g. a `LocalSubprocessSandbox` that can't usefully `write_file`),
  promote them to a `_RemoteIOSandbox` intermediate base and let
  consumers express the requirement via `requires_sandbox = _RemoteIOSandbox`.
  Until then, the base IO methods are documented as "convenience, not
  contract" — and adding non-generalizing methods (e.g.
  `compile_lean_file`) to the base is explicitly forbidden.
- ~~**Worker → Sandbox compatibility checking — where does the check
  live?**~~ — *resolved.* The check runs in a pydantic
  `@model_validator(mode="after")` on `Experiment`, since that's the
  composition root that can walk the benchmark's task list after the
  author has constructed the whole graph. For each task, the validator
  walks `task.worker.requires_sandbox` and any
  `requires_sandbox` declared by the directly bound
  `task.evaluators` / criteria, then checks `isinstance(task.sandbox, X)`
  for each declared `X`. Mismatches raise
  `SandboxKindMismatch(task_id=..., component=..., required=..., actual=...)`
  (signature pinned in
  [`01-api-surface.md`](01-api-surface.md#public-exceptions))
  before `Experiment.__init__` returns, so a misconfigured experiment
  fails at construction in the author's process — never reaches
  `persist_definition` or any rollout. Workers/criteria with
  `requires_sandbox: ClassVar[type[Sandbox]] = Sandbox` (the default)
  pass trivially.
- ~~**Backward compatibility window**~~ — *resolved: one cohesive break,
  no deprecation cycle.* Ergon has no external benchmark contributors yet,
  so there's nothing to deprecate against. The redesign ships as a single
  PR that lands all four phases together; no `WorkerSpec` shim release,
  no `Worker.__init__(tools=...)` warning period, no transitional
  `Sandbox | None` parameter. Local PG carries no production data so all
  schema changes are drop-and-recreate rather than data migrations. See
  [`05-migration.md`](05-migration.md) for the consolidated plan.
- ~~**Per-agent tool customization**~~ — *resolved.* `ReActWorker` takes
  a `toolkit` field; benchmark authors instantiate
  `ReActWorker(toolkit=BenchmarkToolkit(...), ...)`. `_Toolkit` is
  module-private to `ergon_builtins`, never promoted to
  `ergon_core.api`, so the framework doesn't pre-shape every future
  worker strategy around the assumption that "agents have toolkits."
  Per-benchmark Worker subclasses delete entirely; the variation lives
  in the `toolkit` instance.
- ~~**Where does the runtime graph-edit API live?**~~ — *resolved (twice):
  WorkerContext is the only public runtime surface for v1.* The framework
  today scatters runtime mutation across `WorkerContext` (just IDs),
  `TaskManagementService` and `TaskInspectionService` (in
  `ergon_core.core.application.tasks`, technically internal but freely
  imported by `ergon_builtins.tools.*` and the workflow CLI). An earlier
  resolution promoted three public service classes
  (`GraphMutator` / `GraphInspector` / `ResourceInspector`) to
  `ergon_core.api` and enforced the boundary; that was rolled back as
  scope creep — see ["Layered public runtime API"](#layered-public-runtime-api-workercontext-facade--graphmutator--graphinspector--resourceinspector)
  in Alternatives considered for the rationale. **Final v1 shape:**
  `WorkerContext` carries the curated facade methods (single-target +
  high-frequency only; see curation rule below), each delegating
  directly to the internal services. The internal services stay where
  they are; toolkits and the CLI keep their existing
  `from ergon_core.core.application import …` imports. No boundary test,
  no public service classes. Promote later when a real third-party
  consumer arrives.
- ~~**Curation rule for `WorkerContext` facade methods**~~ — *still applies.*
  An operation gets a `WorkerContext` facade method **iff** it is (a)
  single-target (operates on exactly one task or one resource — no
  batch / no `predicate` parameter), and (b) used by ≥2 in-tree workers
  or expected to be used by most. Everything else stays only on the
  internal `TaskManagementService` / `TaskInspectionService` /
  `RunResourceRepository`. This keeps `WorkerContext` bounded (~7
  methods at v1) while the internal services carry however many
  granular ops the CLI / advanced toolkits need without bloating what
  every worker sees in its IDE autocomplete. When in doubt, *don't* add
  to `WorkerContext` — the escape-hatch is one direct import away.
- **`Sandbox` capability surface**: what methods does the live `Sandbox`
  object expose? Probably the union of what `CriterionRuntime` proxies today
  (`run_command`, `write_file`, `read_file`, `list_files`, `read_resource`,
  `upload_files`, `execute_code`, `cleanup`). Worth a separate brief design
  pass to lock that surface before passing it as a parameter.
- **Pydantic-model `Worker` and `Criterion` — what about non-pydantic state?**
  Some workers might want lazy-initialized clients (HTTP sessions, model
  resolvers). Either: declared as `PrivateAttr` and built in a
  `model_post_init`, or built lazily inside `execute`. Pick one as the
  pattern.
- **`Task.sandbox` config vs `Task.task_payload`**: there's some overlap
  (a Lean task has `task_payload.formal_statement` AND uses
  `LeanSandbox`). Make sure these stay orthogonal — `task_payload` is
  benchmark-domain data the worker reasons about, `sandbox` is the
  environment kind plus its provisioning config (lean version, repo
  pin, etc.). If a sandbox subclass needs benchmark-specific config to
  provision itself, that goes as a typed pydantic field on the sandbox
  subclass (e.g. `LeanSandbox(lean_version="4.7.0", mathlib_revision="...")`),
  distinct from `task_payload`.
- **Cross-task data handoff** *(surfaced by walkthrough smell #1)*: should
  `Task` declare its inputs/outputs explicitly so the runtime can fail fast
  if a dependent's expected file isn't present? Today this is an implicit
  contract between dependent benchmarks and `SandboxResourcePublisher`.
  Likely a follow-up redesign, but flag it so we don't regress when
  reworking the publish pipeline. Punt with a known-limitation doc.
- **Sandbox output-path convention** *(surfaced by walkthrough smell #2)*:
  the `/workspace/final_output/` path is hardcoded into both worker code
  and the resource publisher. Should this be `Sandbox.output_path: str`,
  defaulting per template? Small change, worth landing alongside the
  `Sandbox` unification.
- ~~**Task worker binding**~~ *(surfaced by walkthrough smell #4)*:
  **resolved by direct object binding.** `Task.worker: Worker` replaces
  `Experiment.assignments` and any string `Task.assigned_worker`
  half-step. Cohort variants reuse the same benchmark shape through
  Python factories that pass different workers into task construction.
- ~~**Per-task criteria / evaluators**~~ *(surfaced by walkthrough smell #5)*:
  **resolved by direct object binding.** `Task.evaluators:
  tuple[Evaluator, ...]` replaces experiment-level evaluator pools and
  `evaluator_binding_keys`.
- **Should `WorkerContext` and `CriterionContext` collapse?** *(surfaced
  by walkthrough smell #6)*. **Partially resolved.** `WorkerContext` no
  longer collapses to "three UUIDs" — it's the curated runtime facade
  carrying `spawn_task` / `cancel_task` / inspection / resource
  discovery. The collapse question now applies only to
  `CriterionContext`, which after the Phase 4 cleanup *is* down to the
  IDs. Possible directions: (a) keep `CriterionContext` as a typed data
  carrier (status quo, fine), or (b) drop it and make `Criterion.evaluate`
  take `run_id`/`execution_id` as kwargs alongside `task` and `sandbox`.
  Lean toward (a) — having a named type for the runtime context bag is
  worth the typing tax even if it's small. Land that decision in Phase 4.
- **Backpressure for dynamic spawning** *(surfaced by the dynamic-spawning
  section)*: a buggy worker could fork-bomb a run. Need configurable
  per-run total / per-parent direct-children / depth caps, enforced at
  `WorkerContext.spawn_task` (synchronous fail-fast). Probably a small
  `GraphSpawnGovernor` analogous to `SandboxLifecycleHub`. Defaults could
  be conservative (e.g. 100 / 20 / 5) and overridable per-experiment.
  Out of scope for this redesign; surface in a brief follow-up.
- ~~**`await_completion=True` semantics**~~ — *resolved by deferral.*
  v1 ships `spawn_task` as fire-and-forget only — the kwarg doesn't
  exist on the v1 surface. Parent workers that need to wait poll
  `context.get_task(handle.task_id)` until the child's status is
  terminal. Synchronous "block until child returns its WorkerOutput"
  semantics is genuinely tricky (parent's sandbox lifecycle during
  the wait, Inngest wait-for-event integration, interaction with
  workers holding in-memory conversational state) and trying to
  decide it now would either ship something brittle or stall this
  PR. Add it in a follow-up once a real consumer demands it; the
  follow-up gets to pick "hold sandbox" vs "yield + reacquire" with
  a concrete workload to validate against. Listed under future work.
- **Drop `Task.instance_key`** *(surfaced by walkthrough smell #3)*: the
  outer `Mapping[instance_key, Sequence[Task]]` already keys by instance;
  having every Task repeat its instance_key is redundant. Have the
  framework fill it in during materialization. Deferred to a follow-up
  so this migration can keep the existing benchmark/definition-writer
  contract stable while it replaces the larger Spec/pool/runtime model.

## Future work

Deliberately deferred so this redesign can land cleanly without having
to design them:

- **Synchronous `spawn_task(..., await_completion=True)`.** v1 ships
  fire-and-forget only. A future redesign decides between
  "parent holds sandbox" (simple, expensive) and "parent yields +
  reacquires via lifecycle hub" (cost-efficient, complicated by
  in-memory worker state) once a real consumer constrains the choice.
- **Multiple agents per task / sandbox sharing.** Today's invariant is
  *one worker per task*; this redesign adds *one sandbox per task*. The
  two invariants together rule out: parent and child sharing a sandbox,
  multiple workers collaborating in one task, snapshot/clone semantics
  for fast fan-out from a common base state. Each is a real ergonomic
  win for some workload (tactic search, multi-agent debate, branching
  exploration), and several touch overlapping mechanism (sandbox
  reattachment, ref-counted lifecycle, concurrency on the runtime,
  per-task event attribution). Designing them piecemeal would produce
  conflicting primitives. Deferred to a single follow-up redesign scoped
  as *"multiple agents per task"* — that redesign will decide whether to
  ship any of them and, if so, will pick one shared mechanism. Until
  then: spawning a task creates a new task with a new sandbox, full stop.
