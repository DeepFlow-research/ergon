# 06 — Builtins

## 1. Purpose

`ergon_builtins/` is the library of first-party benchmarks, workers,
evaluators, criteria, rubrics, and model backends shipped with the runtime.
This document describes the registration pattern, the file-layout convention
per benchmark, and the stub-worker contract. It is a statement of how the
layer is organized today and what must remain true for a benchmark to be
runnable — not a catalog of registered implementations.

## 2. Core abstractions

- Benchmark registry.
  - Plain `dict[str, type[Benchmark]]` populated by eager imports at module
    load, split between an always-available core set and a data-extra-gated
    set. No decorators, no entry points.
  - Surface-area constraint: registration is a dict entry keyed by
    `type_slug`. External packages cannot register without editing the
    registry module; this is the intentional short-term choice for monorepo
    development.
  - Freeze status: layout is conventional, not enforced at import time.
    Divergences are debt.
  - Owner: benchmark author.

- Worker registry.
  - Reference workers that run across benchmarks live under
    `ergon_builtins/workers/baselines/`; benchmark-specific worker variants
    live alongside their benchmark.
  - Registry shape: `WORKERS: dict[str, WorkerFactory]` where
    `WorkerFactory = Callable[..., Worker]` and every entry is called with
    `(name=..., model=..., task_id=..., sandbox_id=...)`. Plain subclasses
    are referenced directly (`"stub-worker": StubWorker`) because base
    `Worker.__init__` requires `task_id` / `sandbox_id` and every concrete
    subclass forwards them through to `super().__init__`. Benchmark-specific
    entries (`"minif2f-react"`, `"swebench-react"`) are small closures that
    build a live toolkit from the sandbox and pass every ctor kwarg —
    including the runtime identity kwargs — through to `ReActWorker(...)`.
    The previous `_plain(cls)` shim has been removed (RFC 2026-04-22 §1).
  - Freeze status: additive.
  - Owner: worker author.

- Evaluator, Criterion, and Rubric layout.
  - Reusable **Criterion** primitives live under
    `ergon_builtins/evaluators/criteria/`; reusable **Rubric** composites
    live under `ergon_builtins/evaluators/rubrics/`. Benchmark-specific
    Criteria and Rubrics live alongside the benchmark subpackage.
  - Semantics: a Criterion is a primitive scoring rule; a Rubric bundles
    Criteria into an Evaluator; an Evaluator is the top-level scoring unit
    bound to the benchmark via `evaluator_requirements()`.
  - Surface-area constraint: Rubrics bundle Criteria, not other Rubrics.
    Rubric nesting is not supported and there are no plans to change that.
  - Third-party users primarily extend at the Criterion layer.

- Model target resolution.
  - Builtins do not register cloud model backends. Model target strings are
    resolved centrally by `resolve_model_target` in `ergon_core`.
  - Freeze status: stable API; adding a backend is additive inside the
    providers layer.

- ReAct toolkit composition.
  - There is one concrete ReAct worker class — `ReActWorker` (slug `react-v1`,
    not registered bare) — with a fully explicit construction contract:
    `ReActWorker(name=..., model=..., task_id=..., sandbox_id=...,
    tools=[...], system_prompt=..., max_iterations=...)`. Every kwarg is
    required; no nullable-with-default fallbacks hide sizing decisions.
    Benchmark-specific glue (the toolkit itself, the system prompt, the
    iteration budget) is a **factory-closure** concern. Registry entries
    such as `"minif2f-react"` and `"swebench-react"` live in
    `registry_core.py` as small closures that build the `list[Tool]` and
    pass every kwarg — including `task_id` and `sandbox_id` — through to
    `ReActWorker(...)`. There is no `BenchmarkAdapter` ABC, no
    `on_run_start`/`on_run_end` hooks, no `transform_output` seam.
  - Per-task environment setup (clone a repo, install deps, apply a
    harness spec) lives in `BaseSandboxManager._install_dependencies`, not
    in the worker or an adapter. The sandbox manager reads the per-task
    payload via `queries.task_executions.get_task_payload(task_id)`.
  - Freeze status: adding a benchmark that needs ReAct means a new registry
    factory closure and (if it needs bespoke setup) a
    `BaseSandboxManager` subclass, not a new worker subclass or adapter.

- Onboarding profile.
  - Today a hand-maintained `BENCHMARK_DEPS` dict in
    `ergon_cli/onboarding/profile.py` declares each benchmark's E2B
    requirement, extras, and optional API keys so `ergon onboard` can prompt
    correctly. It is a parallel registry hand-synced with the benchmark
    registry — see invariant in section 4 and follow-up in section 7.

## 3. Control flow — adding a benchmark

At concept level, adding a benchmark means:

1. Create a subpackage under `ergon_builtins/benchmarks/<slug>/` that
   provides the canonical pieces (benchmark class, task schemas, optional
   sandbox + manager, criteria/rubric/evaluator, stub worker).
2. Register the benchmark in the appropriate registry module (core vs.
   data-extra).
3. Declare the benchmark's onboarding deps so `ergon onboard` prompts
   correctly (see invariants).
4. If the benchmark needs a custom sandbox template, wire a
   `ergon benchmark setup <slug>` path so users can build it.
5. Ship a stub worker so CI can exercise graph propagation and the eval
   pipeline without external LLM or sandbox dependencies.

Runtime data flow when a benchmark runs:

```
Benchmark loader → Task instances → Worker
                                      │
                                      ▼
                        SandboxManager (optional sandbox)
                                      │
                                      ▼
                    Evaluator → Rubric → Criteria (scoring)
                                      │
                                      ▼
                        Persisted evaluation rows
```

## 4. Invariants

