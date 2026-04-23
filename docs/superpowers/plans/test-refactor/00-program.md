# 00 — Program, goals, tier model

**Status:** draft
**Date:** 2026-04-23
**Entry-point index:** [`README.md`](README.md)
**Authoritative tech content:** this folder. Everything else is superseded (see [`05-deletions.md`](05-deletions.md)).

This is the "why + what". Technical "how" lives in [`01-fixtures.md`](01-fixtures.md), [`02-drivers-and-asserts.md`](02-drivers-and-asserts.md), [`03-dashboard-and-playwright.md`](03-dashboard-and-playwright.md), [`04-ci-and-workflows.md`](04-ci-and-workflows.md). Delivery ordering in [`06-phases.md`](06-phases.md).

---

## 1. Goals and non-goals

**Goals**

- Four test tiers with strict, non-overlapping roles (unit / integration / e2e-smoke / real-llm).
- Every PR runs unit + integration against **real Postgres + real Inngest** (no SQLite).
- Every PR runs an **e2e smoke matrix** of 3 benchmarks, each submitting **3 cohort-parallel workflow runs** of its own smoke worker, each spawning a **9-leaf DAG** on its own sandbox image — **9 top-level runs per PR, 80 leaf sandboxes per PR**. The researchrubrics cohort's third slot is a **sad-path run** that deterministically fails `l_2` to exercise static-sibling cascade + partial-work-persists-on-failure.
- Dashboard exercised end-to-end via Playwright on every PR, with screenshots pushed back as PR artifacts.
- Zero LLM calls in unit / integration / e2e-smoke. LLM behaviour lives in `tests/real_llm/` only.
- Test-only stubs (workers, criteria, benchmarks, rubrics) live under `tests/e2e/_fixtures/`, not `ergon_builtins`.
- No "canonical smoke" shared worker, no separate `smoke-test` benchmark, no shared smoke-only sandbox image. Smoke is **always per environment**, against that env's own benchmark.

**Non-goals**

- Sub-60s wall-clock targets for smoke. 5-min hard ceiling per matrix leg is the contract.
- New benchmark domains beyond `researchrubrics`, `minif2f`, `swebench-verified`.
- Relaxing "graph shape identical everywhere" — it is enforced by `SmokeWorkerBase.execute()` being `@final`.
- Replacing the real-LLM harness — it keeps its current shape under `tests/real_llm/`.

---

## 2. Tier model

Path-based only. `@pytest.mark.slow` is available for local dev ergonomics; CI runs everything in-tier.

| Tier | Path | Infra | CI trigger | What it proves |
|---|---|---|---|---|
| **Unit** | `tests/unit/` | No I/O | every PR (`ci-fast`) | Pure logic: Pydantic, validators, registry, pure functions, static lints |
| **Integration** | `tests/integration/` | Real Postgres 15 + Inngest dev server (Docker) | every PR (`ci-fast`) | Graph / service / persistence; API boundaries; harness round-trips |
| **E2E smoke** | `tests/e2e/` | Full Docker stack + **real E2B** + dashboard + Playwright | every PR (`e2e-benchmarks` matrix) | Cross-service + cross-process + UI truth; sandbox provisioning at volume; cohort-parallel scheduling |
| **Real-LLM** | `tests/real_llm/` | As e2e + real model calls, budget-gated | on demand + nightly | Non-deterministic model behaviour |

**`tests/state/` is retired.** Pure files moved to `tests/unit/state/`. Graph/service files migrate to `tests/integration/`. Migration status is tracked in [`06-phases.md`](06-phases.md).

**Decision rule.** Pure function / validator / pydantic model / registry key → unit. Exercises graph, persistence, or HTTP boundary → integration. Needs sandbox + dashboard + UI → e2e. Needs LLM → real-llm.

---

## 3. Canonical smoke program — invariants

### 3.1 Shape — immutable 9-leaf DAG

Every per-env smoke run produces **exactly** this graph, enforced by `SmokeWorkerBase.execute()` via `@final`. Subclasses supply only the leaf slug; topology is unmodifiable.

