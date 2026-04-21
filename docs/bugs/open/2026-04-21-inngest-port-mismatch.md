---
status: open
opened: 2026-04-21
fixed_pr: null
priority: P0
invariant_violated: null
related_rfc: null
---

# Bug: `INNGEST_API_BASE_URL` default port does not match the real-LLM compose overlay

## Symptom

The real-LLM canary test `tests/real_llm/benchmarks/test_smoke_stub.py`
fails end-to-end because its host-side `uv run ergon benchmark run ...`
subprocess cannot reach Inngest. The subprocess falls back to
`Settings.inngest_api_base_url`'s default (`http://localhost:8289`) and
raises `httpx.ConnectError` against that address, because
`docker-compose.real-llm.yml` publishes Inngest on host port **8288**,
not 8289. The canary never exercises `/api/test/read/run/{id}/state`
and the CLI invocation returns non-zero before any pipeline work runs.

## Repro

1. Check out `feature/real-llm-harness-infra`.
2. `docker compose -f docker-compose.real-llm.yml up -d --wait`.
3. `uv run pytest tests/real_llm/benchmarks/test_smoke_stub.py -v`
   (with `ERGON_REAL_LLM=1` etc.).

The CLI subprocess launched from the test body inherits the host
environment. Since `INNGEST_API_BASE_URL` is not set there, the
subprocess uses the `Settings` default:

- Default: `ergon_core/ergon_core/core/settings.py:27` →
  `inngest_api_base_url: str = "http://localhost:8289"`.
- Actual host port: `docker-compose.real-llm.yml:25` → `"8288:8288"`.

CI avoids this by setting `INNGEST_API_BASE_URL=http://localhost:8289`
explicitly in `.github/workflows/e2e-benchmarks.yml:48,100` — but that
value only works because `docker-compose.ci.yml:47-48` maps host port
`8289:8288`. The real-LLM overlay maps `8288:8288`, so the default and
the CI value both miss.

## Root cause

Two files disagree on which host port Inngest listens on in the
real-LLM local stack:

- `docker-compose.real-llm.yml:25` publishes Inngest as `8288:8288`
  (host 8288).
- `ergon_core/ergon_core/core/settings.py:27` defaults
  `INNGEST_API_BASE_URL` to `http://localhost:8289` — a value that
  matches the CI overlay's `8289:8288` mapping but not the real-LLM
  overlay.

The host-side canary subprocess inherits the wrong default and tries
`localhost:8289`, which nothing is listening on.

## Scope

- Every invocation of the real-LLM canary
  (`tests/real_llm/benchmarks/test_smoke_stub.py`) on a developer
  machine using `docker-compose.real-llm.yml`.
- Any host-side `uv run ergon ...` invocation against the real-LLM
  stack that does not explicitly set `INNGEST_API_BASE_URL`.
- Does not affect CI — the e2e-benchmarks workflow sets
  `INNGEST_API_BASE_URL=http://localhost:8289` explicitly and uses
  `docker-compose.ci.yml`, which maps 8289 on the host.
- Does not affect in-network traffic — the `api` container reaches
  Inngest via `http://inngest:8288` (docker network), unaffected by
  host port-publish mapping.

## Proposed fix

Two small changes, preferred option "standardize on 8288 on host for
the real-LLM overlay":

1. In `tests/real_llm/benchmarks/test_smoke_stub.py`, extract the
   subprocess env-dict construction into a `_subprocess_env()` helper
   and add
   `"INNGEST_API_BASE_URL": os.environ.get("INNGEST_API_BASE_URL", "http://127.0.0.1:8288")`
   so the subprocess targets the port the real-LLM overlay actually
   publishes.
2. Document the host-side port assumption in
   `tests/real_llm/fixtures/stack.py` (module comment / named constant)
   so future fixtures agree on the same value.

Add a tiny unit test (`tests/unit/test_canary_smoke_env.py`) that
imports `_subprocess_env` and asserts the default value, so a future
drift between the compose file and the canary is caught without
standing up Docker.

Leave `docker-compose.real-llm.yml` alone — port 8288 is already where
Inngest actually listens and matches the internal
`http://inngest:8288` URL the `api` container uses.

## On fix

When moving from `open/` to `fixed/`:
  - Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
  - Confirm the canary subprocess reaches Inngest when the real-LLM
    overlay is the only stack running on the host.
  - If the `Settings.inngest_api_base_url` default is ever updated to
    match, note it here so the CI workflow's explicit override can be
    removed in the same PR.
