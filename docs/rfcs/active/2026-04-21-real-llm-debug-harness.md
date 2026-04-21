---
status: active
opened: 2026-04-21
author: cm2435+agent
architecture_refs: [docs/architecture/06_builtins.md, docs/architecture/07_testing.md]
supersedes: []
superseded_by: null
---

# RFC: Real-LLM debug harness for end-to-end benchmark validation

## Problem

Every existing test tier exercises Ergon against **stubbed or deterministic
workers**. `tests/unit/` tests isolated classes; `tests/integration/` tests the
full runtime lifecycle but only with stub workers that don't call LLMs;
`tests/e2e/` is Playwright-driven but the experiments it triggers use stubs
too. This means three things the product actually ships have **never been
exercised end-to-end**:

1. The three benchmark sandbox templates (`researchrubrics`, `minif2f`,
   `swebench-verified`) being functional enough that a real LLM, given the
   right tools, can produce the outputs the criterion expects to find.
2. The generic ReAct worker actually using its injected tools correctly under
   a real model's decision-making — i.e., `add_subtask` is called with the
   right arguments, `bash` invocations land in the sandbox, `cancel_task`
   correctly transitions state.
3. The per-benchmark criteria correctly parsing / grading the outputs a real
   LLM would write, rather than the synthetic outputs our stubs emit.

We know these paths are broken in places because ad-hoc local runs surface
bugs that our tiered tests don't catch (an outdated Lean toolchain in the
minif2f sandbox, a missing environment variable in the swebench sandbox,
researchrubrics tools returning structures the criterion doesn't parse). We
need a first-class tier that turns "run a real experiment locally and poke
it" into a reproducible, assertion-backed workflow — one we can point at a
benchmark, let loose with a real LLM, and use to validate every moving piece.
That same harness becomes a **bug-hunting instrument**: run it in an
autonomous loop, file each discovered bug, fix and re-run, until the
configured benchmarks behave as documented.

## Proposal

Land a new pytest tier at `tests/real_llm/` that runs real experiments
against a real LLM (Sonnet 4.6 via OpenRouter), asserts Postgres state after
each run, and asserts dashboard state via Playwright. The tier is gated on
two env vars (`ERGON_REAL_LLM=1`, `OPENROUTER_API_KEY`), is marker-skippable
(`@pytest.mark.real_llm`), and ships with a budget guard that skips remaining
tests when cumulative OpenRouter spend exceeds `ERGON_REAL_LLM_BUDGET_USD`
(default `$5`).

The worker under test is the **existing generic ReAct worker** configured
per-benchmark via a new `benchmark_toolkit_composer` DI factory. This factory
unions the benchmark-specific toolkit with the `SubtaskLifecycleToolkit`
(and, for research-style envs, `ResearchGraphToolkit`), producing a single
ReAct worker that has every tool each benchmark's agent is documented to
need. **No new tools are added in this RFC** — `add_subtask`, `plan_subtasks`,
`cancel_task`, `refine_task`, `restart_task`, `list_subtasks`, `get_subtask`,
and sandboxed `bash` already exist; the composer just wires them.

