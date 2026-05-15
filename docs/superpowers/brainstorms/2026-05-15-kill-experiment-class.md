# Killing the `Experiment` Class: Public API Rethink

**Date:** 2026-05-15
**Status:** Proposal / brainstorm — not yet folded into a PR plan.
**Context:** Surfaced while workshopping PR 6.5 (domain colocation in `ergon_builtins`).  The discussion started with "where should per-benchmark `Sandbox`/`Toolkit` live?", moved through "what's the composition layer in v2?", and landed at "does `Experiment` actually earn its keep as a public API concept?"

## TL;DR

In v2 as it stands, `Experiment` is a Pydantic struct that holds `(benchmark, name, description, metadata)` — three pieces of metadata wrapped around a Benchmark.  All the composition (worker, sandbox, evaluators) already lives **inside** the Benchmark via inline `Task.worker` / `Task.sandbox` / `Task.evaluators`.  So `Experiment` is pure accidental abstraction: no fields that need to be class fields rather than function parameters, no behaviour that's not just persistence ceremony.

**Proposal:** delete the `Experiment` *class*, but keep the word "experiment" as a **string identifier** that groups related runs.  Concretely:

```
Benchmark               — the configured unit of work (already exists)
DefinitionHandle        — identity + metadata for one persisted Benchmark
persist_benchmark(b, *, name, experiment=None, metadata=None) -> DefinitionHandle
launch_run(definition_id) -> RunHandle      (already exists)
```

An **experiment** becomes a `str | None` column on the persisted definition row.  Two benchmarks persisted with the same `experiment="strategy-ablation-2026-05-14"` belong to the same experiment.  No `Experiment` class, no `Cohort` class — just a string.

This naming is deliberate: the word "experiment" stays in the user's vocabulary (it's the natural research term for "I ran a benchmark with two configurations to compare them"), but the *abstraction* drops from "class holding composition" to "string tag grouping definitions."  Users keep saying "I ran an experiment"; the code stops carrying a class that pretended to be composition.

