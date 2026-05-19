# PR 6.5 — Domain Colocation + Kill `Experiment` Class

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two related changes shipped together, structured as **two commits in one PR**:

1. **(Phase 1: Domain colocation)** Re-organise `ergon_builtins` so the file layout matches the actual coupling cardinalities between `Sandbox`, `Toolkit`, `Worker`, `Evaluator`, `Criterion`, and `Benchmark`.  Collapse the misleading top-level `sandboxes/` and `toolkits/` directories into per-benchmark subpackages; leave the genuinely cross-cutting `Worker` classes at the top level; rewrite the v2 RFC's "composability" framing.

2. **(Phase 2: Kill `Experiment` class)** Delete the `Experiment` class outright.  Replace `persist_definition(experiment)` with `persist_benchmark(benchmark, *, name, experiment=None, metadata=None)`.  Rename `ExperimentRecord` SQLModel + physical table to `BenchmarkDefinitionRecord`.  Add an `experiment: str | None` column for grouping.  Delete the CLI authoring route (`ergon experiment define`, `ergon experiment run`).  Update all callers / tests / Inngest payloads / dashboard reads.  See `docs/superpowers/brainstorms/2026-05-15-kill-experiment-class.md` for the full rationale.

**Why one PR with two commits, not two PRs:** the two pieces share a target architecture and benefit from one-shot cutover (no intermediate state where the per-benchmark layout exists but `Experiment` is still alive).  The commits stay clearly labelled so the diff is mentally splittable for review.

**Architecture (final state after both commits):**

```
1:1 with benchmark (lives in benchmarks/<slug>/):
    sandbox.py  •  toolkit.py  •  prompts.py
    workers.py  •  benchmark.py  •  rubric.py
    criteria/<benchmark-specific criteria>

N:1 across benchmarks (lives at top level):
    workers/baselines/    ← ReActWorker, CoTWorker, ReflexionWorker
    sandbox/              ← _manager_backed.py (shared sandbox adapter)
    evaluators/criteria/  ← reusable primitives (e.g. LLMJudgeCriterion)
    evaluators/rubrics/   ← reusable composites
    benchmarks/README.md  ← static catalogue (replaces deleted CLI registry)
```

Note: no per-benchmark `experiment.py` file.  Authoring is Python-only; CLI is observation-only (lifecycle commands move to PR 8).

**Tech Stack:** File moves, import rewrites, doc updates, SQLModel/table rename, public-API surgery on `ergon_core.api`, CLI command deletion, dashboard contract regeneration (`pnpm run generate:contracts`).  Note: the dashboard does **not** use Drizzle; it reads via the REST API + generated Zod contracts from Pydantic JSON Schema (see `ergon-dashboard/scripts/generate-rest-contracts.mjs`).  So the dashboard impact of the rename is mostly automated codegen + a typecheck pass — not direct DB queries.

**Sequencing:** Ships as a follow-up to PR 6, before PR 8 and PR 10a.  Locks in both the file layout AND the API shape before the SWEBench / ResearchRubrics / GDPEval verticals replicate the PR 6 pattern (which would otherwise amplify the wrong layout AND build doomed `Experiment(...)` constructors 3× over).  PR 8 then ships the slim lifecycle-only CLI on top of the cleaned-up API.

---

## Files

### Phase 1 (Commit 1: Domain Colocation)

**Move (PR 6 outputs → benchmark-colocated paths):**

```text
ergon_builtins/ergon_builtins/sandboxes/lean.py
    → ergon_builtins/ergon_builtins/benchmarks/minif2f/sandbox.py
ergon_builtins/ergon_builtins/toolkits/minif2f.py
    → ergon_builtins/ergon_builtins/benchmarks/minif2f/toolkit.py
ergon_builtins/ergon_builtins/toolkits/_minif2f_tools.py
    → ergon_builtins/ergon_builtins/benchmarks/minif2f/_tools.py
```

**Rename:**

```text
ergon_builtins/ergon_builtins/benchmarks/minif2f/worker_factory.py
    → ergon_builtins/ergon_builtins/benchmarks/minif2f/workers.py
```

**Create (Phase 1):**

```text
ergon_builtins/ergon_builtins/benchmarks/minif2f/_legacy_workers.py
ergon_builtins/ergon_builtins/sandbox/__init__.py
```

**Delete (Phase 1 — now-empty top-level dirs):**

```text
ergon_builtins/ergon_builtins/sandboxes/__init__.py
ergon_builtins/ergon_builtins/sandboxes/                  (directory)
ergon_builtins/ergon_builtins/toolkits/__init__.py
ergon_builtins/ergon_builtins/toolkits/                   (directory)
```

**Modify (Phase 1 — import path updates + parameterised constructor):**

```text
ergon_builtins/ergon_builtins/benchmarks/minif2f/__init__.py
ergon_builtins/ergon_builtins/benchmarks/minif2f/benchmark.py
ergon_builtins/ergon_builtins/workers/baselines/react_worker.py
ergon_builtins/registry_core.py                            # if it imports MiniF2FReactWorker
ergon_builtins/registry.py                                  # likewise
ergon_builtins/tests/unit/benchmarks/test_minif2f_task_shape.py
ergon_core/tests/unit/runtime/test_experiment_definition_writer.py
ergon_core/tests/unit/runtime/test_experiment_definition_service.py
scripts/check_suppression_budget.py   # path comments only
```

### Phase 2 (Commit 2: Kill `Experiment` Class)

**Delete (Phase 2):**

```text
ergon_core/ergon_core/api/experiment.py                          # the Experiment class
ergon_core/ergon_core/core/application/experiments/models.py     # ExperimentDefineRequest DTO
ergon_cli/ergon_cli/commands/experiment.py                       # CLI authoring handlers (define/run)
ergon_cli/tests/unit/cli/test_experiment_cli.py                  # tests for deleted handlers
```

(The `ergon_cli/commands/experiment.py` file may be reduced rather than deleted if other commands live there; PR 8 then adds lifecycle commands back to a new `commands/experiment.py` / `commands/run.py`.)

**Create (Phase 2):**

```text
ergon_builtins/ergon_builtins/benchmarks/README.md   # static benchmark catalogue
```

**Rename (Phase 2 — SQLModel + physical table):**

```text
ergon_core/ergon_core/core/persistence/telemetry/models.py::ExperimentRecord
    → BenchmarkDefinitionRecord
# Physical table: rename in the SQLModel definition.  No Alembic migration —
# the migration chain is being dropped/regenerated wholesale; no production
# data to preserve.
```

**Modify (Phase 2 — API surgery + callsites):**

```text
ergon_core/ergon_core/api/__init__.py                             # drop Experiment export, add persist_benchmark
ergon_core/ergon_core/api/persistence.py                          # rename persist_definition → persist_benchmark; new signature
ergon_core/ergon_core/core/application/experiments/service.py     # remove define_benchmark_experiment
ergon_core/ergon_core/core/application/experiments/launch.py      # update event payloads
ergon_core/ergon_core/core/application/experiments/definition_writer.py
ergon_core/ergon_core/core/persistence/telemetry/models.py        # add experiment: str | None column
# Plus every test that constructs Experiment(...) — find via:
#   rg "Experiment\(" ergon_core/tests/ ergon_builtins/tests/ ergon_cli/tests/ tests/
# Plus every event payload that names "experiment" semantically — find via:
#   rg "experiment_id\|experiment=" ergon_core/ ergon_cli/
# Plus the dashboard contract regeneration:
ergon-dashboard/src/generated/                                    # regenerated by `pnpm run generate:contracts`
# (No direct file edits in ergon-dashboard/src/ — the Zod schemas are
#  produced from backend Pydantic JSON Schema via codegen.  Hand-written
#  TypeScript files that consume the regenerated types will typecheck-fail
#  if naming drifts; fix those manually.)
```

### Shared (touched by both phases — finalised in Phase 2)