```
Diamond (4):           Line (3):               Singletons (2):
    d_root             l_1 → l_2 → l_3             s_a     s_b
   ↙      ↘
d_left   d_right
   ↘      ↙
    d_join
```

```python
EXPECTED_SUBTASK_SLUGS = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)
```

Exported once; imported by `SmokeWorkerBase`, `SmokeCriterionBase`, every pytest driver, every Playwright spec. Changing the tuple is the only way to change topology.

**Invariants each shape proves:** diamond → fan-out + fan-in + two-parent deps; line → strict sequential cascade; singletons → multi-terminal leaves + `wait_all` termination.

### 3.2 Cohort-parallel submission

Each matrix leg submits **3 runs of its benchmark's smoke worker as one cohort**. Proves cohort parallelism and concurrent workflow submission at volume on top of graph-propagation invariants. **The researchrubrics leg replaces its third cohort slot with a sad-path run** that uses `ResearchRubricsSadPathSmokeWorker`; the line-cascade failure invariants are exercised here, without adding a 10th top-level run.

| Leg | Slot 1 | Slot 2 | Slot 3 |
|---|---|---|---|
| `researchrubrics` | happy | happy | **sad** — `l_2` deterministic FAIL |
| `minif2f` | happy | happy | happy |
| `swebench-verified` | happy | happy | happy |

Per PR: 3 matrix legs × 3 cohort-parallel runs = **9 top-level runs**. Sandbox acquisitions: 8 happy runs × 9 leaves + 1 sad run × 8 leaves (`l_3` never provisioned because its dep failed) = **80 E2B leaf sandbox acquisitions**.

Per leg: 26 or 27 leaf sandbox acquisitions on that env's image. No shared smoke sandbox image.

If E2B cost becomes an issue, step down to 1 run per leg (9 sandboxes/PR total); the researchrubrics sad slot stays, minif2f and swebench-verified collapse to 1 happy run each. Do **not** reduce leaf count.

### 3.3 Registry surface — 9 entries, test-only

Nine rows, all under `tests/e2e/_fixtures/`, none in `ergon_builtins`. Code sketches in [`01-fixtures.md`](01-fixtures.md).

| Slug | Kind |
|---|---|
| `{env}-smoke-worker` × 3 | Worker (parent) |
| `{env}-smoke-leaf` × 3 | Worker (leaf) |
| `{env}-smoke-criterion` × 3 | Criterion |

`{env} ∈ {researchrubrics, minif2f, swebench}`. Shared base classes (`SmokeWorkerBase`, `BaseSmokeLeafWorker`, `SmokeSubworker` Protocol, `SmokeCriterionBase`) are **not registered** — composed via inheritance.

### 3.4 Test stubs out of `ergon_builtins`

`ergon_builtins/` contains **only production baselines**. All smoke infrastructure moves or gets deleted (see [`05-deletions.md`](05-deletions.md) for the manifest).

Test-only discovery: `tests/e2e/_fixtures/__init__.py` registers via import side-effect. The e2e pytest session imports it at session start. Production CLI paths do not import `tests/`; builtins stays clean.

---

## 4. Budgets

| Measure | Value |
|---|---|
| Per matrix leg | 10-min job timeout; 5-min pytest timeout (hard ceiling) |
| Leaf-subtask sandbox acquisitions per leg | happy legs: 3 runs × 9 leaves = **27**; researchrubrics leg: 2×9 + 1×8 = **26** (sad slot skips `l_3`) |
| Leaf-subtask sandbox acquisitions per PR | (minif2f 27) + (swebench 27) + (researchrubrics 26) = **80** across 3 images |
| Parent-task sandbox per run | 1 (used by parent worker + attached to by the criterion per `sandbox-lifetime-covers-criteria` RFC). Not additional at evaluation time. |
| Sad-path residency | Folded into researchrubrics cohort slot 3 — **zero additional top-level runs**. |
| Parallel workflow runs per PR | **9** (3 legs × 3-run cohort) |
| Warm wall-clock per leg | 1–3 min (post-Docker cache) |
| Cold wall-clock per leg | up to 5 min |

E2B API key is required on every PR — acceptable for private-repo phase; revisit before open-source.

