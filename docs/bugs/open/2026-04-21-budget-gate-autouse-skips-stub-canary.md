---
status: open  # open | fixed
opened: 2026-04-21
fixed_pr: null  # set to PR number when moved to fixed/
priority: P1  # P0 = production broken; P1 = silent data loss or ux break; P2 = correctness; P3 = cleanup
invariant_violated: docs/architecture/07_testing.md#real-llm-tier
related_rfc: null  # if a fix is being designed, link RFC here
---

# Bug: `autouse` OpenRouter budget gate forces an API key on the zero-cost stub canary

## Symptom

Running `tests/real_llm/benchmarks/test_smoke_stub.py` — the stub canary that
exercises the full harness pipeline without spending a single token — *skips*
when `OPENROUTER_API_KEY` is not set, even though the canary touches zero
external LLMs (model=`stub:constant`, worker=`stub-worker`,
evaluator=`stub-rubric`). Developers and CI must therefore expose an
OpenRouter key just to run a pipeline that costs $0. The canary becomes
un-runnable in a key-free environment.

## Repro

```bash
# ERGON_REAL_LLM=1, no OPENROUTER_API_KEY set.
env -u OPENROUTER_API_KEY ERGON_REAL_LLM=1 \
    uv run pytest tests/real_llm/benchmarks/test_smoke_stub.py -v
```

Expected: canary runs and asserts against the harness / dashboard.

Actual: canary skips with `OPENROUTER_API_KEY not set — skipping real-LLM
tests`, sourced from the `openrouter_budget` fixture transitively required by
`_budget_gate` (which is `autouse=True`).

## Root cause

`tests/real_llm/fixtures/openrouter_budget.py:22-26` defines `_budget_gate`
with `autouse=True`. Because autouse fixtures are injected into *every* test
under `tests/real_llm/`, the stub canary picks up `_budget_gate` as a
dependency, which in turn requires `openrouter_budget`. When
`OPENROUTER_API_KEY` is absent, `openrouter_budget` raises `pytest.skip` and
the cascade skips the canary before it runs.

The gate is only meaningful for tests that actually call OpenRouter; autouse
was the wrong scope.

## Scope

Every run of `tests/real_llm/benchmarks/test_smoke_stub.py` in a key-free
environment (local dev without `OPENROUTER_API_KEY`, bootstrapping CI without
secrets). Any future zero-cost canary added under `tests/real_llm/` inherits
the same breakage.

## Proposed fix

Convert the autouse gate to an opt-in marker-dispatched gate. Rename the
fixture to `enforce_openrouter_budget` (no autouse); add a lightweight
`autouse` dispatcher that only requests `enforce_openrouter_budget` when the
test carries a new `real_llm_billing` marker. Register the marker in
`pyproject.toml` `[tool.pytest.ini_options].markers`. The stub canary stays
unmarked — it is `real_llm` (needs the docker stack) but not
`real_llm_billing` (does not spend) — so it runs without a key.

## On fix

When moving from `open/` to `fixed/`:
  - Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
  - Confirm `docs/architecture/07_testing.md` real-LLM tier row reflects the
    zero-cost canary path.