```text
docs/architecture/06_builtins.md                                  # updates from both phases
docs/architecture/01_public_api.md                                # drops Experiment, adds persist_benchmark
docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/00-readme.md
docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/01-api-surface.md
docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/09-pr-08-cli-composition.md
docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/11-pr-10a-swebench.md
docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/11b-pr-10b-researchrubrics.md
docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/11c-pr-10c-gdpeval.md
docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/12-pr-11-deletion-final-schema.md
docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/00-program.md
```

## Current State

After PR 6, `ergon_builtins/` looks like:

```
ergon_builtins/
├── benchmarks/
│   └── minif2f/
│       ├── benchmark.py
│       ├── worker_factory.py    ← legacy + v2 factories mixed
│       ├── rubric.py
│       ├── sandbox_manager.py   ← v1 (deleted in PR 11)
│       └── ...
├── sandboxes/                   ← top-level: looks cross-cutting
│   ├── __init__.py
│   └── lean.py                  ← but it's 1:1 with minif2f
├── toolkits/                    ← top-level: looks cross-cutting
│   ├── __init__.py
│   ├── minif2f.py               ← but it's 1:1 with minif2f
│   └── _minif2f_tools.py        ← same
├── workers/
│   └── baselines/
│       └── react_worker.py      ← genuinely N:1 (reused by every benchmark)
└── evaluators/                  ← genuinely cross-cutting
    ├── criteria/
    └── rubrics/
```

The top-level `sandboxes/` and `toolkits/` directories suggest
cross-benchmark reuse that doesn't exist: `LeanSandbox` is only usable
with `MiniF2FToolkit`; `MiniF2FToolkit` is only usable inside
`LeanSandbox`.  Once PR 10a–10c land, every benchmark adds one file to
each top-level dir even though no file is ever imported by anything
outside its own benchmark.

The genuinely cross-cutting things (`ReActWorker`, the shared
manager-backed runtime adapter `_manager_backed.py` planned in PR 10a)
do belong at the top level.

## Target State For This PR

```
ergon_builtins/
├── benchmarks/
│   └── minif2f/
│       ├── benchmark.py
│       ├── sandbox.py           ← was sandboxes/lean.py
│       ├── toolkit.py           ← was toolkits/minif2f.py
│       ├── _tools.py            ← was toolkits/_minif2f_tools.py
│       ├── workers.py           ← was worker_factory.py (v2 factories only)
│       ├── _legacy_workers.py   ← legacy MiniF2FReactWorker block, marked
│       │                          for PR 11 deletion (clear separation)
│       ├── experiment.py        ← (new file: experiment factory; see Task 4)
│       ├── rubric.py
│       ├── sandbox_manager.py   ← still v1, still deleted in PR 11
│       └── criteria/
├── sandbox/                     ← NEW: cross-cutting sandbox-adapter infra
│   └── (PR 10a will add _manager_backed.py here)
├── workers/
│   └── baselines/
│       └── react_worker.py      ← still here, unchanged
└── evaluators/                  ← unchanged
```

`sandboxes/` (plural) and `toolkits/` are gone.  Every benchmark's
domain-specific bundle (sandbox + toolkit + tools + worker factories +
prompts + rubric + experiment factory) lives in `benchmarks/<slug>/`.
The new top-level `sandbox/` (singular) holds *cross-benchmark*
sandbox infrastructure — currently empty until PR 10a populates it
with `_manager_backed.py`.

**Why `sandbox/` (singular) instead of `runtime/`:** the dir's
contents are specifically about sandbox-adapter wiring (E2B SDK
adapter, manager-backed runtime adapter).  Naming it `sandbox/`
(singular, top-level) signals "infrastructure for the `Sandbox`
abstraction" without the plural's implication of "a catalogue of
sandboxes" that bit us with `sandboxes/`.  Distinct from the
`ergon_core.api.sandbox` namespace by virtue of living under
`ergon_builtins/` (no name collision in practice).

## Why This Layout

The cardinality matrix (derived from the actual coupling, not the
aspirational "composability" framing):

| Pair | Cardinality | Lives where |
|------|-------------|-------------|
| Benchmark ↔ Sandbox | 1↔1 (in practice) | `benchmarks/<slug>/sandbox.py` |
| Sandbox ↔ Toolkit | 1↔N possible, 1↔1 in practice | `benchmarks/<slug>/toolkit.py` |
| Toolkit ↔ Worker class | N↔M (loose) | Worker class in `workers/baselines/`, binding in `benchmarks/<slug>/workers.py` |
| Worker class ↔ Benchmark | N↔1 (one ReActWorker, N benchmarks) | Worker class in `workers/baselines/` |
| Evaluator ↔ Benchmark | 1↔1 (rubric); N↔M (reusable criteria) | Rubric in `benchmarks/<slug>/rubric.py`; benchmark-specific criteria in `benchmarks/<slug>/criteria/`; reusable criteria in top-level `evaluators/criteria/` |
| Evaluator ↔ Sandbox | 1↔1 if agentic, 0 otherwise | Same as Evaluator ↔ Benchmark |
| Experiment factory ↔ Benchmark | 1↔N (one factory per strategy ablation) | `benchmarks/<slug>/experiment.py` |
| Experiment registry ↔ Benchmarks | 1↔N (one dict over all builtins) | `ergon_builtins/benchmarks/_registry.py` (added in PR 8) |
| CLI composition helper ↔ Experiment registry | 1↔1 | `ergon_cli/composition/` (lives in CLI package) |

The test for "where does X live?":

- 1:1 with a benchmark → `benchmarks/<slug>/`
- N:1 across benchmarks → top-level under its category

