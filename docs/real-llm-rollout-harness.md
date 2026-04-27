# Real-LLM rollout harness for researchrubrics

Date: 2026-04-24
Status: design sketch (ignores prior RFCs); spikes complete, one
pre-work PR identified before the harness itself can land.

## Intent

Build a **rollout harness**, not a TDD tier. The test is a trigger; the
artifacts are the product. Running the harness produces a rich,
inspectable snapshot of a real-LLM run against the `researchrubrics`
benchmark that a future agent session (or a human) can read and reason
about in order to iterate on either the agent or the simulator.

This supports the methodological contribution we want to express in the
paper: we are debugging the simulator (ergon_core) and growing a stronger
agent by running real LLM rollouts end-to-end and reading them back.

## Reframe vs. a test tier

The previous framing was a per-benchmark pytest tier with hard-gate
assertions on DB state and UI state. We drop that. The harness asserts
**only** that the benchmark reached a terminal state (`completed`,
`failed`, or `cancelled`) within budget/timeout. `failed` is still a
successful rollout from the harness's perspective — it is a data point.

What drops out:

- No shared `assertions.py` helper (rubric parsing, tool-call
  inspection).
- No per-benchmark assertion knowledge in the test body.
- No "which fields to verify" question at harness-authoring time.

The single assertion is:

```python
assert state["status"] in {"completed", "failed", "cancelled"}
```

## Current state of `tests/real_llm/`

Shipped (PR 1):

- `conftest.py` — marker-gated (`ERGON_REAL_LLM=1`), `--assume-stack-up`
  flag, session fixtures wired.
- `fixtures/stack.py` — docker-compose up/wait/down against the unified
  `docker-compose.yml`.
- `fixtures/openrouter_budget.py` + `ergon_core/.../openrouter_budget.py`
  — live spend check against `/api/v1/auth/key`.
- `fixtures/harness_client.py` — polls
  `/api/test/read/run/{id}/state` for terminal status.
- `fixtures/playwright_client.py` — browser/context session fixtures.
- `benchmarks/test_smoke_stub.py` — zero-cost canary proving the pipe
  (CLI → Postgres → harness → Playwright) with stub workers.

Missing for a real-LLM researchrubrics rollout:

- **Pre-work**: per-benchmark sandbox env-injection + an integration
  test that asserts every required key for every benchmark's sandbox
  is actually present inside the sandbox at provision time. See
  §"Pre-work PR" below.
- `tests/real_llm/rollout.py` — artifact dump helpers.
- `tests/real_llm/benchmarks/test_researchrubrics.py` — the trigger.

## Researchrubrics moving parts (already shipped)

- **Benchmark**: `ResearchRubricsBenchmark`
  (`ergon_builtins/benchmarks/researchrubrics/benchmark.py:32`), plus
  `researchrubrics-vanilla` and `researchrubrics-ablated`. Loads HF
  dataset, honours `--limit N`.
- **Worker**: `researchrubrics-researcher`
  (`ergon_builtins/workers/research_rubrics/researcher_worker.py:53`).
  Concrete `ReActWorker` subclass. At `execute()` time builds a 9-tool
  surface (Exa search / QA / get_content + write/edit/read report
  drafts + `ResearchGraphToolkit` observability tools). Uses
  `pydantic_ai.Agent`, `max_iterations=25`.
- **Evaluator**: `research-rubric` (normalised weighted-criteria
  scorer), wired in `registry_data.py:28`.
- **Sandbox**: `ResearchRubricsSandboxManager` — blank E2B sandbox with
  workspace dirs provisioned. No template file needed.
- **CLI**: `ergon benchmark run researchrubrics --worker
  researchrubrics-researcher --evaluator research-rubric --model <X>
  --limit 1` composes cleanly via `build_experiment`
  (`ergon_cli/composition/__init__.py:42`).

## Keys come from `settings`

All required keys are already surfaced on
`ergon_core/core/settings.py`:

```python
openrouter_api_key     # aliases: OPENROUTER_API_KEY, OPEN_ROUTER_API_KEY
openrouter_base_url    # default: https://openrouter.ai/api/v1
openai_api_key
e2b_api_key
exa_api_key
hf_api_key             # researchrubrics dataset on HF hub
database_url           # for rollout dump
```

`Settings.missing_values(names: list[str]) -> list[str]`
(`settings.py:65`) is the idiomatic preflight.

Fixture-level preflight replaces the old key-plumbed fixtures:

```python
from ergon_core.core.settings import settings

@pytest.fixture(scope="session")
def _required_keys():
    missing = settings.missing_values(
        ["openrouter_api_key", "exa_api_key", "e2b_api_key"],
    )
    if missing:
        pytest.skip(f"real-llm rollout requires {missing}")
```

Budget becomes **soft**: record remaining OpenRouter spend in the
manifest, skip only if already ≤0 at session start.

