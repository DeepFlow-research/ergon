# Brainstorm: Real-LLM debug harness

**Date:** 2026-04-21
**Status:** Converged → RFC at `docs/rfcs/active/2026-04-21-real-llm-debug-harness.md`
**Participants:** @cm2435 + agent

---

## Premise

Our existing test tiers (`tests/unit/`, `tests/integration/`, `tests/e2e/`) all
run against stubbed or deterministic workers. That means we've never actually
validated, end-to-end, that:

1. The three benchmark sandboxes (`researchrubrics`, `minif2f`,
   `swebench-verified`) are correctly provisioned and usable by a real LLM.
2. The ReAct worker correctly uses the tools it's given (`add_subtask`,
   `cancel_task`, `bash`, env-specific) under a real LLM's decision-making.
3. The verifiers/criteria correctly read the outputs a real LLM would produce.

Ad-hoc local runs have surfaced bugs that stub-tier tests miss. The goal is to
codify the "run a real experiment locally and poke it" workflow as a first-class
pytest tier — then use that tier as a bug-hunting instrument during an overnight
autonomous loop.

## Converged decisions

### Location — A (`tests/real_llm/` as a pytest tier)

Rejected: `examples/`, sibling repo, hybrid. Rationale: this is **debugging
infrastructure**, not shipped examples. Pytest gives us fixtures, conftest
reuse, parametrize, and skip semantics for free. Examples can be added later.

### Worker shape — generic ReAct + per-benchmark DI'd toolkit

Rejected: per-benchmark specialized workers. The shipped ReAct worker
(`ergon_builtins/workers/baselines/react_worker.py`) takes `tools=[...]` at
construction. We build a `benchmark_toolkit_composer` module that, given a
benchmark slug + `WorkerContext`, returns the right union of toolkits:

- `researchrubrics` → `SubtaskLifecycleToolkit(8)` ∪ `ResearchRubricsToolkit(6)`
  ∪ `ResearchGraphToolkit(6)`
- `minif2f` → `SubtaskLifecycleToolkit(8)` ∪ `MiniF2FToolkit(Lean)`
- `swebench-verified` → `SubtaskLifecycleToolkit(8)` ∪ `SWEBenchToolkit(bash +
  str-replace editor)`

All three per-env toolkits already exist in the repo; the composer is a small
DI factory, not new tool code. **`edit_task_topology` as discussed is not a new
tool — existing `refine_task`/`plan_subtasks`/`restart_task` cover it.**

### Execution topology — C (hybrid stack)

Rejected: in-process runtime (doesn't test what users run); compose-up-only
(slow dev iteration).

pytest session fixture runs `docker compose -f docker-compose.real-llm.yml up
-d` unless `--assume-stack-up` flag is passed. Per-test: spawns `ergon
benchmark run` as subprocess, polls
`/api/test/read/run/{id}/state` from the smoke-shared-infra harness (PR #25)
until the run reaches a terminal state, then:

- DB assertions via in-process `get_session()`
- Playwright assertions (must-have) via `playwright.async_api` against the live
  dashboard — screenshots on every run

Best of both: CI reproducibility via the default fixture, fast dev iteration
via `--assume-stack-up` when a developer already has `pnpm dev:test` running.

### LLM provider / model — Sonnet 4.6 via OpenRouter

Rejected: per-benchmark model; direct Anthropic. Single knob
(`ERGON_REAL_LLM_MODEL`, default
`openrouter/anthropic/claude-sonnet-4.6`), so matrix expansion is a future
trivial change.

### Budget gate — OpenRouter `/api/v1/auth/key` polling

OpenRouter exposes `GET /api/v1/auth/key` returning
`{data: {usage, limit, limit_remaining, ...}}`. We snapshot `usage` at session
start and poll between tests; if `usage - baseline > ERGON_REAL_LLM_BUDGET_USD`
(default `5.0`), remaining tests skip with a clear reason. This plus per-test
wall-clock and max-turn caps from the ReAct agent itself prevents overnight
surprises.

### "Three examples per benchmark" (PR 2) — A (three random distinct instances)

Rejected: same-task × 3 seeds (doesn't test diversity); hand-picked tiered
(too much curation upfront; interesting for PR 3 if this pattern sticks). Seed
pinned in the config so re-runs pick the same instances — reproducibility
without the curation overhead.

### PR 1 acceptance — A (infra-only, stub-worker smoke canary)

Rejected: canary-with-real-LLM in PR 1 (couples infra merge to LLM
availability + cost). The real-LLM agent runs happen in the **bug-hunt phase
between PR 1 and PR 2**, and each bug becomes its own
`docs/bugs/open/YYYY-MM-DD-<slug>.md` + fix PR. PR 2 doesn't freeze until the
bug-hunt phase has converged.

### PR 2 assertion philosophy — Tiered (infra hard, result soft)

Rejected: strict (too red; LLMs are nondeterministic); permissive-only
(misses the "agent isn't using its tools at all" failure mode).

Hard gates (test fails if violated):

- Run reaches a terminal status within budget
- Sandbox set up correctly (no connect/provisioning error)
- At least one tool call made
- Postgres row exists with the right relationships (graph nodes, mutations)
- Playwright finds the run in the dashboard and renders the run detail page

Soft gate (per-benchmark, all instances together):

- At least 1 of 3 instances per benchmark produced a non-zero criterion score

Raw scores are reported, not asserted.

## Key phrases (for RFC consistency)

- **`tests/real_llm/`** — the pytest tier
- **`@pytest.mark.real_llm`** — the opt-in marker
- **`benchmark_toolkit_composer`** — the DI factory
- **`docker-compose.real-llm.yml`** — the stack overlay
- **`openrouter_budget`** — the budget gate module
- **`--assume-stack-up`** — the dev-iteration fixture flag
- **`ERGON_REAL_LLM=1`** + **`OPENROUTER_API_KEY`** — the two env vars that
  activate the tier
- **`ERGON_REAL_LLM_MODEL`** — model override
- **`ERGON_REAL_LLM_BUDGET_USD`** — spend cap

## Explicit non-goals

- Not a CI default. This tier never runs on every PR; only on a manual
  dispatch or the `real-llm` label.
- Not a deterministic regression gate. LLM outputs drift; the infra gate is
  the pass/fail line, scores are artifacts.
- Not a replacement for `tests/e2e/` (Playwright + stubs). That tier stays
  for fast end-to-end frontend coverage.
- Not a new tool. `edit_task_topology` does not become a thing — existing
  tools cover the capability.

## Open questions deferred to the RFC

(none major; all of Q1–Q5 converged)

## Dependencies on other in-flight work

- **smoke-shared-infra PR #25** (`feature/smoke-shared-infra`) lands the
  `/api/test/*` harness endpoints we poll. Must merge before real-LLM PR 1
  starts. Real-LLM PR 1 branches off `main` after #25 merges.
- **testing-posture-reset** (`docs/rfcs/active/2026-04-18-testing-posture-reset.md`)
  PRs 2–4 land the Docker caching, integration-test fixtures, and tests/e2e/
  deletion. Real-LLM PR 1 can proceed without these (falls back to
  `--assume-stack-up` on dev machines), but CI reproducibility is cleaner once
  they land.
