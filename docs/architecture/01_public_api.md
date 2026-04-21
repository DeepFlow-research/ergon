# 01 — public api

## purpose

This layer defines the types a contributor touches to add a benchmark, worker,
evaluator, or criterion to Ergon. It is the narrow seam between user-authored
research code and the runtime: a handful of frozen Pydantic models, two abstract
bases, one Protocol, and one declarative binding. Everything below this layer
(Inngest functions, RL adapters, DB writes, provider clients) is implementation
detail the public API deliberately hides. If a type appears in this document it
is part of the contract; if it does not, it is internal and may move without
notice.

## core abstractions

All public-surface Pydantic models are `frozen=True`; mutation is done through
`model_copy(update=...)`. Every type below lives under `ergon_core/api/` and is
owned by that module.

- **`Benchmark`** — abstract base. Produces work units via `build_instances()`
  (a mapping from `instance_key` to a sequence of `BenchmarkTask`) and declares
  the evaluator binding keys it expects via `evaluator_requirements()`. Carries
  a `type_slug: ClassVar[str]` that is a keyed identifier across the CLI, the
  onboarding profile, and the benchmark registry — renames are breaking.
- **`BenchmarkTask`** — frozen Pydantic model describing a single unit of work.
  It has two textual surfaces with very different audiences: `description` is
  the only free-text the worker ever sees; `task_payload` is a dict the
  evaluator (and benchmark itself) may read but the worker never does. The
  split is load-bearing — see invariants. Intra-instance task graph edges
  (`parent_task_key`, `dependency_task_keys`) are validated by
  `Experiment.validate()`.
- **`Worker`** — abstract base. `execute()` is an async generator that MUST
  yield a `GenerationTurn` per LLM call (see invariants). The runtime uses each
  yield as both an RL observation point and a cancellation checkpoint.
- **`GenerationTurn`** — frozen model holding the per-turn LLM trace (input
  messages, response parts, tool results, token IDs, logprobs, policy version,
  timing). Not persisted directly; the runtime decomposes each turn into one
  `RunContextEvent` per message at the event sink.
- **`Evaluator`** — abstract base. Scores a completed task by examining
  recorded turns and published artifacts, delegating per-aspect scoring to
  `Criterion` implementations and aggregating the results. The provided
  `Rubric` subclass aggregates by weighted average over a fixed criteria list.
- **`Criterion`** — abstract base. Scores a single aspect of a completed task.
  Criteria MAY be agentic — they may themselves call an LLM, issue tool calls,
  or read sandbox resources. This is intentional: rubric-style benchmarks want
  LLM-judge criteria, correctness-style benchmarks want criteria that exec
  tests inside the task sandbox.
- **`CriterionRuntime`** — Protocol. The execution context an agentic
  criterion uses to reach into its environment. **Surface-area constraint:**
  this Protocol is narrowly scoped to sandbox lifecycle and resource I/O; it
  should not grow into a generic service locator. The one current method that
  is not about sandbox/I/O is a candidate for extraction if the surface
  continues to accumulate capabilities. Expansion is in flight — see
  follow-ups.
- **`Experiment`** — **plain Python class**, deliberately not a Pydantic model,
  because it is the declarative binding of `{benchmark, workers, evaluators,
  assignments, metadata}` and the canonical import contributors rely on.
  Constructor is keyword-only. `validate()` enforces the cross-type invariants
  (binding-key coverage, unique task keys, graph-edge resolution, assignments
  referencing real keys). `persist()` writes the immutable definition rows;
  `run()` persists (if needed) and dispatches the Inngest flow. The
  `from_single_worker` classmethod is the ergonomic path for the common
  one-worker case.

## control flow