---

## 5. Acceptance gate (merge checklist)

- [ ] All 3 `e2e-benchmarks` matrix legs green on the PR. (Researchrubrics leg contains 2 happy + 1 sad-path cohort runs; all must be green.)
- [ ] `ci-fast` unit + integration green.
- [ ] No `ergon_builtins/**` file contains `stub` or `smoke` in its name (case-insensitive), **except** the production-baseline exception list: `workers/baselines/training_stub_worker.py` (synthetic-trajectory RL baseline per accepted RFC `2026-04-22-worker-interface-and-artifact-routing`). Anything else that still matches is a miss.
- [ ] Registry contains no `canonical-smoke`, `smoke-test`, or generic `smoke-leaf` slug.
- [ ] Production `pnpm build` of dashboard does not bundle `/api/test/*` routes (harness-mount-gate test enforces).
- [ ] No LLM references on the smoke path: grep `OPENROUTER`, `anthropic`, `openai`, `pydantic_ai` in `tests/e2e/` → zero.
- [ ] Screenshots land on `screenshots/pr-{N}` and PR comment renders inline images.
- [ ] Docker layer cache in effect (cold leg < 5 min; warm < 3 min).
- [ ] Per-run assertions green on every run: graph, resources, turn counts, sandbox command WAL, sandbox lifecycle events, thread messages (9 happy / 8 sad), blob round-trip, temporal ordering, evaluation, env content.
- [ ] Cohort membership assertion green for each matrix leg (3 runs visible on `/cohort/{key}` via harness DTO).
- [ ] Sad-path assertions green: graph cascade (l_1 COMPLETED, l_2 FAILED, l_3 BLOCKED/CANCELLED; diamond + singletons COMPLETED), partial artifact persisted as `RunResource`, pre-fail `wc -l` WAL entry persisted, completion-message suppression (8 msgs on `smoke-completion` thread, `l_2` missing), evaluation score=0.0 with `l_2` named in feedback.
- [ ] `docs/architecture/07_testing.md` points at this folder; all superseded RFCs/plans listed in [`05-deletions.md`](05-deletions.md) have been removed in the same PR.

---

## 6. Open decisions to pin

1. **Training-stub residency — RESOLVED: keep in `ergon_builtins/workers/baselines/`.** `TrainingStubWorker` is a production baseline: RL operators invoke it (`ergon benchmark run smoke-test --worker training-stub`) to exercise the trajectory-extraction pipeline without spending on a real model. Accepted RFC [`2026-04-22-worker-interface-and-artifact-routing.md`](../../../rfcs/accepted/2026-04-22-worker-interface-and-artifact-routing.md) already treats it as a first-class baseline alongside `ReActWorker` and `ManagerResearcherWorker`; the "stub" in its name is a technical term (synthetic trajectories / fake logprobs), not "test fixture." This refactor does **not** touch the file. Renaming it to drop "stub" is an optional follow-up, not blocking.
2. **Cohort size.** Default **3** per leg (81/PR). Step down to 1/leg (27/PR) if E2B cost is unacceptable.
3. **Dashboard fidelity vs speed.** Default prod build (`pnpm build && start`); dev-server fallback if 5-min budget blown.
4. **Existing Next.js `/api/test/dashboard/*` routes.** Keep as-is, consolidate into backend `/api/test/*`, or remove? Covered in [`03-dashboard-and-playwright.md §4`](03-dashboard-and-playwright.md).
5. **Harness test-secret rotation.** `TEST_HARNESS_SECRET` read from env; CI passes a random per-run value. Document mechanism in [`03-dashboard-and-playwright.md §2`](03-dashboard-and-playwright.md).

---

## 7. Changelog

| Date | Change |
|---|---|
| 2026-04-23 | Initial single-plan draft. |
| 2026-04-23 (rev 1) | Drop `canonical-smoke` slug + `smoke-test` benchmark. Smoke is per-env self-contained. 9 registry rows. |
| 2026-04-23 (rev 2) | Split into folder `test-refactor/`. This file becomes the "program" entry; technical detail moves to `01-` through `06-`. |