Experiments run via `subprocess.run(["ergon", "benchmark", "run", ...])` so
we exercise the shipped CLI path. The pytest session fixture brings the stack
up (Postgres + Inngest + FastAPI + `pnpm dev:test`) via a new
`docker-compose.real-llm.yml` overlay, unless `--assume-stack-up` is passed
(in which case the developer is expected to have the stack already running
for faster iteration). After subprocess exit, the test polls
`/api/test/read/run/{run_id}/state` from the smoke-shared-infra test harness
(RFC `2026-04-21-e2e-smoke-coverage-rewrite.md`, PR #25) until a terminal
status is reached, asserts DB invariants via `get_session()`, then launches a
headless Playwright spec that navigates the cohort page and run detail page
and asserts the expected nodes render. Screenshots are saved for every run.

### Component sketch

```
tests/real_llm/
├── __init__.py
├── conftest.py                 # session fixture, --assume-stack-up flag
├── fixtures/
│   ├── stack.py                # docker-compose up/down + health probe
│   ├── openrouter_budget.py    # see below
│   └── playwright_client.py    # reuse BackendHarnessClient (from smoke PR)
├── benchmarks/
│   ├── test_smoke_stub.py      # PR 1 canary: stub workers, no LLM cost
│   ├── test_researchrubrics.py # PR 2: 3 random instances
│   ├── test_minif2f.py         # PR 2: 3 random instances
│   └── test_swebench.py        # PR 2: 3 random instances
└── reporting/
    └── results_writer.py       # per-run .results.md + PR body emission

ergon_builtins/ergon_builtins/tools/benchmark_toolkit_composer.py  # NEW
ergon_core/ergon_core/core/providers/generation/openrouter_budget.py  # NEW
docker-compose.real-llm.yml                                       # NEW
```

### Toolkit composition

```python
# ergon_builtins/tools/benchmark_toolkit_composer.py

from ergon_core.api.worker_context import WorkerContext

def compose_benchmark_toolkit(
    *, benchmark_slug: str, ctx: WorkerContext, sandbox: AsyncSandbox
) -> list[Tool]:
    """Return the union of tools a generic ReAct worker needs for a benchmark."""
    lifecycle = SubtaskLifecycleToolkit(
        run_id=ctx.run_id,
        parent_node_id=ctx.node_id,
        sandbox_id=ctx.sandbox_id,
    ).get_tools()

    match benchmark_slug:
        case "researchrubrics":
            return [
                *lifecycle,
                *ResearchRubricsToolkit(...).build_tools(),
                *ResearchGraphToolkit(
                    run_id=ctx.run_id,
                    task_execution_id=ctx.execution_id,
                ).build_tools(),
            ]
        case "minif2f":
            return [*lifecycle, *MiniF2FToolkit(sandbox=sandbox).get_tools()]
        case "swebench-verified":
            return [*lifecycle, *SWEBenchToolkit(sandbox=sandbox).get_tools()]
        case _:
            raise ValueError(f"no toolkit composer for {benchmark_slug!r}")
```

Registration: a new CLI worker slug `react-generic` that the harness passes
as `--worker react-generic --toolkit-benchmark <slug>`. The composition layer
in `ergon_cli/composition/__init__.py` wires this into
`ReactWorker(tools=compose_benchmark_toolkit(...))` at experiment build time.

### OpenRouter budget gate

```python
# ergon_core/core/providers/generation/openrouter_budget.py

class OpenRouterBudget:
    def __init__(self, limit_usd: float) -> None:
        self._limit = limit_usd
        self._baseline: float | None = None

    async def snapshot_baseline(self) -> None:
        data = await self._get_key_status()
        self._baseline = data["usage"]

    async def remaining_usd(self) -> float:
        data = await self._get_key_status()
        return self._limit - (data["usage"] - (self._baseline or data["usage"]))

    async def _get_key_status(self) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            )
            resp.raise_for_status()
            return resp.json()["data"]
```

The session fixture calls `snapshot_baseline()` once. A per-test fixture
calls `remaining_usd()` before each test; if ≤0, it raises `pytest.skip(...)`
with a clear "budget exceeded" reason.

### Assertion model

**Hard gates** (infra bugs — test fails if violated):

- subprocess exits with return code 0
- `/api/test/read/run/{id}/state` returns `status` in `{completed, failed}`
  within budget
- Postgres query via `get_session()`:
  - `RunRecord` row exists
  - `RunGraphNode` count ≥ 1 (at least root node)
  - If benchmark allows subtasks: `RunGraphMutation` with
    `mutation_type="add_subtask"` exists iff the ReAct worker decided to
    delegate
- Playwright:
  - Cohort index page lists the run with the right status
  - Run detail page renders without JS errors and shows ≥ 1 graph node

**Soft gates** (report only — PR 2 adds one asserted form):

- Per-benchmark, over the 3 instances: at least one produced
  `RunTaskEvaluation.score > 0` on the primary criterion
- Per-run tool-call count, per-run wall clock, per-run cost

Soft gate values are persisted to `tests/real_llm/.results/<run-id>.json`
and summarised into a `.results.md` that PR 2's "ship" step attaches to the
PR body.

### CLI surface

```
uv run pytest tests/real_llm/ -m real_llm            # CI default (stack up)
uv run pytest tests/real_llm/ -m real_llm --assume-stack-up
uv run pytest tests/real_llm/benchmarks/test_minif2f.py -vv -s
```

Env:

- `ERGON_REAL_LLM=1` — activates the tier
- `OPENROUTER_API_KEY` — must be set; tests skip cleanly otherwise
- `ERGON_REAL_LLM_MODEL` — default `openrouter/anthropic/claude-sonnet-4.6`
- `ERGON_REAL_LLM_BUDGET_USD` — default `5.0`
- `ERGON_REAL_LLM_MAX_TURNS` — default `40`
- `ERGON_REAL_LLM_WALL_CLOCK_S` — default `300`

## Invariants affected

- **`docs/architecture/07_testing.md`** — adds a new tier (`tests/real_llm/`)
  alongside `unit/`, `integration/`, `e2e/`. Update the testing-tier matrix
  section to list its opt-in activation, budget gate, and non-CI-default
  posture.
- **`docs/architecture/06_builtins.md`** — adds
  `benchmark_toolkit_composer` to the builtin tools registry section.
- **Cross-cutting:** no new sandbox-lifecycle, artifact, or error-propagation
  invariants introduced. The tier uses the same sandbox lifecycle and test
  harness as smoke-shared-infra PR #25; only adds a marker and gated
  execution path.

## Migration

No existing test fails or changes behaviour. Nothing is deleted. New files
only, plus a small addition to `ergon_cli/composition/__init__.py` to
resolve `--worker react-generic --toolkit-benchmark <slug>` into
`ReactWorker(tools=compose_benchmark_toolkit(...))`.

No Alembic revision. No data migration.

## Rollout (4 PRs)

### PR 1 — Harness infrastructure

**Branch:** `feature/real-llm-harness-infra`
**Blocks on:** smoke-shared-infra PR #25 merged to `main`.

Scope:

- `tests/real_llm/` scaffolding (conftest, fixtures, stack fixture with
  `--assume-stack-up`, Playwright fixture, budget fixture)
- `benchmark_toolkit_composer.py` + registration under `react-generic` worker
  slug
- `openrouter_budget.py` module + unit tests
- `docker-compose.real-llm.yml` stack overlay
- One canary: `test_smoke_stub.py` exercising the existing `smoke_test`
  benchmark with **stub workers** (cost = $0), asserting:
  - Subprocess ran, ergon CLI exits 0
  - Postgres has a completed `RunRecord` with `RunGraphNode`s
  - Playwright finds the run in the cohort index and run detail
- Budget gate unit tests use a mocked OpenRouter API
- Architecture doc updates to `06_builtins.md` + `07_testing.md`

Acceptance gate: `pnpm run check:fast` + `uv run pytest tests/unit -v` green
AND `uv run pytest tests/real_llm/ -m real_llm` green **without**
`OPENROUTER_API_KEY` set (i.e. the stub canary runs; real-LLM tests skip
cleanly).

### Bug-hunt phase (between PR 1 and PR 2)

Autonomous loop runs `uv run pytest tests/real_llm/ -m real_llm` with
`ERGON_REAL_LLM=1` set and `OPENROUTER_API_KEY` provided. Each discovered
non-LLM bug follows the CLAUDE.md workflow:

1. File `docs/bugs/open/YYYY-MM-DD-<slug>.md` from `docs/bugs/TEMPLATE.md`.
2. If fix is trivial, open a fix PR that also moves the bug file to
   `docs/bugs/fixed/` and sets `fixed_pr` in frontmatter.
3. If fix is non-trivial, promote to RFC, link via `related_rfc`.

The loop terminates when, for each of the three benchmarks, the hard-gate
assertions all pass on a fresh run.

### PR 2 — Three-example artifact

**Branch:** `feature/real-llm-three-examples`

Scope:

- `test_researchrubrics.py`, `test_minif2f.py`, `test_swebench.py` — each
  parametrized over 3 random benchmark instances (seeded via
  `ERGON_REAL_LLM_INSTANCE_SEED`, default `42`).
- Hard-gate assertions on every test (as in the Proposal).
- Soft-gate: each benchmark's test class asserts "at least 1 of 3 instances
  scored non-zero on primary criterion."
- Results reporter: writes `.results/YYYY-MM-DD-HHMM-<benchmark>.md`
  summarising per-instance score, tool-call count, wall-clock, cost. PR 2's
  ship step attaches a combined report to the PR body.
- Each soft gate that fires gets a `docs/bugs/open/` entry + follow-up PR.

Acceptance gate: all hard gates green on three consecutive runs. Soft gates
document whatever reality is, not an idealised pass rate.

### PR 3 — Results baseline (optional, deferred)

If PR 2 surfaces an interesting capability curve, PR 3 can promote the
3-random to a hand-picked tiered set (easy/medium/hard) and include a stored
baseline. Skip unless requested.

### PR 4 — CI integration (optional, deferred)

Wire a manually-dispatchable workflow (`.github/workflows/real-llm.yml`) that
runs the tier on label `real-llm` on a PR. Defer until PR 2 stabilises.

## Alternatives considered

**Sibling repository.** Rejected. Keeps secrets + flaky runs out of the main
repo but makes Ergon imports awkward, breaks refactor-in-place workflows,
and defeats the "debug in a loop" use case where you want to edit Ergon
source and immediately re-run the harness.

**Examples-dir instead of pytest.** Rejected. The use case is
assertion-backed debugging, not shipped documentation. Example scripts would
still need to implement the assertion model; building that outside pytest
reinvents most of what pytest gives us (fixtures, parametrize, skip, collect,
reports).

**In-process runtime, no CLI subprocess.** Rejected. We'd bypass the Inngest
event path and the CLI composition layer — the exact production code paths
we most need to validate. The "real LLM + real CLI + real Inngest + real
Postgres + real dashboard" shape is the whole point.

**Anthropic API direct, no OpenRouter.** Rejected. OpenRouter gives us
per-model swap (matrix-expansion friendliness) and a single billing/budget
surface. OpenRouter is already Ergon's canonical provider router.

**Hand-picked tiered tasks in PR 2.** Deferred to PR 3. Hand-picked tasks
are more informative but require upfront curation per benchmark; random
instances prove the harness is useful with less human cost.

**Per-benchmark specialized ReAct workers.** Rejected. The three
benchmark-specific workers already exist, but using them means the PR 2
signal is "the specialized workers work," not "the generic ReAct loop +
toolkit composer work." Testing the more general primitive is higher
leverage.

## Open questions

None blocking RFC acceptance. Items deferred to PR 2 / PR 3:

- How the soft-gate "at least 1/3 passes" threshold should evolve as models
  improve. For Sonnet 4.6 in 2026-04, 1/3 feels right for minif2f and
  swebench; researchrubrics may hit 3/3 and the soft gate becomes
  uninteresting.
- Whether the `.results.md` reporter should also upload per-run terminal
  recordings (asciinema) as CI artifacts. Nice-to-have; not in PR 2 scope.

## On acceptance

When this RFC moves from `active/` to `accepted/`:

- Update `docs/architecture/07_testing.md` testing-tier matrix with the new
  `tests/real_llm/` row, its activation env vars, and its non-CI-default
  posture.
- Update `docs/architecture/06_builtins.md` to list
  `benchmark_toolkit_composer` alongside existing toolkits.
- Link the implementation plan
  (`docs/superpowers/plans/2026-04-21-real-llm-debug-harness.md`) from
  here.
- Close `docs/bugs/open/` entries that were resolved during the bug-hunt
  phase; move to `docs/bugs/fixed/` and link `fixed_pr`.
