# 07 — Testing

## 1. Purpose

Describe Ergon's standing testing posture: four tiers with non-overlapping roles, a canonical smoke program that every PR runs against real E2B + real Postgres, and the handoff contracts between layers (criteria, runtime, dashboard). A green CI run implies production correctness for everything except non-deterministic model behaviour, which lives in its own tier.

Transition history + rationale behind this posture live in [`docs/superpowers/plans/test-refactor/`](../superpowers/plans/test-refactor/) (delete that folder after the standing system has been running for a week).

## 2. Tiers

Path-based, not marker-based. The local gate and the CI workflow both dispatch by directory.

| Tier | Path | Infra | CI trigger | Proves |
|------|------|-------|------------|--------|
| **Unit** | `tests/unit/` | None — no I/O, no fixtures | every PR (`ci-fast.yml`) | Pure logic: Pydantic, validators, registry wiring, pure functions, static lints |
| **Integration** | `tests/integration/` | Real Postgres 15 + real Inngest dev server (docker-compose.ci.yml) | every PR (`ci-fast.yml`) | Graph / service / persistence semantics; API boundaries; harness round-trips |
| **E2E smoke** | `tests/e2e/` | Full Docker stack + **real E2B** + dashboard + Playwright | every PR (`e2e-benchmarks.yml` matrix) | Cross-service + cross-process + UI truth; sandbox provisioning at volume; cohort-parallel scheduling; partial-work persistence on FAILED tasks |
| **Real-LLM** | `tests/real_llm/` | As e2e + real model calls, budget-gated | on demand + nightly | Non-deterministic model behaviour; RL trajectory extraction |

`@pytest.mark.slow` is available for local dev ergonomics only; CI runs everything in-tier.

**Decision rule.** Pure function / validator / pydantic model / registry key → unit. Exercises graph, persistence, or an HTTP boundary → integration. Needs sandbox + dashboard + UI → e2e smoke. Needs LLM → real-llm.

## 3. Canonical smoke program

Every PR runs three benchmark legs in parallel via `.github/workflows/e2e-benchmarks.yml`:

| Leg | Slot 1 | Slot 2 | Slot 3 |
|---|---|---|---|
| `researchrubrics` | happy | happy | **sad** — `l_2` forced FAIL |
| `minif2f` | happy | happy | happy |
| `swebench-verified` | happy | happy | happy |

**9 top-level runs per PR; 80 leaf sandbox acquisitions** (8 happy × 9 leaves + 1 sad × 8 leaves — `l_3` never provisioned because its dependency failed).

### 3.1 Immutable 9-leaf DAG

Every smoke run — happy or sad — spawns exactly this graph:

```
Diamond (4):           Line (3):               Singletons (2):
    d_root             l_1 → l_2 → l_3             s_a     s_b
   ↙      ↘
d_left   d_right
   ↘      ↙
    d_join
```

Topology is enforced by `tests/e2e/_fixtures/smoke_base/worker_base.py::SmokeWorkerBase.execute` being decorated `@typing.final`. Subclasses supply the leaf slug via `leaf_slug` and (optionally) override `_spec_for(slug, deps, desc)` to route specific slugs elsewhere — the sad-path subclass uses this to route `l_2` to a failing leaf. They cannot change the DAG itself.

The single source of truth for topology is [`tests/e2e/_fixtures/smoke_base/constants.py`](../../tests/e2e/_fixtures/smoke_base/constants.py):

```python
EXPECTED_SUBTASK_SLUGS = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)
```

### 3.2 Fixture residency — test-only, out of `ergon_builtins`

`ergon_builtins/` contains only production baselines (ReActWorker, TrainingStubWorker). All smoke workers, leaves, and criteria live under [`tests/e2e/_fixtures/`](../../tests/e2e/_fixtures/) and register into the process-level `WORKERS` / `EVALUATORS` dicts via an import side-effect in `tests/e2e/_fixtures/__init__.py`, which `tests/e2e/conftest.py` imports at session start.

11 registry rows total — none production:

| Slug | Kind |
|---|---|
| `{env}-smoke-worker` × 3 | Worker (parent) — inherits `SmokeWorkerBase` |
| `{env}-smoke-leaf` × 3 | Worker (leaf) — inherits `BaseSmokeLeafWorker` |
| `researchrubrics-sadpath-smoke-worker` | Worker (sad-path parent) |
| `researchrubrics-smoke-leaf-failing` | Worker (sad-path failing leaf) |
| `{env}-smoke-criterion` × 3 | Criterion — inherits `SmokeCriterionBase` |

where `{env} ∈ {researchrubrics, minif2f, swebench}`.