`Sandbox` and `Toolkit` fail the test for cross-cutting (every concrete
class is 1:1 with a benchmark); they move down.  `ReActWorker` passes
(one class powers every benchmark); it stays up.  The shared
manager-backed sandbox adapter passes (one adapter wraps every
benchmark's `BaseSandboxManager` subclass until PR 11); it gets its own
top-level home in `sandbox/`.

## Composition Layer

The composition layer — where worker strategy, benchmark, sandbox, and
evaluator are wired into a runnable `Experiment` — lives in three
places, each at its correct cardinality level:

```
ergon_builtins/benchmarks/<slug>/
├── workers.py        ← per-benchmark factories: react_worker(),
│                       cot_worker(), reflexion_worker(), …
│                       Each binds a Worker class from
│                       workers/baselines/ to this benchmark's
│                       sandbox + toolkit + prompt.
│
└── experiment.py     ← per-benchmark Experiment factories:
                        make_react_experiment(args) -> Experiment,
                        make_cot_experiment(args) -> Experiment, …
                        Each picks ONE worker factory from workers.py,
                        constructs the Benchmark instance, attaches
                        evaluators, returns an Experiment.

ergon_builtins/benchmarks/_registry.py   (added in PR 8)
                        BUILTIN_EXPERIMENT_FACTORIES: dict[str, Callable]
                        Maps CLI slug → experiment factory.

ergon_cli/composition/
                        build_experiment(args) — argparse Namespace
                        in, Experiment out.  Looks up slug in
                        BUILTIN_EXPERIMENT_FACTORIES and dispatches.
```

The split is: **what** to compose lives per-benchmark (factories knowing
about the local sandbox/toolkit/prompt); **how to discover** it lives
at the `_registry.py` level; **how to drive it from a CLI** lives in
the CLI package.  Each layer is at its correct cardinality and only
imports downward.

### Making the swap point real: parameterised Benchmark

The above layering only works if `Benchmark.build_instances()` does
*not* hardcode a specific worker factory.  PR 6 today writes:

```python
# benchmark.py — current
yield Task(..., worker=make_minif2f_worker(), sandbox=LeanSandbox(), ...)
```

— which means swapping ReAct → CoT requires editing `benchmark.py`.
That makes `experiment.py` cosmetic.  To make it the real swap point,
PR 6.5 parameterises the benchmark:

```python
# benchmark.py — post-PR-6.5
class MiniF2FBenchmark(Benchmark):
    def __init__(
        self,
        *,
        worker_factory: Callable[[], Worker] = make_minif2f_worker,
        sandbox_factory: Callable[[], Sandbox] = LeanSandbox,
        ...,
    ) -> None: ...

    def build_instances(self):
        yield Task(
            ...,
            worker=self._worker_factory(),
            sandbox=self._sandbox_factory(),
            ...,
        )
```

Then `experiment.py` is genuinely where strategy is chosen:

```python
def make_react_experiment(args):
    return Experiment(benchmark=MiniF2FBenchmark(worker_factory=make_minif2f_react), ...)

def make_cot_experiment(args):
    return Experiment(benchmark=MiniF2FBenchmark(worker_factory=make_minif2f_cot), ...)
```

The benchmark module still imports its sandbox (the default value),
which is honest: the sandbox is part of the per-benchmark domain
bundle.  The worker, in contrast, is now genuinely swappable from the
outside.

**This PR does not implement the composition layer.** PR 8 owns the
`_registry.py` + `ergon_cli/composition/` wiring.  What PR 6.5 does is:

1. Move per-benchmark files into `benchmarks/<slug>/` (Tasks 1–3).
2. Create `benchmarks/<slug>/experiment.py` with a stub factory so
   the location is locked in before PR 8 lands (Task 4).
3. **Parameterise `MiniF2FBenchmark.__init__`** to accept
   `worker_factory` / `sandbox_factory` callables (Task 5), so the
   strategy swap is honest and `experiment.py`'s eventual body is
   trivial.
4. Update PR 8's plan (Task 10) to reflect the new file paths and
   the parameterised-benchmark constructor.

## Task 1: Move MiniF2F Sandbox

**Files:**

- Move: `ergon_builtins/sandboxes/lean.py` → `ergon_builtins/benchmarks/minif2f/sandbox.py`

- [ ] **Step 1: `git mv` the file**

  ```bash
  git mv ergon_builtins/ergon_builtins/sandboxes/lean.py \
         ergon_builtins/ergon_builtins/benchmarks/minif2f/sandbox.py
  ```

- [ ] **Step 2: Update module docstring**

  Replace "object-bound Lean 4 sandbox for MiniF2F" introduction with a
  shorter version that reflects the new colocation; drop the "PR 10
  extracts `_ManagerBackedSandboxRuntime` into
  `ergon_builtins/sandboxes/_manager_backed.py`" line and replace with
  "PR 10a extracts the shared adapter to `ergon_builtins/sandbox/_manager_backed.py`".

- [ ] **Step 3: Verify no remaining `sandboxes/lean` references**

  ```bash
  rg "from ergon_builtins.sandboxes" ergon_builtins/ ergon_core/
  rg "ergon_builtins\.sandboxes" ergon_builtins/ ergon_core/
  ```

## Task 2: Move MiniF2F Toolkit + Tools

**Files:**

- Move: `ergon_builtins/toolkits/minif2f.py` → `ergon_builtins/benchmarks/minif2f/toolkit.py`
- Move: `ergon_builtins/toolkits/_minif2f_tools.py` → `ergon_builtins/benchmarks/minif2f/_tools.py`

- [ ] **Step 1: `git mv` both files**

- [ ] **Step 2: Update internal imports**

  - `toolkit.py` line 43 (`from ergon_builtins.toolkits._minif2f_tools import build_tools`)
    → `from ergon_builtins.benchmarks.minif2f._tools import build_tools`
  - `_tools.py` line 22 (`from ergon_builtins.benchmarks.minif2f.constants import ...`) — already correct, no change needed
  - `_tools.py` line 25 (`from ergon_builtins.toolkits.minif2f import MiniF2FToolkit` under TYPE_CHECKING)
    → `from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit`

- [ ] **Step 3: Re-check the circular-import cycle**

  The PR 6 cycle was:
  `toolkits/minif2f.py → toolkits/_minif2f_tools.py → benchmarks.minif2f.constants → benchmarks/minif2f/__init__.py → benchmark.py → worker_factory.py → toolkits/minif2f.py`

  Post-move:
  `benchmarks/minif2f/toolkit.py → benchmarks/minif2f/_tools.py → benchmarks/minif2f/constants.py → benchmarks/minif2f/__init__.py → benchmark.py → workers.py → benchmarks/minif2f/toolkit.py`

  Still a cycle.  The lazy import inside `MiniF2FToolkit.tools()` is
  still required; keep the `# reason:` comment but update the path
  description.

## Task 3: Rename `worker_factory.py` → `workers.py` AND Split Out Legacy

**Files:**

- Rename: `ergon_builtins/benchmarks/minif2f/worker_factory.py` → `ergon_builtins/benchmarks/minif2f/workers.py`
- Create: `ergon_builtins/benchmarks/minif2f/_legacy_workers.py`

**Rationale:** PR 6's `worker_factory.py` mixed v2 factories
(`make_minif2f_worker`, `make_minif2f_rubric`) with the legacy
`MiniF2FReactWorker` class + `_minif2f_run_skill` (kept alive for the
registry-string bridge until PR 11).  This task separates the two so
PR 11's deletion is a single-file `rm`, not a multi-block surgery.

- [ ] **Step 1: `git mv` worker_factory.py → workers.py**

- [ ] **Step 2: Move the legacy block to `_legacy_workers.py`**

  Cut from `workers.py` and paste into `_legacy_workers.py`:
  - `_minif2f_run_skill()` function
  - `MiniF2FReactWorker` class
  - Imports of `MiniF2FSandboxManager` and `_LegacyMiniF2FToolkit`

  Leave `workers.py` with only the v2 factories
  (`make_minif2f_worker`, `make_minif2f_rubric`).

- [ ] **Step 3: Add a clear deletion marker to `_legacy_workers.py`**

  Top-of-file docstring:

  ```python
  """Legacy MiniF2F worker bridge — DELETED IN PR 11.

  This file exists solely so the `"minif2f-react"` registry slug
  still resolves for experiments persisted before PR 6.  Once PR 11
  retires the legacy registry fallback chain, delete this entire
  file along with `sandbox_manager.py`.

  Do NOT import from this file in new code.  v2 callers use
  `workers.make_minif2f_worker()`.
  """
  ```

- [ ] **Step 4: Update registry imports**

  Find every reference to `MiniF2FReactWorker` in
  `ergon_builtins/registry_core.py` / `ergon_builtins/registry.py`:

  ```bash
  rg "MiniF2FReactWorker" ergon_builtins/
  ```

  Update the import path:
  `from ergon_builtins.benchmarks.minif2f.worker_factory import MiniF2FReactWorker`
  → `from ergon_builtins.benchmarks.minif2f._legacy_workers import MiniF2FReactWorker`

- [ ] **Step 5: Update imports in `benchmark.py`**

  `from ergon_builtins.benchmarks.minif2f.worker_factory import (...)`
  → `from ergon_builtins.benchmarks.minif2f.workers import (...)`

- [ ] **Step 6: Update `workers.py` docstring**

  ```python
  """MiniF2F worker factories — one per agentic strategy.

  Each factory bundles the MiniF2F sandbox, toolkit, and system
  prompt with a chosen worker class (ReActWorker today; CoTWorker /
  ReflexionWorker future).  Strategies vary independently; the
  domain bundle is constant.

  Legacy registry bridge (MiniF2FReactWorker) lives in
  `_legacy_workers.py` and is deleted in PR 11.
  """
  ```

- [ ] **Step 7: Sanity-check no stragglers**

  ```bash
  rg "minif2f\.worker_factory" ergon_builtins/ ergon_core/ ergon_cli/
  ```

  Expect zero hits.

## Task 4: Parameterise `MiniF2FBenchmark` For Strategy A/B

**Files:**

- Modify: `ergon_builtins/benchmarks/minif2f/benchmark.py`

**Rationale:** PR 6 hardcodes `make_minif2f_worker()` and
`LeanSandbox()` inside `build_instances()`.  That makes the
`experiment.py` swap point fictional — swapping worker strategy
today requires editing `benchmark.py`.  This task parameterises
the benchmark constructor so the swap point becomes real and the
composition layering described above holds.

- [ ] **Step 1: Add factory kwargs to `__init__`**

  ```python
  from collections.abc import Callable

  from ergon_core.api.sandbox import Sandbox
  from ergon_core.api.worker import Worker

  from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
  from ergon_builtins.benchmarks.minif2f.workers import (
      make_minif2f_rubric,
      make_minif2f_worker,
  )


  class MiniF2FBenchmark(Benchmark):
      def __init__(
          self,
          *,
          # Existing kwargs (name, description, metadata, limit, ...) stay.
          worker_factory: Callable[[], Worker] = make_minif2f_worker,
          sandbox_factory: Callable[[], Sandbox] = LeanSandbox,
          evaluator_factory: Callable[[], "MiniF2FRubric"] = make_minif2f_rubric,
          ...,
      ) -> None:
          super().__init__(...)
          self._worker_factory = worker_factory
          self._sandbox_factory = sandbox_factory
          self._evaluator_factory = evaluator_factory
          ...
  ```

- [ ] **Step 2: Use the factories inside `build_instances`**

  ```python
  def build_instances(self) -> Mapping[str, Sequence[Task[MiniF2FTaskPayload]]]:
      tasks = []
      for problem in self._load_problems():
          ...
          tasks.append(
              Task[MiniF2FTaskPayload](
                  ...,
                  worker=self._worker_factory(),
                  sandbox=self._sandbox_factory(),
                  evaluators=(self._evaluator_factory(),),
              )
          )
      return {"default": tasks}
  ```

- [ ] **Step 3: Keep behaviour identical for callers that don't pass factories**

  The defaults (`make_minif2f_worker`, `LeanSandbox`, `make_minif2f_rubric`)
  reproduce PR 6's behaviour exactly.  All existing tests must
  continue to pass — confirm by running
  `uv run pytest ergon_builtins/tests/unit -q` after this task.

- [ ] **Step 4: Add a one-line test that the factories swap**

  Append to `ergon_builtins/tests/unit/benchmarks/test_minif2f_task_shape.py`:

  ```python
  def test_minif2f_benchmark_accepts_custom_worker_factory() -> None:
      """The benchmark uses the worker_factory passed to its constructor."""
      from unittest.mock import MagicMock

      from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
      from ergon_builtins.benchmarks.minif2f.workers import make_minif2f_worker

      sentinel_worker = make_minif2f_worker()
      sentinel_worker.name = "sentinel"
      factory = MagicMock(return_value=sentinel_worker)

      benchmark = MiniF2FBenchmark(worker_factory=factory, limit=1)
      tasks = list(benchmark.build_instances().values())[0]

      assert tasks[0].worker is sentinel_worker
      factory.assert_called_once()
  ```

  This is the load-bearing assertion: factories are *called*, not
  the class attribute that defaults to them.  Without this test, a
  future refactor could accidentally revert to hardcoding the
  default and the test suite would still pass.

- [ ] **Step 5: Update `worker_factory` defaults to be a real swap point**

  Sanity-check that calling `MiniF2FBenchmark(worker_factory=lambda: <other_worker>)` produces tasks bound to the new worker, not the default.  This is covered by Step 4's test; just verify the assertion is meaningful.

## Task 5: Update `benchmarks/minif2f/__init__.py`

**Files:**

- Modify: `ergon_builtins/benchmarks/minif2f/__init__.py`

- [ ] **Step 1: Reconsider the eager-export comment**

  The PR 6 comment explains why `MiniF2FBenchmark` cannot be eagerly
  re-exported (cycle through `sandboxes/lean.py → MiniF2FSandboxManager`).
  Post-move, the cycle is:
  `benchmarks/minif2f/__init__.py → benchmark.py → sandbox.py → sandbox_manager.py → __init__.py`

  Still a cycle (sandbox.py still imports MiniF2FSandboxManager until
  PR 11).  Keep the non-re-export, update the comment to describe the
  new (shorter) cycle path, and keep the existing
  `TODO(PR 11)` marker.

## Task 6: Add `sandbox/` Top-Level Dir Stub

**Files:**

- Create: `ergon_builtins/ergon_builtins/sandbox/__init__.py`

- [ ] **Step 1: Empty package init**

  Just a docstring explaining the dir's purpose:

  ```python
  """Cross-cutting sandbox infrastructure shared across benchmarks.

  Files in this package implement adapters / utilities that more than
  one benchmark's `Sandbox` subclass relies on.  Per-benchmark code
  (`LeanSandbox`, `SWEBenchSandbox`, etc.) lives in
  `ergon_builtins/benchmarks/<slug>/sandbox.py`, NOT here.

  Naming: singular `sandbox/` (this package, cross-cutting infra)
  vs.  per-benchmark `benchmarks/<slug>/sandbox.py` (single concrete
  Sandbox subclass).  The deleted `sandboxes/` (plural) directory
  conflated the two and is gone.

  PR 10a populates this with `_manager_backed.py` (the shared
  BaseSandboxManager → SandboxRuntime adapter).
  """
  ```

- [ ] **Step 2: Add to test_public_api_boundaries allowlist if needed**

  Check whether any architecture test enforces a closed set of top-level
  `ergon_builtins/` packages; if so, add `sandbox` to the allowlist
  (and remove `sandboxes` / `toolkits` if present).

  ```bash
  rg "ergon_builtins.*(sandbox|workers|sandboxes|toolkits)" ergon_core/tests/unit/architecture/
  ```

## Task 7: Update Suppression Budget Comment

**Files:**

- Modify: `scripts/check_suppression_budget.py`

- [ ] **Step 1: Update path references in the comment**

  Change `_minif2f_tools.py build_tools` → `benchmarks/minif2f/_tools.py build_tools` etc.  No count change; this is documentation drift.

## Task 8: Update Architecture Docs

**Files:**

- Modify: `docs/architecture/06_builtins.md`
- Modify: `docs/architecture/01_public_api.md`

- [ ] **Step 1: Update the code map in `06_builtins.md`**

  Replace:

  ```
  | v2 object-bound Sandbox subclasses | `ergon_builtins/sandboxes/` |
  | v2 serializable Toolkit configs | `ergon_builtins/toolkits/` |
  ```

  With:

  ```
  | Per-benchmark Sandbox subclass | `ergon_builtins/benchmarks/<slug>/sandbox.py` |
  | Per-benchmark Toolkit config | `ergon_builtins/benchmarks/<slug>/toolkit.py` |
  | Per-benchmark worker factories | `ergon_builtins/benchmarks/<slug>/workers.py` |
  | Per-benchmark experiment factories | `ergon_builtins/benchmarks/<slug>/experiment.py` |
  | Per-benchmark legacy (PR 11 deletes) | `ergon_builtins/benchmarks/<slug>/_legacy_workers.py` |
  | Cross-cutting sandbox-adapter infra | `ergon_builtins/sandbox/` |
  ```

- [ ] **Step 2: Add a "Cardinality and colocation" section**

  Insert the cardinality matrix (from "Why This Layout" above) plus
  the "1:1 → `benchmarks/<slug>/`; N:1 → top-level" test.

  **`06_builtins.md` is the canonical home for this matrix.**  Do
  not duplicate it in the RFC docs (`00-readme.md`,
  `01-api-surface.md`); those describe authoring intent, not the
  internal builtins layout.  Cross-references are fine; copies are
  not (they drift).

- [ ] **Step 3: Add an anti-pattern**

  Append to `06_builtins.md` § 6:

  > **Per-benchmark code under top-level `sandboxes/` or `toolkits/`.**
  > A `LeanSandbox` is only useful inside MiniF2F; a `MiniF2FToolkit`
  > assumes `LeanSandbox`.  These belong in `benchmarks/minif2f/`,
  > not in cross-cutting top-level dirs that imply reuse that doesn't
  > exist.  The cardinality test: a file is cross-cutting only if N
  > different benchmarks would import it.

- [ ] **Step 4: Add an anti-pattern (worker side)**

  > **`<Benchmark>ReActWorker(ReActWorker)` subclasses.**  Making
  > per-benchmark worker subclasses costs N×M classes (N strategies ×
  > M benchmarks) and forces the agentic-loop logic to live in N
  > subclasses that all `super().execute()`.  The v2 pattern is: one
  > worker class per strategy in `workers/baselines/`, plus a
  > per-benchmark factory function in `benchmarks/<slug>/workers.py`
  > that binds the strategy to the local sandbox + toolkit + prompt.
  > Cost is N + M, not N × M.

- [ ] **Step 5: Update `01_public_api.md`**

  Find the "add a new benchmark" extension point (added in PR 6) and
  replace the file paths.  Drop the references to
  `ergon_builtins/sandboxes/` and `ergon_builtins/toolkits/`; replace
  with `ergon_builtins/benchmarks/<slug>/sandbox.py` and `.../toolkit.py`.

## Task 9: Update v2 RFC Framing

**Files:**

- Modify: `docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/00-readme.md`
- Modify: `docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/01-api-surface.md`

- [ ] **Step 1: Rewrite the "composability" framing in `00-readme.md`**

  Wherever the RFC claims the v2 design lets you compose any
  `Sandbox`/`Toolkit`/`Worker` freely, replace with:

  > **Domain colocation + orthogonal worker strategies.** A benchmark
  > ships with a coupled triple: its `Sandbox` (runtime container),
  > `Toolkit` (LLM-facing tools that assume that container), and
  > system prompt.  These are co-designed; they are not portable across
  > benchmarks.  The orthogonal axis is the worker *class*: the same
  > `ReActWorker` (or `CoTWorker`, `ReflexionWorker`) is reused for
  > every benchmark, parameterised by the per-benchmark triple via a
  > factory function.  This is what the architecture buys:
  > - one place for agentic-loop logic (per worker class),
  > - one place for per-benchmark wiring (per benchmark subpackage),
  > - serialisable config so tasks round-trip through the
  >   orchestrator → eval-worker process boundary.
  >
  > What the design does *not* buy: the ability to use `MiniF2FToolkit`
  > inside a `SWEBenchSandbox` or vice versa.  Toolkit / sandbox /
  > prompt are domain-coupled.

- [ ] **Step 2: Update `01-api-surface.md`**

  Find any references to `Toolkit` portability or "compose any
  worker with any toolkit" and rewrite to match Step 1's framing.

  **Do NOT duplicate the cardinality matrix here.**  It lives in
  `docs/architecture/06_builtins.md` (Task 7 Step 2) as the
  single source of truth.  If `01-api-surface.md` needs to reference
  the cardinality story, link to `06_builtins.md` rather than
  pasting the table.

## Task 10: Update Later PR Plans (Contradiction Sweep)

**Files:**

- Modify: `09-implementation-plan/09-pr-08-cli-composition.md`
- Modify: `09-implementation-plan/11-pr-10a-swebench.md`
- Modify: `09-implementation-plan/11b-pr-10b-researchrubrics.md`
- Modify: `09-implementation-plan/11c-pr-10c-gdpeval.md`
- Modify: `09-implementation-plan/12-pr-11-deletion-final-schema.md`
- Modify: `09-implementation-plan/00-program.md`

The later PR plans were written assuming PR 6's `sandboxes/<slug>.py` /
`toolkits/<slug>.py` layout.  Each one's `Files → Create:` section,
plus any embedded `import` lines in code blocks, must be updated to
the post-PR-6.5 paths.

**Method: do a thorough scan of each file before editing.**  For each
PR plan, before making changes, run:

```bash
rg "sandboxes/" docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/<file>
rg "toolkits/"  docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/<file>
rg "worker_factory" docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/<file>
rg "ergon_builtins\.sandboxes\|ergon_builtins\.toolkits" docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/09-implementation-plan/<file>
```

Treat every hit as a candidate edit; update or remove as appropriate.
Do not assume the bullet points below are exhaustive — the sweep is.

- [ ] **Step 1: PR 8 (CLI composition) path + parameterisation updates**

  In `09-pr-08-cli-composition.md`:
  - The plan adds `ergon_builtins/ergon_builtins/benchmarks/_registry.py`.
    Confirm it imports `MiniF2FBenchmark` directly from
    `benchmarks/minif2f/benchmark.py`, not through any top-level
    re-export.
  - Any factory functions referenced in example code blocks should use
    `benchmarks/minif2f/experiment.py::make_react_experiment` (PR 6.5
    Task 4 creates this file with one factory; PR 8 may add more).
  - Drop any references to `worker_factory` (it no longer exists).
  - **Update PR 8's example code to use the parameterised benchmark
    constructor** (PR 6.5 Task 5):

    ```python
    # PR 8 example: experiment factory
    def make_react_experiment(args):
        benchmark = MiniF2FBenchmark(
            worker_factory=make_minif2f_worker,
            limit=args.limit,
        )
        return Experiment(benchmark=benchmark, ...)

    def make_cot_experiment(args):
        benchmark = MiniF2FBenchmark(
            worker_factory=make_minif2f_cot_worker,  # different strategy
            limit=args.limit,
        )
        return Experiment(benchmark=benchmark, ...)
    ```

    If PR 8's current draft has experiment factories hardcoding
    `MiniF2FBenchmark()` and then ignoring the worker (because the
    benchmark builds tasks with `make_minif2f_worker()` baked in),
    that's now a contradiction — update it.

- [ ] **Step 2: PR 10a (SWEBench) path updates**

  In `11-pr-10a-swebench.md`:
  - `ergon_builtins/sandboxes/swebench.py` → `ergon_builtins/benchmarks/swebench_verified/sandbox.py`
  - `ergon_builtins/sandboxes/_manager_backed.py` → `ergon_builtins/sandbox/_manager_backed.py`
  - `ergon_builtins/toolkits/swebench.py` → `ergon_builtins/benchmarks/swebench_verified/toolkit.py`
  - `ergon_builtins/toolkits/_swebench_tools.py` (if planned) → `ergon_builtins/benchmarks/swebench_verified/_tools.py`
  - `swebench_verified/worker_factory.py` → `swebench_verified/workers.py`
  - Mirror PR 6.5's `_legacy_workers.py` split if the SWEBench plan
    keeps a legacy worker class during the bridge.
  - All imports inside example code blocks: rewrite to match.

- [ ] **Step 3: PR 10b (ResearchRubrics) path updates**

  Same pattern for `11b-pr-10b-researchrubrics.md`:
  - `sandboxes/researchrubrics.py` → `benchmarks/researchrubrics/sandbox.py`
  - `toolkits/researchrubrics.py` → `benchmarks/researchrubrics/toolkit.py`
  - Imports inside `from ergon_builtins.sandboxes._manager_backed import …`
    → `from ergon_builtins.sandbox._manager_backed import …`
  - Plus the workers / _legacy_workers split if relevant.

- [ ] **Step 4: PR 10c (GDPEval) path updates**

  Same pattern for `11c-pr-10c-gdpeval.md`:
  - `sandboxes/gdpeval.py` → `benchmarks/gdpeval/sandbox.py`
  - `toolkits/gdpeval.py` → `benchmarks/gdpeval/toolkit.py`
  - Same import / workers / _legacy_workers updates as above.

- [ ] **Step 5: PR 11 (deletion) — thorough scan**

  PR 11 is the most likely to contain stale path assumptions because
  it lists files to delete and symbols to remove.  Treat this as the
  most important sweep target.

  In `12-pr-11-deletion-final-schema.md`:

  a. **Files To Delete** list:
     - Confirm `benchmarks/<slug>/sandbox_manager.py` paths are
       present and correct (per-benchmark managers).
     - REMOVE any entry that lists `ergon_builtins/sandboxes/` or
       `ergon_builtins/toolkits/` as a deletion target — those dirs
       were already deleted by PR 6.5.
     - REMOVE any entry that lists
       `ergon_builtins/sandbox/_manager_backed.py` as a deletion
       target (the adapter stays; only its internals change to call
       E2B directly).  If PR 11's plan currently says to delete the
       adapter, it's a contradiction — flag for resolution.
     - If PR 11 deletes `MiniF2FReactWorker`, the path is now
       `benchmarks/minif2f/_legacy_workers.py` (whole file goes),
       not `benchmarks/minif2f/worker_factory.py`.  Same for
       SWEBench's `SWEBenchReactWorker` (or whatever it's called)
       if it gets a `_legacy_workers.py` in PR 10a.

  b. **Symbol deletion table** (if any):
     - `_minif2f_run_skill` moves from `worker_factory.py` to
       `_legacy_workers.py`; the deletion target updates.

  c. **PR 11 sandbox-rewrite plan**:
     - `LeanSandbox.provision()` and `_bind_runtime()` are rewritten
       to call E2B directly (drop `MiniF2FSandboxManager` calls).
       Confirm PR 11's plan reflects this.  If it currently says
       "delete `LeanSandbox`", that's wrong — `LeanSandbox` stays,
       only its body changes.

  d. **Imports in PR 11's example code blocks**:
     - Any `from ergon_builtins.sandboxes…` → `from ergon_builtins.benchmarks.<slug>.sandbox…`
     - Any `from ergon_builtins.toolkits…` → `from ergon_builtins.benchmarks.<slug>.toolkit…`