```
Benchmark.build_instances()
    |
    v
dict[instance_key, Sequence[BenchmarkTask]]
    |
    v
Experiment binding resolves (worker, evaluator) per instance_key
    |
    v
runtime fans out one execution per (task, worker_binding)
    |
    v
Worker.execute()  ---- async generator ---->  GenerationTurn (n times)
                                                    |
                                                    v
                                          decomposed into
                                          RunContextEvent rows
                                          (one per message)
                                                    |
                                                    v
                                          persisted via event sink
    |
    v  (on completion)
Evaluator runs against recorded turns + artifacts
    |
    v
Evaluator invokes its Criteria
    |                                               |
    v                                               v
 scalar criterion                          agentic criterion
       \                                           /
        \               CriterionRuntime          /
         \              (for agentic)            /
          v                                     v
           scores land in RunTaskEvaluation
```

Every arrow crosses a process or await boundary; there is no synchronous path
from `build_instances()` to `RunTaskEvaluation`. The runtime is free to
reorder, retry, and parallelise everything downstream of `build_instances()`
within the constraints the invariants below impose.

## invariants

- **Public-API models are frozen.** Every Pydantic model under
  `ergon_core/api/` sets `frozen=True`. Mutation is done by `model_copy`. This
  lets the runtime cache, hash, and cross process boundaries without defensive
  copies.
- **Workers MUST yield.** `Worker.execute()` yields at least one
  `GenerationTurn` per invocation, including stubs. The runtime uses turns as
  the unit of RL observation and of cancellation checkpointing; a silent
  worker breaks both.
- **`description` is the worker's only window.** `BenchmarkTask.description`
  is the single free-text field passed to the worker. `task_payload` is for
  the evaluator and the benchmark itself. Never leak evaluator-only fields
  (hidden tests, reference patches, rubric answer keys) into `description`.
  Canonical pattern:
  `ergon_builtins/benchmarks/swebench_verified/task_schemas.py:76`.
- **`Experiment` stays in `ergon_core/api/`.** It is the declarative binding
  and the import contributors rely on. Do not move it into the runtime, the
  registry, or a plugin package.
- **`type_slug` is a keyed identifier.** The slug on a `Benchmark` subclass is
  referenced by the CLI, the onboarding profile, and the benchmark registry.
  All three must agree. A mismatch silently strands a benchmark: the registry
  has it, the onboarding flow does not prompt for its credentials, and users
  hit opaque errors at run time.
- **Evaluator binding keys form a typed contract.** The keys a benchmark
  declares in `evaluator_requirements()` must be a superset of the keys its
  `BenchmarkTask.evaluator_binding_keys` emit; evaluators select bindings by
  matching these keys. `Experiment.validate()` enforces coverage.
- **RL-signal fields are nullable, not empty-filled.**
  `GenerationTurn.turn_token_ids` and `turn_logprobs` are `| None`. Backends
  that do not support logprobs MUST return `None`, not `[]` or a list of
  zeros. The RL extractor treats `None` as "no logprobs collected" and pads;
  `[]` would be interpreted as "zero tokens generated" and silently corrupt
  token budget math (`ergon_core/core/rl/extraction.py:173`).

## extension points

### add a new benchmark

1. Subclass `Benchmark` under `ergon_builtins/benchmarks/<slug>/`.
2. Set `type_slug` to the stable identifier.
3. Implement `build_instances()`. If the task payload contains evaluator-only
   fields, route the worker-safe subset through a helper (mirror
   `build_worker_description` in
   `ergon_builtins/benchmarks/swebench_verified/task_schemas.py:76`).
4. Implement `evaluator_requirements()` listing the binding keys any task
   emits.
5. Register in the benchmark registry.
6. Add an entry to `ergon_cli/onboarding/profile.py::BENCHMARK_DEPS`. Skipping
   this is the most common onboarding regression — a benchmark is
   half-registered until `BENCHMARK_DEPS` has it.
7. If the benchmark needs a custom sandbox Docker template, add an `ergon
   benchmark setup <slug>` subcommand that builds and pins the template. Do
   not bake template builds into `build_instances()`.

### add a new worker

1. Subclass `Worker`.
2. Implement `execute()` as an async generator. Yield a `GenerationTurn` for
   every LLM call; stubs must yield at least once.