### 3.3 Turn persistence

- Parent `SmokeWorkerBase.execute` yields **3** `GenerationTurn`s (planning → planned → awaiting) so incremental turn persistence is exercised on every run.
- Each leaf `BaseSmokeLeafWorker.execute` yields **2** turns (attaching → done).
- Total per happy run: **1 × 3 + 9 × 2 = 21** `GenerationTurn` rows; driver asserts on this.

### 3.4 Inter-agent messaging

Each happy-path leaf calls `CommunicationService.save_message` once on the `smoke-completion` thread (first production caller of that service). 9 `ThreadMessage` rows per happy run, sequence_num 1..9 per thread. Sad-path `l_2` raises before reaching this call — 8 messages on a sad run, with `l_2` missing.

### 3.5 Sandbox-side checks

The criterion's `_verify_sandbox_setup` hook runs a trivial env-specific command in the parent task's live sandbox via `context.runtime.run_command(...)` (per RFC `2026-04-17-criterion-runtime-di-container`, accepted). The sandbox is kept alive through criterion execution per RFC `2026-04-17-sandbox-lifetime-covers-criteria`. Per env:

- **researchrubrics** — bash + coreutils + `/tmp` writability (echo → wc -l → OK marker).
- **minif2f** — `lean --check` of `theorem health_check : True := trivial`. No `|| true`; toolchain breakage fails loudly.
- **swebench** — `python` runs a HEALTH_OK marker + `import pytest` resolves.

## 4. Per-run assertion surface

For each run in a cohort, the pytest driver asserts:

| Channel | What it checks |
|---|---|
| `RunGraphNode` | 10 nodes (1 root + 9 leaves); all COMPLETED (happy) or cascade pattern (sad); `sorted(slugs) == EXPECTED_SUBTASK_SLUGS` |
| `RunGraphEdge` | 6 expected dependency edges (diamond + line) |
| `RunResource` | ≥ 18 rows (9 outputs + 9 probes); all with non-empty `content_hash` |
| `GenerationTurn` | Exactly 21 rows per happy run (derived from `PARENT_TURN_COUNT + 9 × LEAF_TURN_COUNT`) |
| `ThreadMessage` (topic `smoke-completion`) | 9 messages per happy run / 8 per sad; `sequence_num` strictly 1..N |
| Blob store round-trip | Re-read of one probe JSON is byte-stable + parses |
| Temporal ordering | `RunTaskExecution.started_at` of children ≥ `completed_at` of parents |
| `RunTaskEvaluation` | Exactly 1 row; score 1.0 (happy) / 0.0 (sad); failed slug named in sad feedback |

Sad-path adds: partial artifact persisted (partial_*.md exists as RunResource), pre-failure WAL entry present, `l_3` status BLOCKED/CANCELLED per RFC `static-sibling-failure-semantics`.

## 5. Harness

`/api/test/*` FastAPI router at [`ergon_core/core/api/test_harness.py`](../../ergon_core/ergon_core/core/api/test_harness.py). Mounted only when `ENABLE_TEST_HARNESS=1`; write endpoints additionally gated by `X-Test-Secret: ${TEST_HARNESS_SECRET}`.

Read endpoints (Playwright + pytest consume):

| Endpoint | Shape |
|---|---|
| `GET /api/test/read/run/{run_id}/state` | `TestRunStateDto` — graph nodes, mutations, evaluations, resource count |
| `GET /api/test/read/cohort/{cohort_key}/runs` | `[{run_id, status}]` — returns empty list on miss (not 404) for cheap polling |

Write endpoints (`POST /write/run/seed`, `POST /write/reset`) are dashboard-fixture scaffolding; smoke does not use them.

`tests/e2e/_asserts.py::wait_for_terminal` polls the read endpoint every 2s until `status ∈ {completed, failed, cancelled}`.

## 6. Dashboard + Playwright

Per leg, the pytest driver subprocesses `pnpm --dir ergon-dashboard exec playwright test tests/e2e/{env}.smoke.spec.ts`, passing cohort state via env vars:

- `COHORT_KEY`, `SCREENSHOT_DIR`, `TEST_HARNESS_SECRET`, `ERGON_API_BASE_URL`
- `SMOKE_COHORT_JSON` — JSON array of `[{run_id, kind}]` enabling per-kind dispatch in the Playwright spec

Per-env spec is a 3-line file that delegates to the shared factory at `ergon-dashboard/tests/e2e/_shared/smoke.ts`. The factory iterates the cohort array, asserts against the backend harness DTO + the dashboard UI (keyed on `data-testid`), and captures screenshots per-run. The harness access goes through `ergon-dashboard/tests/helpers/backendHarnessClient.ts`.