- [ ] **Step 6: 00-program.md bridge table + ledger updates**

  - Bridge row "Sandbox subclasses beside BaseSandboxManager" doesn't
    reference paths.  No path change needed.
  - Add a short note in the "Per-PR ledger updates" section calling
    out PR 6.5's file moves so the v2 transition ledger test
    (`test_v2_transition_ledger.py`) doesn't get surprised when
    `sandboxes/` disappears.
  - Add PR 6.5 to the program timeline / ordering diagram if one
    exists.

## Task 11: Update PR 6 Inline TODO Markers

**Files:**

- Modify: `ergon_builtins/benchmarks/minif2f/sandbox.py` (post-move)
- Modify: `ergon_builtins/benchmarks/minif2f/toolkit.py` (post-move)
- Modify: `ergon_builtins/workers/baselines/react_worker.py`

- [ ] **Step 1: Update path references in `TODO(PR 10a/11)` comments**

  The TODOs in PR 6's output reference paths like
  `ergon_builtins/sandboxes/_manager_backed.py` (for PR 10a).  Update
  to `ergon_builtins/sandbox/_manager_backed.py` (singular).

  Specifically the docstring of `LeanSandbox` (now at
  `benchmarks/minif2f/sandbox.py`) and the `TODO(PR 10a)` comment
  above `_ManagerBackedSandboxRuntime`.

