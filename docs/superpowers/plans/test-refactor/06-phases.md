# 06 — Phases, deliverables, acceptance gates

**Status:** draft
**Scope:** internal branch / commit ordering for the single landing PR. Reviewers see one PR; the branch is layered Phase-B through Phase-F so each commit is independently reviewable.

Cross-refs: program in [`00-program.md`](00-program.md); deletions in [`05-deletions.md`](05-deletions.md).

---

## Delivery shape

**One PR** against `main`, with commits ordered B → F. Each phase has:

- **Scope:** what code + docs move in that commit.
- **Deliverables:** the concrete outputs.
- **Acceptance gate:** the test(s) / command(s) that must be green before proceeding to the next phase.

Phase A was Phase A from the prior plan — it already landed. Phase B onward is new work.

---

## Phase A — Tier command hygiene (DONE)

- `package.json`: `test:be:unit`, `test:be:integration`, `test:be:e2e`, `test:be:real-llm`, `test:be:all`, `test:be:coverage`, `test:be:fast` aligned to the 4-tier model.
- `.github/workflows/ci-fast.yml`: unit job runs `tests/unit/` with coverage.

No work remaining.

---

## Phase B — Fixtures scaffolding + test-only registration

**Scope**

- Create `tests/e2e/_fixtures/` package with the structure in [`01-fixtures.md §1`](01-fixtures.md).
- `smoke_base/constants.py` with `EXPECTED_SUBTASK_SLUGS` + `SUBTASK_GRAPH`.
- `smoke_base/subworker.py` — `SmokeSubworker` Protocol + `SubworkerResult` (moved from builtins).
- `smoke_base/worker_base.py` — **new** `SmokeWorkerBase` class with `@final execute()` and `_spec_for(slug, deps, desc)` override hook.
- `smoke_base/leaf_base.py` — `BaseSmokeLeafWorker` (moved from builtins, imports rewired) plus `_send_completion_message` helper invoking `CommunicationService.save_message`.
- `smoke_base/criterion_base.py` — `SmokeCriterionBase` with `_pull_children` + `_pull_probe_results` **concretely implemented** (the current file's `NotImplementedError` stubs filled in).
- `_fixtures/__init__.py` registration hook (empty registry calls until Phase C registers real classes).
- `tests/e2e/conftest.py` imports `_fixtures` at session start.

**Deliverables**

- `_fixtures/` importable; unit tests for each base class added under `tests/unit/` per [`01-fixtures.md §6`](01-fixtures.md):
  - `test_smoke_worker_base_final.py`
  - `test_smoke_worker_spec_for_override.py`
  - `test_base_smoke_leaf.py` (retarget existing)
  - `test_leaf_sends_completion_message.py`
  - `test_failing_leaf_skips_message.py`
  - `test_smoke_criterion_shape.py`
  - `test_smoke_criterion_completed.py`
  - `test_smoke_criterion_probe.py`

**Acceptance gate**

- `pnpm run test:be:unit` green.
- `pnpm run check:be` green (types pass with new imports).
- No production code imports `tests/e2e/_fixtures/`.

**Not in this phase:** deletions, env-specific code, CI workflow changes.

---

## Phase C — ResearchRubrics end-to-end (one env, full pipe)

Proves the pipe end-to-end on one env before replicating twice.

**Scope**

- `tests/e2e/_fixtures/workers/researchrubrics_smoke.py` — `ResearchRubricsSmokeWorker`, `ResearchRubricsSubworker`, `ResearchRubricsSmokeLeafWorker`.
- `tests/e2e/_fixtures/criteria/researchrubrics_smoke.py` — `ResearchRubricsSmokeCriterion._verify_env_content` + `_verify_sandbox_setup`.
- `tests/e2e/_fixtures/workers/researchrubrics_smoke_sadpath.py` — `AlwaysFailSubworker`, `ResearchRubricsFailingLeafWorker`, `ResearchRubricsSadPathSmokeWorker` (see [`01-fixtures.md §3.4`](01-fixtures.md)).
- Register all five new classes in `_fixtures/__init__.py`.
- `tests/e2e/_asserts.py` — shared pytest assertion helpers from [`02-drivers-and-asserts.md §2`](02-drivers-and-asserts.md): `_assert_run_graph`, `_assert_run_resources`, `_assert_run_turn_counts`, `_assert_sandbox_command_wal`, `_assert_sandbox_lifecycle_events`, `_assert_thread_messages_ordered`, `_assert_blob_roundtrip`, `_assert_temporal_ordering`, `_assert_cohort_membership`, `_assert_run_evaluation`.
- `tests/e2e/test_researchrubrics_smoke.py` — cohort-of-3 driver: 2 happy + 1 sad slot. Per-run assertion dispatch on `kind` ([`02-drivers-and-asserts.md §1`](02-drivers-and-asserts.md), sad helpers at [§10](02-drivers-and-asserts.md)).
- `submit_cohort` helper in `ergon_cli/` — takes `slots: list[tuple[worker_slug, criterion_slug]]` so cohorts can be heterogeneous ([`02-drivers-and-asserts.md §6`](02-drivers-and-asserts.md)).
- `wait_for_terminal` helper.
- `ergon-dashboard/tests/e2e/_shared/smoke.ts` + `_shared/expected.ts` + `helpers/backendHarnessClient.ts`.
- `ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts` — single spec file, iterates `cohort: [{run_id, kind}]` and dispatches per-kind assertions ([`03-dashboard-and-playwright.md §4.2`](03-dashboard-and-playwright.md)).
- `data-testid` attributes added to the relevant dashboard components (per [`03-dashboard-and-playwright.md §6`](03-dashboard-and-playwright.md)).
- Unit tests:
  - `test_env_criterion_verify_content.py` (researchrubrics flavour)
  - `test_env_criterion_sandbox_setup.py` (researchrubrics flavour — see [`01-fixtures.md §6`](01-fixtures.md))
  - `test_always_fail_subworker.py` — asserts write→probe→raise ordering
  - `test_registry_smoke_entries.py` — researchrubrics happy + sad slugs registered; no retired slugs present
- Backend `/api/test/read/run/{id}/state` + `/api/test/read/cohort/{key}/runs` endpoints if not already shaped this way.

**Deliverables**

- Running `pnpm run test:be:e2e -- tests/e2e/test_researchrubrics_smoke.py` against a local Docker stack produces a green 3-run cohort (2 happy + 1 sad) with screenshots under `/tmp/playwright/researchrubrics/`. The sad slot's partial artifact (`partial_l_2.md`) and pre-fail `wc -l` WAL entry are both present in Postgres.

**Acceptance gate**

- Local e2e test green: 3 runs on the researchrubrics leg (2 happy with all happy-path assertions + 1 sad with all sad-path assertions), 26 leaf sandbox acquisitions on the researchrubrics image (2×9 + 1×8).
- Playwright spec green: happy runs render COMPLETED nodes + cohort index lists all 3; sad run renders l_2 FAILED + l_3 BLOCKED/CANCELLED + rest COMPLETED.
- All unit tests green.
- `pnpm run check:be` + `check:fe` green.
- The 6 new assertion helpers (`_assert_sandbox_command_wal`, `_assert_sandbox_lifecycle_events`, `_assert_thread_messages_ordered`, `_assert_blob_roundtrip`, `_assert_temporal_ordering`, `_assert_cohort_membership`) all green on the happy-path run.

**Not in this phase:** CI workflow changes (still runs locally only), other two envs, deletions.

---

## Phase D — MiniF2F + SWE-Bench Verified

Replicate Phase C pattern twice. With Phase C as template, this should be mechanical.

**Scope**

- `tests/e2e/_fixtures/workers/minif2f_smoke.py` + criterion.
- `tests/e2e/_fixtures/workers/swebench_smoke.py` + criterion.
- Register both in `_fixtures/__init__.py`.
- `tests/e2e/test_minif2f_smoke.py`.
- `tests/e2e/test_swebench_smoke.py`.
- Playwright specs: `minif2f.smoke.spec.ts`, `swebench-verified.smoke.spec.ts`.
- Unit tests:
  - `test_env_criterion_verify_content.py` — extend with minif2f + swebench cases.
  - `test_registry_smoke_entries.py` — updated to expect all 9 slugs exactly.

**Deliverables**

- All three drivers pass locally.
- Playwright specs pass locally.
- Full registry set correct.

**Acceptance gate**

- `pnpm run test:be:e2e` green on all three files locally.
- `pnpm run test:be:unit` green.
- `test_registry_smoke_entries.py` asserts exactly 9 slugs, no leftovers.

**Not in this phase:** CI workflow, deletions.

---

## Phase E — CI matrix + Docker cache + screenshot delivery

**Scope**

- `docker-compose.ci.yml` — Buildx cache config from [`04-ci-and-workflows.md §3.1`](04-ci-and-workflows.md); pinned image digests.
- `ci/wait_for_stack.sh` + `ci/wait_for_dashboard.sh`.
- `ci/push_screenshots.sh` + `ci/pr_comment_screenshots.sh`.
- `.github/workflows/e2e-benchmarks.yml` rewritten per [`04-ci-and-workflows.md §2`](04-ci-and-workflows.md) — PR-triggered, 3-leg matrix.
- `.github/workflows/cleanup-screenshots.yml` — branch cleanup on PR close.
- `.github/workflows/ci-fast.yml` integration job: ensure it stands up Postgres service (unit job already aligned in Phase A).
- Repo secrets set: `E2B_API_KEY`, `TEST_HARNESS_SECRET`.

**Deliverables**

- First PR to hit this branch runs the full matrix + produces screenshots + posts a PR comment.

**Acceptance gate**

- `e2e-benchmarks` workflow green on the PR opening this phase's commit.
- All three matrix legs under 5 min warm, under 10 min cold.
- Screenshots visible in `screenshots/pr-{N}` branch + PR comment.
- `cleanup-screenshots.yml` deletes branch on PR close (tested by closing and reopening a throwaway PR, or by merging).

**Not in this phase:** deletions of old builtins / RFCs / plans.

---

## Phase F — Deletions + architecture doc rewrite

The heaviest phase for file count, but mechanical — if Phase B–E passed, nothing here should break functionality.

**Scope**

- Every deletion listed in [`05-deletions.md`](05-deletions.md):
  - `ergon_builtins/` stub workers, criteria, rubrics, benchmarks, smoke_test dir.
  - `tests/` orphaned files (`tests/state/` residue, old e2e tests, old SQLite integration tests).
  - `docs/rfcs/accepted/{testing-posture-reset,e2e-smoke-coverage-rewrite}.md`.
  - `docs/rfcs/rejected/{test-harness-endpoints,fixed-delegation-stub-worker}.md`.
  - `docs/superpowers/plans/{e2e-smoke-coverage-rewrite,phase-2-canonical-smoke-spec,unified-testing-e2e-smoke-plan}.md`.
- Training-stub audit outcome (grep from [`05-deletions.md §6`](05-deletions.md)) — either delete or rehome.
- `docs/architecture/07_testing.md` rewritten: 4 tiers, canonical-smoke-shape-enforced-by-inheritance, `/api/test/*` contract, screenshot flow.
- `docs/architecture/06_builtins.md` + `05_dashboard.md` edits.
- Verification commands from [`05-deletions.md §8`](05-deletions.md) return empty.

**Deliverables**

- Branch diff shows:
  - ~15 new files under `tests/e2e/_fixtures/` + `tests/e2e/test_*_smoke.py`.
  - 3 new Playwright specs + 2 shared modules + 1 backend harness client.
  - ~30 deletions across `ergon_builtins/`, `tests/state/`, old `tests/e2e/*`, superseded docs.
  - `07_testing.md`, `06_builtins.md`, `05_dashboard.md` edits.
  - Root `README.md` / onboarding doc updates if they reference stubs.

**Acceptance gate (final, = merge gate)**

Exactly the checklist in [`00-program.md §5`](00-program.md):

- [ ] All 3 `e2e-benchmarks` matrix legs green on the PR.
- [ ] `ci-fast` unit + integration green.
- [ ] No `ergon_builtins/**` file contains `stub` or `smoke` in its name.
- [ ] Registry contains no `canonical-smoke` / `smoke-test` / generic `smoke-leaf` slug.
- [ ] Production dashboard build does not bundle `/api/test/*` routes.
- [ ] Zero LLM references on smoke path: `rg -n 'OPENROUTER|anthropic|openai|pydantic_ai' tests/e2e/` empty.
- [ ] Screenshots land on `screenshots/pr-{N}` + PR comment inline images.
- [ ] Docker cache in effect (warm < 3 min; cold < 5 min per leg).
- [ ] `07_testing.md` points at the standing system; `test-refactor/` folder deleted in this same PR (or in an immediately-following housekeeping PR — see §"Deleting this folder" below).

---

## Phase G — Final: wire `BaseSandboxManager.reconnect` through CriterionRuntime

**Why this is the last step.** Phases B–F ship smoke end-to-end with criteria attaching via direct `AsyncSandbox.connect(sandbox_id=...)`. That works but violates [`architecture/cross_cutting/sandbox_lifecycle.md`](../../../architecture/cross_cutting/sandbox_lifecycle.md) invariant 3 ("criteria MUST reconnect via the manager"). Phase G closes that gap. After Phase G, criteria reconnect to the task's sandbox **through the manager** and hold it open for the entire evaluation.

**Scope**

- Land RFC [`2026-04-17-sandbox-lifetime-covers-criteria`](../../../rfcs/active/2026-04-17-sandbox-lifetime-covers-criteria.md) PR 2 if not already shipped: add `BaseSandboxManager.reconnect(sandbox_id)` (returns `AsyncSandbox`, raises `SandboxExpiredError` on expiry).
- Wire `CriterionRuntime.ensure_sandbox()` (or add `CriterionRuntime.get_sandbox()`) to call `manager.reconnect(context.sandbox_id)` and hold the handle for the duration of `evaluate()`. The sandbox stays open from criterion start through criterion completion — then `check_evaluators` teardown closes it as today.
- Migrate the 3 smoke criteria's `_verify_sandbox_setup` from `AsyncSandbox.connect(sandbox_id=context.sandbox_id)` to `context.get_sandbox()` (or the final DI accessor name). One-line change per criterion — no behavioural change; just routing through the blessed path.
- Add `SandboxExpiredError` handling: smoke criterion subclasses let it bubble; `CriterionRuntime` or `check_evaluators` translates it to a `"sandbox-expired"` evaluation outcome per the RFC.
- Flip invariant 3 in `cross_cutting/sandbox_lifecycle.md` from "pending enforcement" to "enforced end-to-end by smoke tier on every PR".

**Deliverables**

- `BaseSandboxManager.reconnect` shipped with unit tests (`tests/unit/test_sandbox_reconnect.py`: success path, `SandboxExpiredError` on not-found/404/expired, re-raise on other errors).
- `CriterionRuntime` DI accessor for the task's sandbox, holding it open for the criterion's run.
- 3 smoke criteria migrated to the DI accessor.
- `cross_cutting/sandbox_lifecycle.md` invariant 3 updated.
- Optional canary e2e test from the RFC (`tests/e2e/test_sandbox_criterion_timeout_canary.py`) — slow criterion still reaches sandbox when timeout is provisioned correctly.

**Acceptance gate**

- E2E matrix green across all 3 envs on the migration PR — smoke is now the regression test for this invariant on every PR.
- `tests/unit/test_sandbox_reconnect.py` green.
- `rg -n 'AsyncSandbox.connect' ergon_builtins/ tests/e2e/_fixtures/criteria/` returns only the expected production paths (criteria no longer call it directly).
- `cross_cutting/sandbox_lifecycle.md` invariant 3 no longer says "pending".

**Not in this phase:** anything from Phases B–F. Phase G is strictly a migration of the attach mechanism, not a feature addition to smoke.

**Sequencing note.** Phase G is the one phase that can, if necessary, ship as a follow-up PR rather than in the same landing PR as B–F. Smoke is already proving its end-to-end invariant with direct `AsyncSandbox.connect`; the migration to `manager.reconnect` is a tightening, not a correctness fix. If the RFC's PR 2 is still in flight when B–F is merge-ready, ship B–F first and land Phase G within the following week. Mark the PR description explicitly: "interim `AsyncSandbox.connect` in smoke criteria; follow-up Phase G tightens to `manager.reconnect`".

---

## Deleting this folder

`docs/superpowers/plans/test-refactor/` is planning, not documentation. Two options for when it goes away:

1. **In the same PR as Phase F.** Landing PR also removes this folder; `07_testing.md` is the single source of post-landing truth. Cleanest but biggest diff.
2. **Immediately-following housekeeping PR (same day).** Makes Phase F's diff smaller and keeps the plan available for review during the PR window.

Default: **option 2.** If PR review feedback flags option 1 as cleaner, switch.

Either way, do not leave this folder around past the week of landing.

---

## Phase size estimates (for PR structuring)

| Phase | Scope | Est. diff size |
|---|---|---|
| A | Done | — |
| B | 5 base files + 5 unit tests | ~600 LoC add |
| C | 1 env + driver + Playwright + helpers + 2 dashboard endpoints | ~1500 LoC add |
| D | 2 envs × (worker + criterion + driver + spec) | ~1000 LoC add |
| E | CI + cache + scripts | ~400 LoC add |
| F | Deletions + doc rewrites | ~1500 LoC delete, ~500 LoC add (docs) |
| G | `BaseSandboxManager.reconnect` + `CriterionRuntime` DI wiring + 3 one-liner criterion migrations | ~200 LoC add, ~10 LoC replace |

Total (B–F bundle): **~3500 LoC add, ~1500 LoC delete**. Phase G is a small follow-up (or inline if the sandbox-lifetime RFC's PR 2 is ready to land together).

---

## Phase transition discipline

Do not start Phase C until Phase B's acceptance gate is green. Do not start Phase D until Phase C is fully green end-to-end on one env. Phase E requires Phase D (otherwise 2/3 legs fail on the first CI run). Phase F requires Phase E (otherwise there's nothing to prove deletions didn't break). Phase G requires Phase F **only in the sense that it targets the new smoke criteria** — it can ship inline with F or as an immediate follow-up PR once the sandbox-lifetime RFC's PR 2 (`manager.reconnect`) is ready.

This is a chain; each phase's gate protects the next phase from being based on broken scaffolding.

---

## If a phase fails

- **Phase B:** fundamental misunderstanding of current `Worker` / `Criterion` ABCs. Re-read code, update base classes, re-run unit tests.
- **Phase C:** first exposure to real Docker + E2B. Likely: missing env var, sandbox image missing, harness endpoint mismatch. Fix root cause, not the test.
- **Phase D:** env-specific probe choice wrong (e.g. MiniF2F `lean --check` too slow). Widen probe-exit semantics or switch probe command; update `03-dashboard-and-playwright.md §3.2` to match.
- **Phase E:** CI shape issue — Docker cache miss, dashboard port conflict, screenshot push permission. Fix workflow, not the test.
- **Phase F:** deletion missed an import. `git grep` until clean.
- **Phase G:** `manager.reconnect` raises on an unexpected error shape (E2B SDK quirk). Tighten the exception-classification block in `reconnect`; add a regression unit test. Do not swallow unknown errors — let them propagate.

No retry-in-sleep-loop hacks. No `|| true` fallbacks that hide failures. Fix the root cause or escalate.
