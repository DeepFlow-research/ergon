# 05 — Deletion manifest

**Status:** draft
**Scope:** every file, registration, and doc that must be removed in the same PR as the new code. Nothing listed here survives the landing PR.

**Phase ordering:** deletions in this doc are tagged to Phase F in [`06-phases.md`](06-phases.md). Don't delete until the new code is green — a PR that breaks both old and new simultaneously is unreviewable.

---

## 1. `ergon_builtins/` deletions

### 1.1 Benchmark stubs (delete outright)

- `ergon_builtins/benchmarks/smoke_test/` — whole directory.
- `ergon_builtins/benchmarks/researchrubrics/smoke.py`
- `ergon_builtins/benchmarks/researchrubrics/smoke_rubric.py`
- `ergon_builtins/benchmarks/minif2f/smoke_rubric.py`
- `ergon_builtins/benchmarks/swebench_verified/smoke_rubric.py`

### 1.2 Stub workers (delete outright)

- `ergon_builtins/workers/stubs/canonical_smoke_worker.py` — retired slug.
- `ergon_builtins/workers/baselines/stub_worker.py`
- ~~`ergon_builtins/workers/baselines/training_stub_worker.py`~~ — **KEPT.** Production baseline per accepted RFC `2026-04-22-worker-interface-and-artifact-routing`. See §6 for rationale.
- `ergon_builtins/workers/research_rubrics/stub_worker.py`

### 1.3 Stub workers (move then delete)

- `ergon_builtins/workers/stubs/base_smoke_leaf.py` → `tests/e2e/_fixtures/smoke_base/leaf_base.py`.
- `ergon_builtins/workers/stubs/smoke_subworker.py` → `tests/e2e/_fixtures/smoke_base/subworker.py`.
- `ergon_builtins/workers/stubs/` — delete the whole directory once the two files above are moved.

### 1.4 Stub criteria (delete outright)

- `ergon_builtins/evaluators/criteria/stub_criterion.py`
- `ergon_builtins/evaluators/criteria/stub_report_exists.py`
- `ergon_builtins/evaluators/criteria/varied_stub_criterion.py`

### 1.5 Shared smoke criterion (move then delete)

- `ergon_builtins/evaluators/criteria/smoke_criterion.py` → `tests/e2e/_fixtures/smoke_base/criterion_base.py` (as `SmokeCriterionBase`; env subclasses move to `tests/e2e/_fixtures/criteria/{env}_smoke.py`, see [`01-fixtures.md §3`](01-fixtures.md)).

### 1.6 Stub rubrics (delete outright)

- `ergon_builtins/evaluators/rubrics/stub_rubric.py`
- `ergon_builtins/evaluators/rubrics/varied_stub_rubric.py`

### 1.7 Builtins `__init__` imports

Scrub every `__init__.py` under `ergon_builtins/` that re-exports the above. Missed re-exports cause import-time failures in CI post-deletion — treat this as part of the PR checklist, not a cleanup for later.

---

## 2. Registry rows to expunge

After registration hook runs in `tests/e2e/_fixtures/__init__.py`, the process-level registry must **not** contain any of these slugs:

| Slug | Kind |
|---|---|
| `canonical-smoke` | Worker |
| `smoke-leaf` (generic) | Worker |
| `smoke-test` | Benchmark |
| `researchrubrics-smoke` | Benchmark |
| `stub-worker` | Worker |
| ~~`training-stub-worker`~~ | — (kept: production baseline, see §1.2) |
| `researchrubrics-stub` | Worker |
| `stub-criterion` | Criterion |
| `varied-stub-criterion` | Criterion |
| `stub-report-exists` | Criterion |
| `stub-rubric` | Rubric |
| `varied-stub-rubric` | Rubric |

Unit test in [`01-fixtures.md §6`](01-fixtures.md) (`test_registry_smoke_entries.py`) asserts the **present** set exactly; any leftover slug fails the test.

---

## 3. `tests/` deletions

### 3.1 Old e2e tests (confirm existence, delete)

- `tests/e2e/test_benchmarks_stubbed.py` (pycache implies it existed)
- `tests/e2e/test_researchrubrics_smoke_e2b.py` (pycache implies it existed)
- Any other `tests/e2e/test_*.py` not in {`test_researchrubrics_smoke.py`, `test_minif2f_smoke.py`, `test_swebench_smoke.py`}

### 3.2 `tests/state/` — fully retired

`tests/state/` was the SQLite-backed fast tier; migration to `tests/unit/state/` + `tests/integration/` is already underway. Confirm migration complete and delete:

- `tests/state/` — whole directory, including `conftest.py`, `factories.py`, `mocks.py`, and every `test_*.py` not yet moved.

If anything still lives in `tests/state/` at PR-land time, classify per [`00-program.md §2`](00-program.md) decision rule and migrate in this same PR.

### 3.3 Integration tier SQLite holdovers (audit, migrate, delete)

- `tests/integration/test_full_lifecycle.py`
- `tests/integration/test_full_lifecycle_with_eval.py`

These currently use SQLite + direct service calls per the old `testing-posture-reset` RFC. Rewrite against real Postgres + Inngest **or** delete; they must not survive as SQLite-backed tests post-landing.

---

## 4. Docs to delete (plans + RFCs)