## Task 12: Update Test File Imports

**Files:**

- Modify: `ergon_builtins/tests/unit/benchmarks/test_minif2f_task_shape.py`
- Modify: `ergon_core/tests/unit/runtime/test_experiment_definition_writer.py`
- Modify: `ergon_core/tests/unit/runtime/test_experiment_definition_service.py`

- [ ] **Step 1: Rewrite imports**

  - `from ergon_builtins.sandboxes.lean import LeanSandbox`
    → `from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox`
  - `from ergon_builtins.toolkits.minif2f import MiniF2FToolkit`
    → `from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit`
  - `from ergon_builtins.benchmarks.minif2f.worker_factory import (make_minif2f_rubric, make_minif2f_worker)`
    → `from ergon_builtins.benchmarks.minif2f.workers import (make_minif2f_rubric, make_minif2f_worker)`

- [ ] **Step 2: Run focused tests**

  ```bash
  uv run pytest ergon_builtins/tests/unit ergon_core/tests/unit/runtime/test_experiment_definition_service.py ergon_core/tests/unit/runtime/test_experiment_definition_writer.py -q
  ```

  Expect: all previously-passing tests still pass.

## Task 13: Update ReActWorker Import

**Files:**

- Modify: `ergon_builtins/workers/baselines/react_worker.py`