The **CLI** becomes a thin convenience over the Python API.  Per-benchmark `experiment.py` files (currently in PR 8's plan) are deleted — the CLI dispatches via two flat dicts: `BENCHMARK_CLASSES[slug] -> type[Benchmark]` and `WORKER_FACTORIES[slug] -> dict[name, factory]`.

## The observation

`Experiment` does exactly one thing today: wrap a Benchmark with a name and metadata for persistence.  Walk through what's in the class:

| `Experiment` field | What it actually is |
|---|---|
| `benchmark` | The thing being persisted; doesn't need wrapping |
| `name` | A label, could be a function parameter |
| `description` | Same |
| `metadata` | Same |

There is no field on `Experiment` that needs to be a class field rather than a function parameter to a `persist_benchmark(benchmark, *, name, ...)` call.  The class offers no behaviour beyond construction and persistence routing.

Worse, the name `Experiment` carries the v1 connotation of "composition tuple" (benchmark + worker_spec + evaluator_spec), which it explicitly is **not** in v2.  Every time we explain the architecture, someone has to be told "no, in v2 the Experiment is just a labeled persistable Benchmark; composition lives inside the Benchmark."  That's a smell.

## The proposal

### Public API surface

```python
# 1. Configure a Benchmark (per PR 6.5: parameterised constructor)
benchmark = MiniF2FBenchmark(
    worker_factory=make_minif2f_react_worker,
    sandbox_factory=LeanSandbox,      # default — usually omit
    evaluator_factory=make_minif2f_rubric,
    limit=10,
)

# 2. Persist with a label + optional experiment grouping
handle = persist_benchmark(
    benchmark,
    name="minif2f-react-2026-05-14",
    experiment="strategy-ablation-2026-05-14",     # optional string tag
    metadata={"created_by": "charlie", "notes": "..."},
)

# 3. Launch
await launch_run(handle.definition_id)
```

That's the entire authoring API.  Three calls.  Composable, version-controllable, importable from a notebook.

### What dies (classes / DTOs / files)

- `ergon_core.api.experiment.Experiment` — **class deleted**.  The word "experiment" survives as a string-typed concept, not a class.
- `ergon_core.core.application.experiments.service.ExperimentService.define_benchmark_experiment` — replaced by `persist_benchmark`
- `ExperimentDefineRequest` DTO — no longer needed; arguments go directly to `persist_benchmark`
- `BUILTIN_EXPERIMENT_FACTORIES` (PR 8) — replaced with `BENCHMARK_CLASSES` + `WORKER_FACTORIES` dicts
- Per-benchmark `experiment.py` files (PR 8's current plan) — never created; replaced by simpler CLI dispatch
- The "experiment-as-composition" framing in the v2 RFC — replaced with "Benchmark is the configured unit; an experiment is just a string tag grouping related definitions"

### What churns (renames, signature changes)

- `ExperimentRecord` SQLAlchemy model → renamed to `BenchmarkDefinitionRecord`.  The table itself can keep its existing physical name (`experiments`?) to avoid a destructive Alembic migration — only the Python model class renames.  *Open question: is the existing table name something other than `experiments`?  If so, no churn.*
- `persist_definition(experiment)` → `persist_benchmark(benchmark, *, name, experiment=None, metadata=None) -> DefinitionHandle`.  Signature change: takes a `Benchmark`, not an `Experiment` wrapper.  The `experiment=` kwarg here is the **string tag**, not the deleted class.
- Inngest event payloads that name `experiment_id` semantically — re-check whether they mean "the definition_id" (just a name change to `definition_id`) or whether they referenced the wrapper-class field surface (need rewiring).
- Dashboard TypeScript that queries `ExperimentRecord` by name — adapt to the renamed model / column-renamed shape.

### What lives (unchanged)

- `Benchmark` ABC + `build_instances()` returning `Task` objects with inline worker/sandbox/evaluators
- `MiniF2FBenchmark(worker_factory=..., sandbox_factory=...)` parameterised constructor (PR 6.5 Task 5)
- `Task.worker` / `Task.sandbox` / `Task.evaluators` inline fields (PR 5)
- `launch_run(definition_id)` — already correct shape
- `DefinitionHandle(definition_id, benchmark_type, ...)` — already exists
- The user-facing word **"experiment"** — survives as a string column, a CLI flag, and a verb in the docs.  No vocabulary change for users.

### What's new

- `persist_benchmark(benchmark, *, name, experiment=None, metadata=None) -> DefinitionHandle` — replaces `persist_definition(experiment_obj)`
- `experiment: str | None` column on the persisted `BenchmarkDefinitionRecord`
- `ergon_core.api.experiments` query helper — minimal surface, just `list_definitions_in_experiment(name: str) -> list[DefinitionHandle]` (or skip the helper and use a `select` directly; YAGNI is fine).
- CLI commands:
  - `ergon experiment show <name>` — lists definitions in an experiment with run status
  - `--experiment=<name>` flag on `ergon run <benchmark>` to tag a new definition into an experiment

## Worked examples

### Two workers, same benchmark, one experiment — Python

```python
from ergon_builtins.benchmarks.minif2f import (
    MiniF2FBenchmark,
    make_minif2f_react_worker,
    make_minif2f_cot_worker,
)
from ergon_core.api import persist_benchmark, launch_run

EXPERIMENT = "minif2f-strategy-ablation-2026-05-15"

for label, worker_factory in [
    ("react", make_minif2f_react_worker),
    ("cot", make_minif2f_cot_worker),
]:
    benchmark = MiniF2FBenchmark(worker_factory=worker_factory, limit=10)
    handle = persist_benchmark(
        benchmark,
        name=f"minif2f-{label}",
        experiment=EXPERIMENT,
        metadata={"strategy": label},
    )
    await launch_run(handle.definition_id)
```

4 imports, 11 lines of authoring code.  Two definitions persisted into the same experiment.  No `Experiment` class anywhere — `EXPERIMENT` is just a string the user picked.

### Observing the runs — CLI

The CLI does not start the runs (that was Python above).  It observes them:

```bash
ergon experiment show ablation-2026-05-15
# NAME              DEFINITION_ID    RUNS    STATUS
# minif2f-react     abc-123-...      1       running
# minif2f-cot       def-456-...      1       pending

ergon run status <run-id>
ergon run cancel <run-id>
```

See the next section for the full rationale.

## CLI role, made explicit

The CLI has **one honest role**: lifecycle and observation of persisted state.  It is **not** an authoring interface, not a convenience wrapper, and not a parallel dispatch path.  There is exactly one way to start a run: write Python that calls `persist_benchmark(...)` + `launch_run(...)`.

### What the CLI keeps

- `ergon run status <run-id>` — check status of a running run
- `ergon run cancel <run-id>` — cancel a running run
- `ergon run list [--experiment=<name>]` — list runs, optionally filtered
- `ergon experiment show <name>` — list definitions in an experiment, with run status
- `ergon experiment list` — list known experiment names
- Future: `ergon dashboard` (open the local dashboard), `ergon logs <run-id>`, etc.

All of these operate on state that **already exists in the database**.  The CLI's job is to inspect and steer; not to create.

### What the CLI drops

- ❌ `ergon experiment define --benchmark <slug> ...` — gone.  No CLI-side authoring.
- ❌ `ergon experiment run <definition-id>` — gone.  Use Python; `launch_run` is one line.
- ❌ `ergon run <benchmark> --worker <name> ...` — gone.  No stock-benchmark dispatch from the CLI.
- ❌ `BENCHMARK_CLASSES` + `WORKER_FACTORIES` dicts — gone.  No CLI registry of benchmarks/workers.
- ❌ `BUILTIN_EXPERIMENT_FACTORIES` (PR 8's design) — gone.  Never built.
- ❌ Per-benchmark `experiment.py` / `_cli_factory.py` files — gone.  Never built.

### Why kill the CLI authoring route entirely?

The PR 8 plan introduces a *second* authoring route: argparse → factory dict → benchmark constructor → `Experiment` → persist.  That's a parallel surface that:

- **Must be kept in sync** with the Python API (every benchmark constructor kwarg needs a CLI flag; every worker factory needs a registry entry).
- **Misleads new contributors** about where the "real" authoring happens.
- **Constrains the Python API** to only expose what argparse can pass (no callables, no objects, no inline lambdas).
- **Has its own test surface** doubling the assertions for every code path.

By having exactly **one** authoring path (Python), all of those costs disappear.  Reproducibility is "the script that built the experiment is checked into your repo."  No drift between two surfaces because there's only one.

The argument for keeping a CLI authoring route is "users who don't want to write Python."  The counter-argument is: those users were going to write a multi-line argparse invocation anyway (`--limit 10 --worker react --experiment=ablation-2026-05-15 --name="run-1"`), which is *more* characters than the equivalent Python and not version-controlled.  A 5-line Python script is strictly better for that user too — they just need to know it exists.

### Authoring example (Python only)

```python
# kick_off.py — checked into the user's repo, version-controlled
import asyncio
from ergon_builtins.benchmarks.minif2f import (
    MiniF2FBenchmark, make_minif2f_react_worker,
)
from ergon_core.api import persist_benchmark, launch_run

async def main():
    benchmark = MiniF2FBenchmark(worker_factory=make_minif2f_react_worker, limit=10)
    handle = persist_benchmark(benchmark, name="minif2f-react", experiment="ablation-2026-05-15")
    await launch_run(handle.definition_id)
    print(f"DEFINITION_ID={handle.definition_id}")

asyncio.run(main())
```

```bash
$ uv run python kick_off.py
DEFINITION_ID=abc-123-...

$ ergon experiment show ablation-2026-05-15
NAME              DEFINITION_ID    RUNS    STATUS
minif2f-react     abc-123-...      1       running

$ ergon run status <run-id>
status: running, tasks_completed: 3/10
```

The CLI never appears in the authoring step.  It appears only when observing.

### Implementation shape (CLI side)

The lifecycle commands read from the database via existing repositories.  No new factory dicts.  No per-benchmark imports.  The full CLI source under this proposal:

```python
# ergon_cli/commands/run.py  — observation only

def handle_run_status(args: Namespace) -> int:
    state = RunRepository().get_state(UUID(args.run_id))
    print(f"status: {state.status}, tasks_completed: {state.completed}/{state.total}")
    return 0

def handle_run_cancel(args: Namespace) -> int:
    cancel_run(UUID(args.run_id), reason=args.reason or "cli-cancel")
    return 0

def handle_run_list(args: Namespace) -> int:
    runs = RunRepository().list(experiment=args.experiment)  # filter optional
    for r in runs:
        print(f"{r.run_id}  {r.experiment or '-':30s}  {r.status}")
    return 0
```

```python
# ergon_cli/commands/experiment.py  — observation only

def handle_experiment_show(args: Namespace) -> int:
    defs = DefinitionRepository().list(experiment=args.experiment_name)
    for d in defs:
        latest = RunRepository().latest_for_definition(d.definition_id)
        print(f"{d.name:30s}  {d.definition_id}  {latest.status if latest else 'no runs'}")
    return 0

def handle_experiment_list(args: Namespace) -> int:
    names = DefinitionRepository().distinct_experiments()
    for n in names:
        print(n)
    return 0
```

That's the entire CLI command surface for the experiment / run lifecycle.  No `BENCHMARK_CLASSES`.  No `WORKER_FACTORIES`.  No `BUILTIN_EXPERIMENT_FACTORIES`.  No per-benchmark CLI registration burden.  Adding a new benchmark requires zero CLI changes — users just import it from Python.

## Naming choice: why we keep the word "experiment"

Two alternatives were considered for the grouping-string concept:

- **`cohort`** — borrowed from clinical-trials / observational-study terminology.  Precise, but jargon-y for a Python API.
- **`experiment`** — the word every researcher already uses for "I ran this benchmark with two configurations to compare them".  Carries some baggage from the deleted class, but that baggage is what we *want* the user to keep in their vocabulary.

**Decision: keep `experiment` as the user-facing name.**  The class dies, but the *word* survives as a string label.  Users say "I ran experiment X with two definitions"; the code stores `experiment: str | None` on the definition row.  Vocabulary continuity for users, no class-level abstraction.

This is the same move as collapsing `WorkerSpec` into "just a slug + name" in earlier PRs — keep the word, drop the class.

## Experiment string vs structured class

**Decision: string column, not a class.**  YAGNI for now.

What you need to do with experiments in practice:
- Tag related definitions with a common label
- Query "all definitions in experiment X"
- Compare their results in the dashboard

All of that works with a single string column.  If we later need structured experiment metadata (shared parameters, ablation axes, comparison hypotheses, parent/child relationships), add an `Experiments` table that definitions FK into — **as a separate later RFC**.  Not before.

The CLI gets one `--experiment=<name>` flag.  Python users pass `experiment="..."` to `persist_benchmark`.  Done.

## What's the migration cost?

Real but bounded.  Sketch:

### Code changes
- **Hard delete** `ergon_core/api/experiment.py` (the `Experiment` class).  No deprecation alias.
- Delete `ergon_core/core/application/experiments/service.py::define_benchmark_experiment`
- **Rename in place**: `persist_definition(experiment)` → `persist_benchmark(benchmark, *, name, experiment=None, metadata=None) -> DefinitionHandle`.  Signature change.  No "add new + deprecate old" — one rename, all callers updated in the same PR.
- Rename `ExperimentRecord` SQLAlchemy model → `BenchmarkDefinitionRecord` in `ergon_core/core/persistence/telemetry/models.py`.  Rename the **physical table too** — there's no production data to preserve, and the Alembic chain is being dropped/regenerated wholesale later anyway.
- Add `experiment: str | None` column on the renamed `BenchmarkDefinitionRecord` (just a SQLModel field; no fiddly Alembic dance since tables get dropped/recreated).
- Update every test that references `Experiment` (~20 files based on rough grep).
- Update Inngest event payloads that mention "experiment" (probably 5-10 places).
- Update dashboard reads — the dashboard queries `ExperimentRecord` directly, so TypeScript needs updating.
- **Delete the CLI authoring route**: `ergon_cli/commands/experiment.py::handle_experiment_define`, `handle_experiment_run`, and any tests around them.
- **Hard break on CLI** — no deprecation warnings on removed commands.  Ergon is pre-1.0; clean break is acceptable.

### Doc changes
- v2 RFC: rewrite `00-readme.md`, `01-api-surface.md` to reflect the cleaner model (no `Experiment` class; `experiment` is a string tag).
- `docs/architecture/01_public_api.md`: drop `Experiment` from the type list; add `persist_benchmark`; note Python-only authoring.
- `docs/architecture/06_builtins.md`: update to reflect lifecycle-only CLI; add a "Discovery" section pointing at the new `README.md` catalogue.
- **New `ergon_builtins/benchmarks/README.md`** — discovery doc listing every builtin benchmark + the workers it ships with, plus the import path.  Replaces the CLI registry as the catalogue.

### What we DON'T need
- No Alembic migration dance.  Tables are dropped/recreated; we just adjust the SQLModel.
- No deprecation aliases for either `Experiment` or the removed CLI commands.
- No `launch_run_sync(...)` wrapper.  Users write `asyncio.run(launch_run(...))` in their scripts.
- No `ergon list benchmarks` static-catalogue command.  Catalogue lives in the README.

### Effort estimate
- Pure code + tests: ~1 PR worth of focused work.
- Plus the dashboard TypeScript update.
- Plus the catalogue README.

Not trivial.  Not huge.  Probably 1-2 days of focused work.

## Where in the PR sequence?

### Decision: fold everything into PR 6.5; PR 8 becomes the lifecycle-CLI cleanup PR.

PR 6.5's scope expands from "domain colocation" to "domain colocation + API surgery."  Concretely PR 6.5 now does:

- **Original scope (kept):**
  - File moves (`sandboxes/lean.py` → `benchmarks/minif2f/sandbox.py`, etc.)
  - Rename `worker_factory.py` → `workers.py` + split out legacy
  - Add `sandbox/` top-level dir stub
  - Parameterise `MiniF2FBenchmark` with `worker_factory` / `sandbox_factory` / `evaluator_factory` kwargs
  - Architecture doc updates (cardinality matrix, anti-patterns)
  - v2 RFC framing rewrite

- **New scope (added):**
  - **Drop Task 4** (the `experiment.py` placeholder) — never create the file.
  - **Hard delete** `ergon_core.api.experiment.Experiment` class.  No alias.
  - **Rename in place** `persist_definition(experiment)` → `persist_benchmark(benchmark, *, name, experiment=None, ...)`.
  - **Rename** `ExperimentRecord` SQLModel → `BenchmarkDefinitionRecord` (table too — no data to preserve).
  - **Add** `experiment: str | None` column on the renamed model.
  - **Delete** CLI authoring commands: `ergon experiment define`, `ergon experiment run`, the entire `BUILTIN_EXPERIMENT_FACTORIES` design.
  - **Update** every test that constructs `Experiment(...)` to use the new shape.
  - **Update** Inngest event payloads that name `experiment` semantically.
  - **Update** the dashboard's TypeScript reads of `ExperimentRecord`.
  - **Add** `ergon_builtins/benchmarks/README.md` catalogue.

PR 8 (the existing `09-pr-08-cli-composition.md`) becomes a **slim cleanup PR** with one job: the lifecycle / observation commands.

- Add `ergon run status <run-id>`, `ergon run cancel <run-id>`, `ergon run list [--experiment=<name>]`
- Add `ergon experiment show <name>`, `ergon experiment list`
- Delete the now-stale parts of its existing plan (factory dict task, per-benchmark `experiment.py` task, etc.).

### Honest pushback on the sequencing

**I'd push back on this once before you commit.**  Folding the `Experiment` kill into PR 6.5 makes PR 6.5 a substantially bigger and riskier PR than originally scoped.  Concretely:

- **Original PR 6.5:** ~6 file moves, 1 ctor change, ~15 doc/import updates.  Reviewable in 30 minutes.  Low risk — it's mostly mechanical.
- **PR 6.5 with the kill folded in:** all of the above PLUS deletion of a public API class, signature change on the persistence function, SQLModel + table rename, new column, CLI command deletion, dashboard TypeScript update, ~20-30 test files touched, Inngest payload changes.  Closer to a 2–4 hour focused review.  Higher risk because it crosses layers (API / persistence / CLI / dashboard).

**Two reasons you might still want to fold it in:**

1. **No intermediate state** — landing the parameterised benchmark with `Experiment` still alive creates a window where the architecture is half-migrated.  Folding avoids that.
2. **Velocity** — one big PR is sometimes faster than two sequential PRs through review and CI.

**Two reasons you might want to split it:**

1. **Reviewability** — PR 6.5 is meant to be the "easy win" reorganization.  Folding makes it harder to spot bugs.
2. **Bisectability** — if something breaks after PR 6.5 lands, "was it the file moves or the Experiment kill?" becomes a harder bisect.

**Middle-ground option not yet considered:** ship PR 6.5 as two commits in one branch, but as one PR — first commit = file moves + parameterise (the "easy win"), second commit = Experiment kill + persist_benchmark + CLI deletion (the surgery).  Same PR, but the diff is mentally splittable for review.  Then PR 8 is the lifecycle CLI cleanup as planned.

**My recommendation: do the middle-ground.** One PR titled "PR 6.5: domain colocation + kill Experiment class" with two clearly labelled commits.  Get the benefits of one-shot cutover without making the diff incomprehensible.  PR 8 = lifecycle CLI cleanup, as you suggested.

If you prefer the split-into-two-PRs version (PR 6.5 = original scope, PR 6.6 = kill), say so and I'll write the plans that way.

## Decisions taken

All ten questions raised during the brainstorm are now resolved.  Recorded here for the plan author:

| # | Decision | Choice |
|---|---|---|
| 1 | Kill `Experiment` class? | ✅ **Yes — hard delete, no alias** |
| 2 | Keep `experiment` as a `str \| None` column? | ✅ **Yes** |
| 3 | Kill the CLI authoring route entirely? | ✅ **Yes — no `ergon run <bench>`, no `experiment define/run`** |
| 4 | `persist_definition` → `persist_benchmark`: rename in place vs add+deprecate? | ✅ **Rename in place** (signature change; all callers updated in one PR) |
| 5 | `ExperimentRecord` SQLModel rename: keep table name, or rename table too? | ✅ **Rename the table too** — no production data; Alembic chain gets dropped/regenerated wholesale |
| 6 | CLI removed commands: deprecation warnings, or clean break? | ✅ **Clean break** — Ergon is pre-1.0 |
| 7 | PR 6.5 Task 4 (create `experiment.py` stub): keep or drop? | ✅ **Drop entirely** — file never gets created |
| 8 | PR sequencing | ✅ **Fold into PR 6.5; PR 8 becomes lifecycle-CLI cleanup** (with my pushback noted above re: PR-6.5 size) |
| 9 | `ergon list benchmarks` static-catalogue command? | ✅ **Skip** — `ergon_builtins/benchmarks/README.md` is the catalogue |
| 10 | Sync `launch_run_sync` wrapper? | ✅ **Skip** — users write `asyncio.run(launch_run(...))` |

Once these are recorded, the next step is to turn this brainstorm into a concrete plan: `docs/superpowers/plans/2026-05-15-kill-experiment-class.md` (the work) plus updates to `docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/07b-pr-6-5-domain-colocation.md` (expand PR 6.5's scope) and `09-pr-08-cli-composition.md` (slim PR 8 down to lifecycle commands).

## What this is NOT proposing

- **Not changing `Benchmark`'s shape.**  PR 5/6's design (inline worker/sandbox/evaluators on each Task) stands.
- **Not changing `Task`.**  The object-bound authoring shape is correct.
- **Not changing the worker / sandbox / toolkit abstractions.**  Those earn their keep.
- **Not killing the CLI binary.**  `ergon` still exists; it just stops being an authoring interface.  Lifecycle / observation commands (`status`, `cancel`, `experiment show`, etc.) stay.
- **Not changing how runs / evaluations work.**  Run lifecycle is unchanged; only the persistence-time class and the CLI authoring path disappear.
- **Not removing the word "experiment" from the user's vocabulary.**  It becomes a string label (`experiment="..."`) rather than a class (`Experiment(...)`).

The change is targeted: (1) one class (`Experiment`) + its persistence ceremony, (2) the CLI authoring route (`define` / `run <benchmark>` commands and the factory-dict layer that powers them), and (3) the misleading framing around both.  Everything else stays.

## Summary of decisions taken in discussion

The brainstorm grew over several rounds.  Recorded here for future readers:

1. **`Experiment` class dies.**  Hard delete, no alias.  It's a wrapper around `(benchmark, name, description, metadata)` with no behaviour beyond persistence routing.  Function parameters do the same job with less abstraction.
2. **The word "experiment" survives as a `str | None` column.**  Two definitions with the same `experiment="x"` tag are part of the same experiment.  No `Cohort` or `Experiment` class.
3. **The CLI authoring route dies entirely.**  Clean break, no deprecation.  No `ergon experiment define`, no `ergon run <benchmark> --worker <name>`, no `BENCHMARK_CLASSES` / `WORKER_FACTORIES` dicts, no per-benchmark `experiment.py` files.  One authoring path: Python.
4. **The CLI keeps lifecycle / observation commands.**  `run status`, `run cancel`, `run list`, `experiment show`, `experiment list`.  All read-only against persisted state.  No static `list benchmarks` command — the catalogue is a README in `ergon_builtins/benchmarks/`.
5. **`persist_definition` → `persist_benchmark`** — rename in place, signature change, all callers updated in one PR.
6. **`ExperimentRecord` SQLModel + physical table both rename** to `BenchmarkDefinitionRecord`.  No production data; Alembic chain gets dropped/regenerated wholesale, so no migration dance.
7. **Async authoring stays async.**  No `launch_run_sync` wrapper; users write `asyncio.run(launch_run(...))`.
8. **PR sequencing: fold into PR 6.5; PR 8 becomes slim lifecycle-CLI cleanup.**  My pushback on size is recorded above — the middle-ground recommendation is "one PR, two clearly-labelled commits."  Final call is the user's.

These eight decisions form the spine of the eventual PR 6.5 (expanded) + slimmed-PR-8 plans.