## Artifact layout

One directory per rollout, named with timestamp and run_id:

```
tests/real_llm/.rollouts/<timestamp>-<run_id>/
├── manifest.json               # run metadata
├── db/
│   ├── run_record.json
│   ├── run_graph_nodes.jsonl
│   ├── run_graph_edges.jsonl
│   ├── run_graph_mutations.jsonl
│   ├── run_generation_turns.jsonl
│   ├── run_context_events.jsonl
│   ├── run_resources.jsonl
│   ├── run_task_evaluations.json
│   └── sandbox_events.jsonl
├── screenshots/
│   ├── cohort_index.png
│   ├── run_detail.png
│   └── node_<id>.png           # optional per-node
└── report.md                   # stitched summary for quick skim
```

`manifest.json` contents:

- `run_id`, `benchmark`, `worker`, `evaluator`, `model`
- wall-clock start/end
- terminal status
- OpenRouter budget snapshot (baseline, post-run, delta)
- key fingerprints (hashes), never raw values
- harness version / git sha

`report.md` is the first thing a reviewing agent should read: prompt,
turn count, tools called (counts), final report excerpt, score if the
evaluator ran, links into the `db/` jsonl files.

## Rollout dump surface

SQLModel tables to snapshot (all present in
`ergon_core/core/persistence/`):

- `RunRecord` (`telemetry/models.py:61`)
- `RunTaskExecution` (`telemetry/models.py:110`)
- `RunResource` (`telemetry/models.py:217`)
- `RunTaskEvaluation` (`telemetry/models.py:267`)
- `RunGenerationTurn` (`telemetry/models.py:415`)
- `SandboxEvent` (`telemetry/models.py:646`)
- `RunGraphNode` (`graph/models.py:44`)
- `RunGraphEdge` (`graph/models.py:96`)
- `RunGraphMutation` (`graph/models.py:172`)
- `RunContextEvent` (`context/models.py:25`)

A single `dump_rollout(run_id, out_dir)` helper: one `get_session()`,
~10 queries, `.model_dump_json()` per row.

## The test itself

Roughly 30 lines:

```python
pytestmark = [pytest.mark.real_llm, pytest.mark.asyncio]

async def test_researchrubrics_rollout(
    real_llm_stack,
    _required_keys,
    playwright_context,
    harness_client,
):
    before = datetime.now(timezone.utc)
    rc = subprocess.run(
        [
            "uv", "run", "ergon", "benchmark", "run", "researchrubrics",
            "--worker", "researchrubrics-researcher",
            "--evaluator", "research-rubric",
            "--model", os.environ.get(
                "ERGON_REAL_LLM_MODEL",
                "anthropic:claude-sonnet-4.6",
            ),
            "--limit", "1",
        ],
        timeout=900,
    ).returncode

    run_id = _latest_run_id_since(before)
    state = harness_client.wait_for_terminal(run_id, timeout_s=900)

    out_dir = _rollout_dir(run_id)
    dump_rollout(run_id, out_dir)
    await capture_dashboard(run_id, playwright_context, out_dir)
    write_manifest(out_dir, rc=rc, state=state, ...)

    assert state["status"] in {"completed", "failed", "cancelled"}
```

## Spike results

**1. OpenRouter model routing.**
`resolve_model_target("anthropic:claude-sonnet-4.6")` resolves to a
PydanticAI chat model backed by
`pydantic_ai.providers.openrouter.OpenRouterProvider`. Cloud provider
prefixes (`openai:`, `anthropic:`, `google:`) are OpenRouter-hosted in
Ergon; use `OPENROUTER_API_KEY` in the process env and do not route
through direct provider APIs.

**2. Exa inside the sandbox — confirmed not wired.** The plumbing
exists but nothing populates it:

- `BaseSandboxManager.create(envs=...)` → `AsyncSandbox.create(envs=...)`
  is wired (`manager.py:280`).
- `SandboxSetupRequest.envs: dict[str, str] = {}` is declared
  (`child_function_payloads.py:23`).
- `execute_task.py:141` constructs the `SandboxSetupRequest` **without
  ever setting `envs`** — the field is always the default empty dict.
- `ResearchRubricsSandboxManager` does not override `create()` to
  inject its own envs; it only overrides `_install_dependencies` to
  `pip install exa-py` and scaffold `/workspace/*` dirs.

Net effect: every researchrubrics rollout today would complete with
Exa tools failing auth inside the sandbox. A rollout harness built on
top of this would produce a degenerate distribution of failure modes
(every run is "agent can't search") instead of useful data.

**And the test gap is real.** Neither
`tests/integration/minif2f/test_sandbox_manager.py` nor
`tests/integration/swebench_verified/test_sandbox_manager.py` asserts
anything about sandbox env injection. There is no
`tests/integration/researchrubrics/test_sandbox_manager.py` at all
(only a stale `.pyc` left over — the `.py` was deleted). This needs a
fix *before* the rollout harness, and the fix should be generic across
all benchmarks.