- [ ] **Step 1: Rewrite the import**

  `from ergon_builtins.toolkits.minif2f import MiniF2FToolkit`
  → `from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit`

  Note: this import is the entry point to the dependency that PR 11
  replaces with a `Toolkit` protocol (see existing TODO comment on the
  `toolkit:` field).  The import path change is mechanical; the TODO
  stays.

## Task 14: Phase 1 Check Suite

Phase 1 (file moves + parameterised benchmark) is now complete.  Verify before committing.

- [ ] **Step 1: Run lint + format + type-check + slopcop**

  ```bash
  pnpm run check:be
  ```

  All checks must pass.

- [ ] **Step 2: Run fast test suite**

  ```bash
  pnpm run test:be:fast
  ```

  Expect: same pass count as before PR 6.5 Phase 1 (no behaviour change yet — `Experiment` class still alive).

- [ ] **Step 3: Search for stragglers**

  ```bash
  rg "ergon_builtins\.sandboxes" .
  rg "ergon_builtins\.toolkits" .
  rg "minif2f\.worker_factory" .
  ```

  Any hit outside of `docs/rfcs/accepted/` (historical) is a bug.

## Task 15: Phase 1 Commit

```bash
git add -A
git commit -m "PR 6.5 (1/2): domain colocation in ergon_builtins

- Move per-benchmark sandbox/toolkit/tools into benchmarks/minif2f/
- Rename worker_factory.py → workers.py; split legacy into _legacy_workers.py
- Parameterise MiniF2FBenchmark(worker_factory=..., sandbox_factory=...)
- Add top-level sandbox/ stub for PR 10a's shared adapter
- Update architecture docs, v2 RFC framing, suppression budget
- No behaviour change; all tests still pass"
```

Phase 2 begins below.  Do NOT mix Phase 2 changes into this commit.

---

## Task 16: (Phase 2 starts) Hard-Delete `Experiment` Class

**Files:**

- Delete: `ergon_core/ergon_core/api/experiment.py`
- Modify: `ergon_core/ergon_core/api/__init__.py` (drop `Experiment` export)

- [ ] **Step 1: Inventory `Experiment` callsites**

  ```bash
  rg "from ergon_core\.api.* import .*Experiment\b" .
  rg "Experiment\(" --type py
  rg "Experiment\b" ergon_core/ ergon_cli/ ergon_builtins/ tests/ | grep -v _test_data | wc -l
  ```

  Expect ~20-30 hits across tests + the application services + CLI handlers.  Note where each comes from; each one needs an edit in subsequent tasks.

- [ ] **Step 2: Delete the class file**

  ```bash
  rm ergon_core/ergon_core/api/experiment.py
  ```

- [ ] **Step 3: Drop the export**

  Edit `ergon_core/ergon_core/api/__init__.py`:
  - Remove `from ergon_core.api.experiment import Experiment`
  - Remove `"Experiment"` from `__all__`
  - Add `from ergon_core.api.persistence import persist_benchmark` (Task 17 creates this)

  Project will not import-clean until Task 17 lands.  Acceptable — these two tasks must land in the same commit.

## Task 17: Rename `persist_definition` → `persist_benchmark` (Signature Change)

**Files:**

- Modify: `ergon_core/ergon_core/api/persistence.py` (or wherever the existing `persist_definition` lives — find via `rg "def persist_definition"`)
- Modify: every callsite found in `rg "persist_definition\("`

- [ ] **Step 1: Locate the current function**

  ```bash
  rg "def persist_definition" --type py
  ```

  Likely `ergon_core/ergon_core/core/application/experiments/definition_writer.py`.