3. Resolve LLM clients via `resolve_model_target(...)` from
   `ergon_core/core/providers/generation/model_resolution.py`. Never import a
   provider SDK directly — the resolver presents a uniform cross-provider
   interface.
4. Register per the worker registry conventions.

### add a new evaluator or criterion

1. Subclass `Evaluator`. Select tasks by matching binding keys against
   `BenchmarkTask.evaluator_binding_keys`.
2. For per-aspect scoring, implement `Criterion`. Plain criteria can be pure
   functions over the recorded turns and artifacts.
3. For an agentic criterion, implement against the `CriterionRuntime`
   Protocol. A criterion runs in the task's existing sandbox; it does not
   allocate its own.
4. Ensure the benchmark's `evaluator_requirements()` keys match the keys the
   evaluator consumes.

## anti-patterns

- **Importing an LLM SDK directly in a worker.** All model clients come from
  `resolve_model_target` in
  `ergon_core/core/providers/generation/model_resolution.py`. The pattern is
  currently clean across `ergon_builtins/workers/`; keep it that way.
- **Mutating a frozen model in place.** Pydantic will raise at runtime. Use
  `model_copy(update={...})`. If you find yourself reaching for a setter, the
  abstraction is wrong.
- **Stub workers that `return` without yielding.** Zero RL observations, zero
  cancellation checkpoints; the runtime treats it as a no-op and the evaluator
  sees an empty turn list.
- **Evaluator-only fields in `BenchmarkTask.description`.** Route hidden
  tests, reference patches, and rubric answers through `task_payload` and
  build a worker-safe `description` explicitly.
- **Leaving `type_slug` out of the onboarding registry.** Users running
  `ergon onboard` will not be prompted for the benchmark's API keys and the
  benchmark fails opaquely at run time.
- **Emitting empty RL-signal lists from a non-logprob backend.** A
  logprob-less backend MUST set `turn_logprobs=None`. `[]` or a list of zeros
  is read as "zero tokens generated" and silently corrupts downstream token
  accounting.
- **Criteria that allocate their own sandbox.** Agentic criteria must run in
  the task's existing sandbox via the `CriterionRuntime` seam. Enforced by
  `tests/state/test_criteria_do_not_spawn_sandboxes.py`.

## follow-ups

- **`CriterionRuntime` DI container expansion** — RFC at
  `docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md`. Adds
  resource and event-sink accessors to the Protocol; explicitly does not add
  sandbox-allocation methods (criteria share the task sandbox). Every current
  agentic criterion is in scope for migration. Open direction: if the surface
  keeps growing, the LLM-judge helper is a candidate for extraction into a
  mixin so the Protocol stays focused on sandbox and resource I/O.
- **Artifact handoff between worker and evaluator** — see
  `docs/architecture/cross_cutting/artifacts.md`. Today worker artifacts drop
  at the Inngest seam and evaluators reinvent retrieval ad-hoc. The canonical
  path will be `SandboxResourcePublisher` on the worker side and a
  `read_resource` accessor on the evaluator side. Until that lands, treat
  artifact retrieval as unstable and keep benchmark-specific retrieval code
  local to the benchmark package.

## code map

Compact onboarding reference. The architectural argument above stands without
this table; it is here only so contributors can find the files fast.

| Type | File |
|------|------|
| `Benchmark` | `ergon_core/api/benchmark.py` |
| `BenchmarkTask` | `ergon_core/api/task_types.py` |
| `Worker` | `ergon_core/api/worker.py` |
| `GenerationTurn` | `ergon_core/api/generation.py` |
| `Evaluator`, `Rubric` | `ergon_core/api/evaluator.py` |
| `Criterion` | `ergon_core/api/criterion.py` |
| `CriterionRuntime` | `ergon_core/api/criterion_runtime.py` |
| `Experiment` | `ergon_core/api/experiment.py` |
| Composition examples | `ergon_cli/composition/__init__.py` |
| Onboarding deps registry | `ergon_cli/onboarding/profile.py` |