## Pre-work PR: sandbox env-injection + integration tests

Sandbox env injection is a cross-cutting concern — every benchmark's
sandbox manager should declare exactly which keys its in-sandbox tools
need, and an integration test should assert each declared key actually
arrives inside the sandbox at provision time. This covers
researchrubrics today and anything we add tomorrow.

### Declaration site

Each `Benchmark` subclass already declares
`onboarding_deps: BenchmarkDeps` with an `optional_keys` tuple. For
example:

```python
class ResearchRubricsBenchmark(Benchmark):
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(
        extras=("ergon-builtins[data]",),
        optional_keys=("EXA_API_KEY",),
    )
```

Treat `optional_keys` as the **canonical list of env keys the in-sandbox
tools will read**. The sandbox manager for that benchmark must forward
every key in that list into the sandbox process env.

### Implementation

The cleanest locus is the per-benchmark manager — it already owns
"what this benchmark needs in its sandbox" (packages, directories,
templates). Extending that to env vars keeps benchmark-specific
knowledge out of upstream dispatch code.

Two reasonable patterns — pick one and apply uniformly:

- **a. Manager-composed envs** (preferred): each manager overrides
  `create()` (or a new `_compose_envs()` hook) to read the keys named
  in its benchmark's `BenchmarkDeps.optional_keys` from `settings`,
  merge them into the caller-supplied `envs` dict, and call
  `super().create()`. Missing keys in `settings` raise a clear error
  at `create()` time so misconfigured rollouts fail fast instead of
  producing Exa-401 soup.
- **b. Upstream composer populates `SandboxSetupRequest.envs`** based
  on the benchmark's `BenchmarkDeps` — more generic but spreads
  benchmark-specific knowledge upstream.

### Integration test

One shared parametrised test, one file per benchmark with a sandbox
manager. Mirrors the minif2f/swebench `test_sandbox_manager.py` shape.

For each benchmark: provision the sandbox with a dummy value for every
declared key (e.g. `{"EXA_API_KEY": "test-dummy-12345"}`), then for
each key run `echo $<KEY_NAME>` inside the sandbox and assert stdout
equals the dummy value.

Also assert the negative: if a required key is missing from `settings`,
`manager.create()` raises a clear message.

Concrete files:

- `tests/integration/researchrubrics/test_sandbox_manager.py` (new)
- `tests/integration/minif2f/test_sandbox_manager.py` (extend with env
  assertions — even if minif2f declares no optional keys today, the
  test confirms the declared-set size matches observed-set size and
  future-proofs additions)
- `tests/integration/swebench_verified/test_sandbox_manager.py` (same)
- `tests/integration/gdpeval/test_sandbox_manager.py` (if/when gdpeval
  grows a sandbox manager)

### Acceptance

- `tests/integration/**/test_sandbox_manager.py` green with a dummy
  `EXA_API_KEY` exported by the researchrubrics manager.
- A manually-run researchrubrics smoke rollout no longer emits Exa 401s
  from inside the sandbox.
- `pnpm run check:fast` + `pnpm run test:be:fast` green.

Estimated effort: **half to one day**, unconditional of the rollout
harness — this lands as a standalone fix.

## Minimum shippable harness (after pre-work PR lands)

Files:

1. `tests/real_llm/rollout.py` — `dump_rollout`, `capture_dashboard`,
   `write_manifest`, `_rollout_dir`.
2. `tests/real_llm/benchmarks/test_researchrubrics.py` — the 30-line
   trigger above.
3. Model targets resolve centrally in `resolve_model_target`; use
   provider-prefixed targets such as `anthropic:claude-sonnet-4.6`.
   Cloud provider prefixes route through OpenRouter.

Estimated effort: **half a day** on top of the pre-work PR.

## The loop

After shipping:

```bash
pnpm run test:be:real-llm -k researchrubrics
open tests/real_llm/.rollouts/<latest>/report.md
```

The agent (me, or a future session) reads `report.md`, drills into the
jsonl files or screenshots as needed, and reasons about whether the
task ran successfully — and what to tweak in either the model or the
environment to iterate on the agent. That is the paper-worthy loop:
rollout → read → tweak → rollout.

No unit-test-shaped discipline; rollout-shaped discipline.

## Extensions (deliberately not in v1)

- Parametrise over N seeded instances.
- Soft gates: "at least 1 of N produced a non-zero rubric score".
- Per-instance screenshot of the run graph expanded.
- Auto-opening a `docs/bugs/open/` entry when a rollout surfaces a
  simulator bug (as opposed to a model-quality issue).
- Nightly cron running the harness against all three benchmarks with a
  fresh artifact directory each time.

Keep v1 to one benchmark, one instance, one rollout directory.