- [ ] **Step 2: Rename + change signature**

  Old:
  ```python
  def persist_definition(experiment: Experiment) -> DefinitionHandle:
      ...
  ```

  New:
  ```python
  def persist_benchmark(
      benchmark: Benchmark,
      *,
      name: str,
      experiment: str | None = None,
      metadata: dict[str, Any] | None = None,
  ) -> DefinitionHandle:
      """Persist a configured Benchmark as a definition row.

      ``experiment`` is an optional string tag grouping related
      definitions (e.g. an ablation study).  It is NOT a class — see
      docs/superpowers/brainstorms/2026-05-15-kill-experiment-class.md
      for the rationale.
      """
      ...
  ```

  Body: pull `benchmark`, `name`, `metadata` directly from kwargs (no `experiment.benchmark` / `experiment.name` indirection).  Write the new `experiment: str | None` column on the persisted row (Task 18 adds the column).

- [ ] **Step 3: Update every callsite**

  Old shape (`define_benchmark_experiment` / direct `persist_definition(experiment)`):
  ```python
  experiment = Experiment(benchmark=b, name="foo", metadata={...})
  handle = persist_definition(experiment)
  ```

  New shape:
  ```python
  handle = persist_benchmark(b, name="foo", metadata={...})
  ```

  Callsites to update (non-exhaustive, use `rg` to find all):
  - `ergon_core/ergon_core/core/application/experiments/service.py::define_benchmark_experiment` — delete; replace with direct `persist_benchmark` calls at the new CLI / handler boundary (most are removed in Task 21).
  - Any integration test that round-trips through persist + load.
  - Any fixture in `ergon_core/tests/conftest.py` or `ergon_builtins/tests/conftest.py`.

- [ ] **Step 4: Confirm no stragglers**

  ```bash
  rg "persist_definition\b" .
  rg "Experiment\(" .
  ```

  Expect zero hits in production code.  Test fixtures that still reference these are tracked in Task 21 for cleanup.

## Task 18: Rename `ExperimentRecord` SQLModel + Physical Table

**Files:**

- Modify: `ergon_core/ergon_core/core/persistence/telemetry/models.py`
- Modify: every repository / query that names `ExperimentRecord`

- [ ] **Step 1: Rename the SQLModel class AND the physical table**

  In `models.py`:

  ```python
  class BenchmarkDefinitionRecord(SQLModel, table=True):
      __tablename__ = "benchmark_definitions"   # was "experiments"
      ...
      experiment: str | None = Field(default=None, index=True)  # NEW
  ```

  Both the Python class name and the physical table name change.  There's no production data to preserve and the Alembic chain is being dropped/regenerated wholesale (see PR 11), so no migration dance is required.

- [ ] **Step 2: Add an explicit ledger entry**

  In the `BenchmarkDefinitionRecord` class docstring:

  ```python
  """Persisted definition row for one configured Benchmark.

  Renamed from ``ExperimentRecord`` in PR 6.5 Phase 2 (kill-Experiment
  refactor).  Table also renamed: ``experiments`` → ``benchmark_definitions``.
  The ``experiment: str | None`` column is the user-facing grouping tag
  (e.g. ``experiment="strategy-ablation-2026-05-14"``) — it is a label, not
  a foreign key.
  """
  ```

- [ ] **Step 3: Update all reads**

  ```bash
  rg "ExperimentRecord\b" .
  ```

  Every hit gets rewritten to `BenchmarkDefinitionRecord`.  Likely files:
  - Every `*_repository.py` and `*_repositories.py` in `ergon_core/core/persistence/`
  - `ergon_core/core/application/experiments/` query helpers
  - Inngest function payload classes that reference the table indirectly
  - The dashboard's generated contract schemas (regenerated via `pnpm run generate:contracts` — separate Task 21)

## Task 19: Delete CLI Authoring Commands

**Files:**

- Delete: `ergon_cli/ergon_cli/commands/experiment.py::handle_experiment_define`
- Delete: `ergon_cli/ergon_cli/commands/experiment.py::handle_experiment_run`
- Delete: argparse subparsers for `experiment define` / `experiment run`
- Delete: `ergon_cli/tests/unit/cli/test_experiment_cli.py` (or the affected test cases)

- [ ] **Step 1: Locate the CLI surface**

  ```bash
  rg "experiment.define\|experiment.run\|handle_experiment_define\|handle_experiment_run" ergon_cli/
  ```

- [ ] **Step 2: Delete the handlers + argparse plumbing**

  Remove the subparser registrations from wherever the argparse tree is built (likely `ergon_cli/__main__.py` or `ergon_cli/cli.py`).  The `experiment` top-level command may continue to exist for the lifecycle subcommands `show` / `list` added in PR 8 — for now, drop just the `define` and `run` subcommands.

- [ ] **Step 3: Delete the corresponding tests**

  ```bash
  rg "handle_experiment_define\|handle_experiment_run" ergon_cli/tests/
  ```

  Remove every test case referencing these.  Run `uv run pytest ergon_cli/tests/unit -q` to confirm the CLI tests still pass (other commands unaffected).

- [ ] **Step 4: Document the hard break**

  Add an entry to the repo CHANGELOG (or wherever user-facing breaking changes go) noting that `ergon experiment define` / `ergon experiment run` are gone.  Direct users to the Python API (`persist_benchmark` + `launch_run`).  See the example `kick_off.py` script in `docs/superpowers/brainstorms/2026-05-15-kill-experiment-class.md`.

## Task 20: Add `benchmarks/README.md` Catalogue

**Files:**

- Create: `ergon_builtins/ergon_builtins/benchmarks/README.md`

The CLI no longer dispatches benchmarks, so the discoverability surface is documentation.  This README is the catalogue.

- [ ] **Step 1: Write the README**

  ```markdown
  # Builtin Benchmarks

  Each subdirectory is one benchmark.  Import from Python; there is no
  CLI authoring path.

  | Benchmark | Module | Worker factories | Default sandbox |
  |---|---|---|---|
  | MiniF2F | `ergon_builtins.benchmarks.minif2f` | `make_minif2f_worker` (ReAct) | `LeanSandbox` |

  Adding a new benchmark = a new subdirectory.  Update this table in
  the same PR.

  ## Authoring example

  See `docs/superpowers/brainstorms/2026-05-15-kill-experiment-class.md`
  for the full Python authoring example.  Minimal:

      from ergon_builtins.benchmarks.minif2f import MiniF2FBenchmark, make_minif2f_worker
      from ergon_core.api import persist_benchmark, launch_run

      benchmark = MiniF2FBenchmark(worker_factory=make_minif2f_worker, limit=10)
      handle = persist_benchmark(benchmark, name="minif2f-react", experiment="ablation-2026-05-15")
      await launch_run(handle.definition_id)
  ```

- [ ] **Step 2: Add an architecture-doc cross-reference**

  In `docs/architecture/06_builtins.md`, add a "Discovery" sub-section pointing at this README as the canonical catalogue.  See Task 8 (already covers other 06_builtins.md edits; add this one as a step there or as a Phase 2 addendum).

## Task 21: Update All Remaining Callsites (Tests, Inngest, Dashboard)

**Files:**

- Modify: every test file constructing `Experiment(...)` (~20 files; identify via `rg`)
- Modify: every Inngest event payload naming `experiment` semantically
- Regenerate: dashboard contract schemas (`pnpm run generate:contracts`); hand-fix any consumer TypeScript that typecheck-fails
- Modify: any fixture or conftest that yields `Experiment` instances

- [ ] **Step 1: Tests**

  ```bash
  rg "Experiment\(" --type py ergon_core/tests/ ergon_builtins/tests/ ergon_cli/tests/ tests/
  ```

  Rewrite each from `Experiment(benchmark=b, name="x", metadata={})` → either:
  - direct `persist_benchmark(b, name="x", metadata={})` if the test was exercising persist;
  - or just drop the `Experiment` wrapper if the test was using it as a struct;
  - update assertions that read `experiment.benchmark` / `experiment.name` to read the kwarg directly.

