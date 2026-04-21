---
status: open  # open | fixed
opened: 2026-04-21
fixed_pr: null  # set to PR number when moved to fixed/
priority: P0  # P0 = production broken; P1 = silent data loss or ux break; P2 = correctness; P3 = cleanup
invariant_violated: null  # e.g. docs/architecture/03_providers.md#sandbox-event-sink
related_rfc: null  # if a fix is being designed, link RFC here
---

# Bug: real-LLM canary parent pytest process reads wrong `ERGON_DATABASE_URL`

## Symptom

`tests/real_llm/benchmarks/test_smoke_stub.py::test_harness_canary_smoke_stub`
errors out after the CLI subprocess completes but before the Playwright
assertions run. The failure trace points at
`_latest_run_id_since(before)` → `get_session()` raising a psycopg
authentication error against Postgres (wrong password, or wrong port when a
developer's local DB is on the default 5432).

## Repro

1. Start the real-LLM compose overlay: `docker compose -f docker-compose.real-llm.yml up -d`.
2. Have a developer `.env` in the repo root with `ERGON_DATABASE_URL=postgresql://ergon:ergon_dev@127.0.0.1:5432/ergon` (standard Ergon dev setup).
3. Run `ERGON_REAL_LLM=1 uv run pytest tests/real_llm/benchmarks/test_smoke_stub.py -v`.
4. Subprocess CLI succeeds (it uses the compose-overlay URL explicitly). Parent pytest then calls `_latest_run_id_since` and fails with `password authentication failed for user "ergon"` (or connection refused if the dev DB isn't even up).

## Root cause

`tests/real_llm/benchmarks/test_smoke_stub.py:54-60` correctly injects
`ERGON_DATABASE_URL=postgresql://ergon:ergon@127.0.0.1:5433/ergon` into the
subprocess `env` dict. But the **parent pytest process** also needs that URL:
line 87 calls `_latest_run_id_since(before)`, which imports
`ergon_core.core.persistence.shared.db.get_session`. That reads
`ERGON_DATABASE_URL` from the parent's own environment, which was loaded from
`.env` by python-dotenv and points at the developer's local DB with different
credentials and port.

Two different DB URLs end up in play for one test run: the compose overlay for
the subprocess, and the developer `.env` for the parent — guaranteeing a split
and a post-subprocess auth failure.

## Scope

Every real-LLM canary run on any developer machine with a populated `.env`.
Blocks the real-LLM harness tier from passing locally or in CI where `.env` is
present. Trivial to hit — anyone running the canary once.

## Proposed fix

Autouse pytest fixture at the `tests/real_llm/` tree root that monkeypatches
`ERGON_DATABASE_URL` to the compose-overlay URL for every real-LLM test. This
pins both the parent pytest process and any subprocesses (which inherit
`os.environ`) to the same Postgres instance. Test-scaffolding-only; no
production code change.

## On fix

When moving from `open/` to `fixed/`:
  - Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
  - No architecture invariants affected (test scaffolding only).