All under `docs/` in the Ergon repo.

### 4.1 Accepted RFCs (superseded by this folder)

- `docs/rfcs/accepted/2026-04-18-testing-posture-reset.md`
- `docs/rfcs/accepted/2026-04-21-e2e-smoke-coverage-rewrite.md`

### 4.2 Rejected RFCs (already dead, housekeep)

- `docs/rfcs/rejected/2026-04-18-test-harness-endpoints.md`
- `docs/rfcs/rejected/2026-04-18-fixed-delegation-stub-worker.md`

### 4.3 Superseded plans

- `docs/superpowers/plans/2026-04-21-e2e-smoke-coverage-rewrite.md`
- `docs/superpowers/plans/2026-04-22-phase-2-canonical-smoke-spec.md`
- `docs/superpowers/plans/2026-04-22-unified-testing-e2e-smoke-plan.md`

### 4.4 Brainstorms to audit

- `docs/superpowers/brainstorms/2026-04-21-real-llm-debug-harness.md` — keep only if the real-LLM plan at `docs/superpowers/plans/2026-04-21-real-llm-debug-harness.md` references it. Otherwise delete.

### 4.5 NOT deleted (out of scope)

- `docs/rfcs/accepted/2026-04-21-real-llm-debug-harness.md`
- `docs/superpowers/plans/2026-04-21-real-llm-debug-harness.md`

Real-LLM is a separate tier — it has its own design authority and is not restructured by this refactor.

### 4.6 This folder itself

After the rebuild lands and `docs/architecture/07_testing.md` fully describes the standing system:

- Delete `docs/superpowers/plans/test-refactor/`.

Planning docs are not documentation. Leaving them around after landing creates the same fragmentation we just cleaned up.

---

## 5. Architecture docs — updated, not deleted

These get edits, not deletions:

- `docs/architecture/07_testing.md` — rewritten to describe the 4 tiers, canonical-smoke-shape-enforced-by-inheritance, `/api/test/*` contract, screenshot flow. Post-landing, `07_testing.md` is the documentation; this folder is the planning trail.
- `docs/architecture/06_builtins.md` — remove any mention of stubs/smoke that contradicts §1. Add pointer to `tests/e2e/_fixtures/` for test-only registry entries.
- `docs/architecture/05_dashboard.md` — add `/api/test/*` route contract summary + `data-testid` contract.
- `docs/architecture/01_public_api.md` — no change expected (Worker/Criterion ABCs unchanged).

---

## 6. Training-stub audit — RESOLVED (2026-04-23)

Audit run with `grep -Rn "training-stub\|training_stub\|TrainingStubWorker" ergon_core/ ergon_cli/ ergon_infra/ ergon_builtins/` surfaced:

- **`ergon_builtins/registry_core.py`** registers `"training-stub": TrainingStubWorker` — production registry entry.
- **`ergon_builtins/AGENTS.md`** documents it as the RL-logprobs fixture operators invoke via `ergon benchmark run smoke-test --worker training-stub`.
- **Accepted RFC [`2026-04-22-worker-interface-and-artifact-routing.md`](../../../rfcs/accepted/2026-04-22-worker-interface-and-artifact-routing.md)** treats `TrainingStubWorker` as a first-class baseline alongside `ReActWorker`, `ManagerResearcherWorker`, `StubWorker`, and migrates it through the worker-interface refactor.

**Outcome:** keep `training_stub_worker.py` in `ergon_builtins/workers/baselines/` untouched. The "stub" in its name is a technical term (synthetic trajectory / fake logprobs), not "test fixture." Renaming is an optional follow-up, not blocking this refactor.

The merge checklist in `00-program.md §5` carries this exception explicitly.

---

## 7. Code-path follow-ups

Things that are not strict deletions but must not break post-PR:

- `ergon_cli/` subcommands that default to `stub-worker` — update defaults to a real baseline or remove the subcommand.
- `ergon_infra/` config templates that pre-populate `stub-*` slugs — update or remove.
- `docker-compose.ci.yml` comments referencing `smoke-test` benchmark — update.
- Any `README.md` or `ONBOARDING.md` walking through `stub-*` usage — rewrite with real baselines.

Run `git grep -n 'stub\|canonical-smoke\|smoke-test'` pre-commit; each surviving match is either (a) intentionally in `tests/e2e/_fixtures/`, (b) the preserved `training_stub_worker.py` production baseline (§6), or (c) a miss to fix.

---

## 8. One-shot verification command

Before marking the PR ready:

```bash
# Should return zero:
rg -n 'canonical-smoke|smoke-test|ResearchRubricsSmokeTestBenchmark' \
  ergon_core/ ergon_cli/ ergon_builtins/ ergon_infra/ ergon-dashboard/src

# Should return only tests/e2e/_fixtures/:
rg -l 'SmokeWorkerBase|SmokeSubworker|BaseSmokeLeafWorker|SmokeCriterionBase' \
  | grep -v '^tests/e2e/_fixtures/'

# Training-stub baseline is ALLOWED to remain in ergon_builtins (see §6).
# This command should return exactly ONE match — the baseline itself:
rg -l 'TrainingStubWorker' ergon_builtins/ | head
```

Both should be empty outputs. If not, the deletion pass is incomplete.