- [ ] **Step 2: Inngest event payloads**

  ```bash
  rg "experiment_id\b\|experiment\s*:\s*Experiment\|experiment\s*:\s*\"" ergon_core/
  ```

  Likely sites: `core/application/experiments/launch.py` event payloads, any `*_inngest.py` handlers.  Rewrite to use `definition_id` for the runtime identity (it always was the actual key; the name was just misleading) and `experiment: str | None` for the tag.

- [ ] **Step 3: Dashboard TypeScript**

  ```bash
  # Find consumer TypeScript that references the renamed types:
  rg "ExperimentRecord\|experiment_record\|ExperimentDefineRequest" ergon-dashboard/src/ --type ts --type tsx | grep -v generated
  ```

  Workflow: (1) run `pnpm run generate:contracts` from `ergon-dashboard/` — this regenerates the Zod schemas from the backend's renamed Pydantic models, picking up `BenchmarkDefinitionRecord` and the new `experiment: str | None` field automatically.  (2) Run `pnpm run typecheck`; for each consumer file that fails, rename the referenced type / field by hand.  (3) Update any UI surface labeling — the `experiment` column is the optional grouping tag; the `name` column is the per-definition human label.  Both are user-facing.

- [ ] **Step 4: Run full test suite**

  ```bash
  pnpm run test:be:fast
  pnpm run check:fe   # dashboard typecheck + lint
  ```

  Both must pass.  If frontend has tests, run those too.

## Task 22: Finalise Architecture Docs + RFC Framing for Phase 2

**Files:**

- Modify: `docs/architecture/01_public_api.md`
- Modify: `docs/architecture/06_builtins.md`
- Modify: `docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/00-readme.md`
- Modify: `docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/01-api-surface.md`

(Some of these may have been partly updated in Task 8 / Task 9 for Phase 1's framing — finalise here for the post-Experiment-kill state.)

- [ ] **Step 1: `01_public_api.md`** — drop the `Experiment` type from the type list.  Add `persist_benchmark(benchmark, *, name, experiment=None, metadata=None) -> DefinitionHandle` as the canonical authoring API.  Note: the word "experiment" survives only as a `str | None` field, not a class.

- [ ] **Step 2: `06_builtins.md`** — add the Discovery sub-section pointing at `benchmarks/README.md`.  Note that the CLI is observation-only after PR 6.5.

- [ ] **Step 3: `00-readme.md`** — rewrite the "experiment" terminology section to match the brainstorm doc.  The class is gone; the word is a label.  Cross-reference the brainstorm doc for the longer rationale.

- [ ] **Step 4: `01-api-surface.md`** — drop `Experiment` from the public API type list.  Add `persist_benchmark`.  Add a short note on `experiment: str | None` semantics (tag, not class).

## Task 23: Phase 2 Check Suite

- [ ] **Step 1: Full backend checks**

  ```bash
  pnpm run check:be
  ```

  All green.

- [ ] **Step 2: Full backend tests**

  ```bash
  pnpm run test:be:fast
  ```

  All green.  Expect a slight test-count change (deleted CLI authoring tests) but no failures.

- [ ] **Step 3: Frontend checks (dashboard)**

  ```bash
  pnpm run check:fe
  ```

  All green.

- [ ] **Step 4: Verify the Experiment class is truly gone**

  ```bash
  rg "class Experiment\b" .       # zero hits in code (history/docs OK)
  rg "from ergon_core.*import.*Experiment\b" .   # zero hits
  rg "ExperimentRecord\b" .                       # zero hits in code
  rg "ExperimentDefineRequest\b" .                # zero hits
  ```

  Any hit outside of `docs/superpowers/brainstorms/` or `docs/rfcs/active/2026-05-11-.../` is a bug.

## Task 24: Phase 2 Commit

```bash
git add -A
git commit -m "PR 6.5 (2/2): kill Experiment class; persist_benchmark + experiment column

- Hard delete ergon_core.api.experiment.Experiment (no alias)
- Rename persist_definition(experiment) → persist_benchmark(benchmark, *, name, experiment=None, ...)
- Rename ExperimentRecord SQLModel + 'experiments' table → BenchmarkDefinitionRecord / 'benchmark_definitions'
- Add experiment: str | None column for grouping related definitions
- Delete CLI authoring commands (ergon experiment define / run) — clean break
- Add ergon_builtins/benchmarks/README.md as catalogue (replaces deleted CLI registry)
- Update all tests, Inngest payloads, dashboard TypeScript
- See docs/superpowers/brainstorms/2026-05-15-kill-experiment-class.md for rationale"
```

PR is now ready to push.  Two commits, one PR: file moves + Experiment kill.

## Verification

After both commits land:

- All `pnpm run check:be` steps green.
- All `pnpm run test:be:fast` tests pass.
- All `pnpm run check:fe` checks pass.
- `rg "ergon_builtins\.sandboxes"` zero hits in code.
- `rg "ergon_builtins\.toolkits"` zero hits in code.
- `rg "class Experiment\b"` zero hits in code.
- `rg "ExperimentRecord\b"` zero hits in code.
- `rg "persist_definition\b"` zero hits in code.
- The architecture docs (`06_builtins.md`, `01_public_api.md`) describe the new framing.
- The cardinality matrix appears in `06_builtins.md`.
- `ergon_builtins/benchmarks/README.md` exists and lists the builtin benchmarks.

## What This PR Is NOT

- Not a worker-subclass-per-benchmark rewrite.  The point is the opposite: lock in the "factory function per strategy, not subclass per benchmark" pattern before PR 10a/10b/10c replicate it.
- Not a `Sandbox` / `Toolkit` API redesign.  The Pydantic-bound model + `_type` discriminator pattern from PR 5 stands.
- Not a CLI rewrite.  Lifecycle commands (`run status`, `run cancel`, etc.) are added in PR 8 — *not* in this PR.  PR 6.5 only deletes the CLI authoring route.
- Not a behaviour change in `Benchmark.build_instances()`.  PR 5/6's design (inline worker/sandbox/evaluators on each Task) stands.

## Risks

- **Import cycles re-emerge differently.**  The PR 6 cycle (lazy import in `MiniF2FToolkit.tools()`) survives Phase 1's move but the path description in the `# reason:` comment needs updating.  Task 2 Step 3 covers this; double-check post-move.
- **Test discovery surprises.**  Pytest discovery rooted at `ergon_builtins/tests/unit` finds tests by directory; moved files shouldn't affect discovery.  Confirm with `pytest --collect-only` if anything looks off.
- **Registry references survive.**  Search for any `worker_factory` string in `registry_core.py` / `registry.py`; PR 6 didn't remove the legacy registry binding for `"minif2f-react"`, so the file is still referenced by string.  Task 3 Step 4 covers this — if it imports `MiniF2FReactWorker` from `worker_factory`, the rename needs to update that import too.
- **Dashboard contract drift.**  The frontend reads via the REST API + Zod schemas generated from Pydantic JSON Schema (no Drizzle).  Phase 2 Task 21 Step 3 covers regenerating contracts and fixing typecheck failures.  Risk: forgetting to run `pnpm run generate:contracts` after backend renames, leaving the dashboard typing against stale schemas.  *Mitigation: Task 21 Step 3 explicitly runs the regeneration; Task 23 runs `pnpm run check:fe`.*
- **Inngest event payload drift.**  Event payloads that named `experiment_id` semantically need rewriting to `definition_id`.  Phase 2 Task 21 Step 2 covers this — risk is missing one and silently breaking a workflow.  *Mitigation: run E2E tests if available.*
- **Phase 1 and Phase 2 commits must land together.**  Phase 1 alone leaves `Experiment` alive but PR 8's CLI dispatch references the now-renamed file paths — landing only Phase 1 creates a broken intermediate state.  Don't split the PR.