- `type_slug` is the stable identifier used by CLI, onboarding, and
  registry. It matches the directory name by convention and MUST NOT change
  after a benchmark has run in any persisted dataset. Renaming orphans
  persisted runs.
- A custom sandbox template implies a matching
  `ergon benchmark setup <slug>` code path. No silent template dependencies.
- Every benchmark MUST ship a stub worker that exercises the graph
  propagation and eval pipeline without external LLM or sandbox
  dependencies. Enforcement is weak today: stub-worker coverage lags the
  registered benchmark set.
- Every registered benchmark MUST have a matching onboarding deps entry.
  The two registries being separate means they can drift, and have: the
  `BENCHMARK_DEPS` dict regressed on `swebench-verified` as recently as
  2026-04-17.
- Criteria MUST NOT spawn their own sandboxes. A Criterion that
  instantiates a `SandboxManager` directly bypasses the runtime's sandbox
  lifecycle and resource accounting. Enforced by
  `tests/state/test_criteria_do_not_spawn_sandboxes.py`.

## 5. Extension points

- **New benchmark.** Follow the concept-level recipe in section 3. Do not
  invent new file names for the canonical pieces — the layout convention is
  what makes the subpackage legible without reading every file.
- **New worker.** Add under `ergon_builtins/workers/baselines/` if it is
  cross-benchmark; alongside the benchmark otherwise. The contract is which
  task schemas it supports.
- **New model backend.** Add an explicit `resolve_model_target` branch in
  `ergon_core/core/providers/generation/`; prefer short, stable prefixes.
- **New Criterion.** Place in `ergon_builtins/evaluators/criteria/` if
  reusable, alongside the benchmark if benchmark-specific. This is the
  layer third-party users most often extend.
- **New Rubric.** Place in `ergon_builtins/evaluators/rubrics/` when
  reusable; alongside the benchmark otherwise. Rubrics bundle Criteria,
  never other Rubrics.
- **Template setup.** Today the pattern is implicit — some benchmarks ship
  a pre-built E2B template ID, others install dependencies at sandbox
  startup, others have no template at all. See section 7.
- **External registration.** Not supported today. A third-party package
  cannot register a benchmark without editing the registry module.

## 6. Anti-patterns

- **Adding a benchmark without a stub worker.** CI then cannot prove the
  pipeline still works end-to-end after refactors; the graph-propagation
  and eval paths become untested for that benchmark.
- **Inlining evaluator logic into `benchmark.py`.** The per-concern file
  split is what makes the subpackage navigable; collapsing it defeats the
  layout convention.
- **Forgetting the onboarding deps entry.** `ergon onboard` then fails to
  prompt for required API keys or extras, and the benchmark is unrunnable
  out of the box.
- **Custom sandbox template without a `ergon benchmark setup <slug>`
  path.** Users cannot build the template and the benchmark is
  non-runnable.
- **Benchmark code importing worker-specific internals.** Benchmarks
  describe tasks; they must be worker-agnostic so multiple workers can
  target the same benchmark.
- **Renaming `type_slug` after the benchmark has run in a shared
  environment.** Persisted runs become orphaned (see invariant).
- **A Criterion spawning its own sandbox.** Enforced by
  `tests/state/test_criteria_do_not_spawn_sandboxes.py`.
- **Worker subclasses for per-benchmark glue.** Benchmark-specific wiring
  is a factory-closure concern (registry), not a class hierarchy. The
  worker `__init__` contract is `tools: list[Tool]` + prompt only; a new
  benchmark that reuses `ReActWorker` means a new registry factory, not a
  new `ReActWorker` subclass.
- **Per-task setup inside workers.** Setup scripts (clone, install deps,
  environment bootstrap) belong to `BaseSandboxManager._install_dependencies`
  — sandbox lifecycle, not worker lifecycle. The manager reads the
  per-task payload via `queries.task_executions.get_task_payload(task_id)`.
- **Nullable-with-default kwargs on concrete Worker `__init__`.**
  `tools: list[Tool] | None = None`, `max_iterations: int = 10`, etc. hide
  sizing decisions in a shared default and mask per-benchmark intent.
  Concrete workers declare their required construction contract; factories
  pass every kwarg explicitly.

## 7. Follow-ups

Known limits and open questions touching this layer:

- The `BENCHMARK_DEPS` dict is a parallel registry that can drift from the
  benchmark registry; the drift invariant (section 4) is enforced only by
  vigilance today.
- Stub-worker coverage lags the registered benchmark set; the per-benchmark
  stub pattern (stub worker plus stub sandbox manager plus smoke test) is
  not yet uniform.
- Template setup is implicit — there is no declared shape for "this
  benchmark needs no template" vs. "this benchmark ships a template ID"
  vs. "this benchmark installs deps at sandbox startup".
- External benchmark registration has no supported path. Revisit if a
  concrete external use case appears.

Active RFCs and bugs in this area live under `docs/rfcs/active/` and
`docs/bugs/open/`; grep for `benchmark`, `criterion`, or `onboarding` in
those trees for the current set. This doc describes how the layer works
today and will be updated when an RFC lands and changes an invariant.

## Code map

| Concern | Location |
|---|---|
| Always-available benchmark registry | `ergon_builtins/registry_core.py` |
| Data-extra benchmark registry | `ergon_builtins/registry.py` |
| Benchmark subpackages | `ergon_builtins/benchmarks/<slug>/` |
| Cross-benchmark reference workers | `ergon_builtins/workers/baselines/` |
| Reusable Criterion primitives | `ergon_builtins/evaluators/criteria/` |
| Reusable Rubric composites | `ergon_builtins/evaluators/rubrics/` |
| Model backends | `ergon_builtins/models/` |
| Onboarding deps dict | `ergon_cli/onboarding/profile.py` |