Required `data-testid` attributes: `run-status`, `task-node-{slug}` (one per `EXPECTED_SUBTASK_SLUGS`), `graph-canvas`, `cohort-run-row`, `cohort-env-label`.

## 7. CI workflow

[`.github/workflows/e2e-benchmarks.yml`](../../.github/workflows/e2e-benchmarks.yml):

- Trigger: `pull_request` + `workflow_dispatch`.
- Matrix: `env ∈ {researchrubrics, minif2f, swebench-verified}`.
- Per leg: `docker compose up --build --wait` with BuildKit GHA cache (`cache_from/cache_to: type=gha`) → `ci/wait_for_stack.sh` → dashboard prod build + start → `ci/wait_for_dashboard.sh` → Playwright install (cached) → `uv run pytest tests/e2e/test_{env}_smoke.py --timeout=270`.
- Per leg: 10-min job timeout; pytest hard ceiling 5 min (RFC).
- Screenshot upload runs `if: always()` so dashboard state is captured even on failure: `ci/push_screenshots.sh` pushes PNGs to the orphan branch `screenshots/pr-{N}`; `ci/pr_comment_screenshots.sh` posts a markdown comment linking them.
- `cleanup-screenshots.yml` deletes the branch on PR close.

## 8. Invariants

1. **Topology is identical across all envs.** Enforced by `@final` on `SmokeWorkerBase.execute`. Tested by `tests/unit/smoke_base/test_smoke_worker_base_final.py`.
2. **No LLM calls on the smoke path.** Enforced by convention + grep: `rg 'OPENROUTER|anthropic|openai|pydantic_ai' tests/e2e/` must return zero.
3. **Test stubs live in `tests/e2e/_fixtures/`, not `ergon_builtins/`.** Production registry (`ergon_builtins/registry_core.py`) contains only production baselines. Exception: `training_stub_worker.py` — it's a real RL-trajectory baseline, not test scaffolding; operators invoke it via CLI.
4. **Criteria reconnect via the CriterionRuntime DI container, never via `AsyncSandbox.connect` directly.** Enforced by code inspection; the anti-pattern previously fixed by `bugs/fixed/2026-04-18-swebench-criterion-spawns-sandbox.md`.
5. **Sandbox outlives the task until all criteria finish.** RFC `sandbox-lifetime-covers-criteria`. Smoke is the living regression test for this.
6. **Cohort parallelism exercised on every PR.** 3-run cohorts prove concurrent workflow submission and cohort aggregation at the scale smoke uses.
7. **Partial work persists on FAILED leaves.** Sad-path `AlwaysFailSubworker` writes a file + runs a probe command, then raises. Driver asserts the partial artifact and pre-failure WAL entry survive.

## 9. Budget

| Measure | Value |
|---|---|
| Per matrix leg | 10-min job timeout; 5-min pytest timeout |
| Leaf-subtask sandbox acquisitions per leg | 26 or 27 (researchrubrics has 26 because the sad slot skips `l_3`) |
| Leaf-subtask sandbox acquisitions per PR | 80 across 3 sandbox images |
| Parent-task sandbox per run | 1 (used by parent worker + attached to by the criterion). Not additional at evaluation time. |
| Parallel workflow runs per PR | 9 (3 legs × 3-run cohort) |
| Warm wall-clock per leg | 1–3 min (post-Docker cache) |
| Cold wall-clock per leg | up to 5 min |

E2B API key required on every PR — accepted for private-repo phase; revisit before open-sourcing.

## 10. Known follow-ups

- **`BaseSandboxManager.reconnect`** shipped in `manager.py` (see `bugs/fixed/2026-04-17-sandbox-lifetime-covers-criteria*` / RFC) but `CriterionRuntime.ensure_sandbox` still uses the in-process `get_sandbox(task_id)` path. Cross-process criterion reconnect (Phase G of the test-refactor program) wires `ensure_sandbox` through `reconnect` so the path is actually exercised.
- **Sandbox command WAL / lifecycle event persistence.** `SandboxEventSink.sandbox_command` + `sandbox_closed` fire reliably into the dashboard event sink, but no dedicated Postgres persistence exists yet. The corresponding driver assertions in `tests/e2e/_asserts.py` soft-skip when the tables are absent; land persistence to turn those into hard assertions.
- **Static-sibling-failure-semantics RFC** (`docs/rfcs/active/2026-04-17-static-sibling-failure-semantics.md`) is still active. The sad-path driver accepts `l_3 status ∈ {blocked, cancelled}`; tighten once the RFC pins the exact value.
