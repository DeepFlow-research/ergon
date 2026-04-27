---
status: active
opened: 2026-04-27
author: GPT-5.5
architecture_refs:
  - docs/architecture/07_testing.md
  - docs/architecture/02_runtime_lifecycle.md
  - docs/architecture/04_persistence.md
supersedes: []
superseded_by: null
---

# RFC: Test Brittleness And Confidence Gaps

## Problem

Behavior-preserving refactors need trustworthy tests. Ergon already has useful
unit, integration, e2e, state, and real-LLM tiers, but the test surface has
grown alongside the code. Some tests encode current implementation details,
some test-support concepts leak toward runtime code, and some important
package-boundary expectations are not yet expressed as contracts.

The goal is to make tests better at preserving behavior while reducing their
ability to freeze accidental architecture.

## Current findings

### Test support has explicit gates, but the boundary is fragile

Smoke fixtures and test harness paths are mostly gated behind environment
flags such as `ENABLE_TEST_HARNESS` and `ENABLE_SMOKE_FIXTURES`. This is
useful, but it means import discipline matters. A small number of direct
imports can turn test-only composition into runtime coupling.

### Existing architecture tests are valuable but narrow

There are tests that assert smoke fixtures do not move into old production
paths. That pattern should expand: import-boundary rules should cover core to
builtins, builtins to CLI, and core to CLI exceptions.

### State tests exercise behavior but may mix concerns

The `tests/unit/state` tier appears to group workflow/tool/research-rubric
state behavior rather than a dedicated state package. These tests are useful,
but they should make clear whether they are verifying public behavior, database
state transitions, or current helper implementation.

### Real-LLM and e2e tests are opt-in

Opt-in real-LLM rollout tests and dashboard/e2e tests are valuable for catching
integration failures, but they are not always part of the fast feedback loop.
The refactor program needs a smaller characterization layer for behavior that
must not change during architecture cleanup.

### Fixtures can hide missing contracts

When tests rely on broad fixtures or sentinel identities, they can keep passing
even though production composition boundaries are unclear. Refactors should
prefer explicit fake providers and public-contract setup over reaching into
runtime internals.

## Target shape

The test suite should have a clear contract for each tier:

- **Architecture tests** enforce import direction, package ownership, and
  allowed exceptions.
- **Unit tests** verify pure behavior and service logic without requiring the
  default builtins registry unless that is the unit under test.
- **State/integration tests** verify persisted runtime transitions through
  public service boundaries.
- **E2E tests** verify deployed surfaces and dashboard/API hydration.
- **Real-LLM tests** verify representative model-facing workflows and artifact
  health, gated by explicit credentials.

Each behavior-preserving refactor should start by identifying which tier locks
the behavior being preserved.

## Standards proposed

- Add architecture tests for dependency direction and allowed import
  exceptions. Exceptions should be named and justified in one place.
- Prefer fake implementations of public protocols over sentinel strings that
  runtime code must recognize.
- Keep smoke fixtures and real-LLM harnesses under test-support or tests, with
  explicit opt-in registration.
- Avoid tests that assert line-by-line implementation detail unless the detail
  is itself a contract.
- For every major refactor, add or identify characterization tests before
  moving code.
- Keep slow/e2e/real-LLM tests useful but non-blocking for local refactor
  loops; provide smaller contract tests for behavior that must always pass.

## Candidate fixes

Each candidate below should include enough detail for an implementation plan to
be written without rediscovering the audit. Tests are themselves part of the
architecture here: they define what future refactors are not allowed to break.

### TB-1: Add import-boundary architecture tests

**Issue fixed:** Package-boundary rules are currently mostly social
conventions, so new reverse imports or ad hoc slug branches can land without a
fast test failure.

Create tests that parse imports and enforce the intended package graph. Start
with warnings/allowlists for current known violations, then tighten the rules
as dependency-inversion fixes land.

Initial rules:

- `ergon_core.core.runtime` should not import `ergon_builtins`.
- `ergon_core` should not import `ergon_cli` except explicitly allowed
  test-harness paths.
- `ergon_builtins` should not import `ergon_cli.commands`.
- Production runtime modules should not import `ergon_core.test_support` or
  `tests.*`.

Candidate location: `tests/unit/architecture/test_package_boundaries.py`.

Suggested helper shape:

```python
def assert_no_imports(package_root: Path, forbidden: str, *, allowlist: set[str]) -> None:
    offenders = scan_python_imports(package_root, forbidden)
    unexpected = offenders - allowlist
    assert unexpected == set()
```

Initial allowlist should include only named, reviewed exceptions. Avoid broad
directory-level exceptions unless the whole directory is intentionally an
adapter or test-support surface.

Steps:

- [ ] Implement a small AST-based import scanner, not a regex-only test.
- [ ] Add rules for core-to-builtins, core-to-cli, builtins-to-cli, and
      production-to-test-support.
- [ ] Encode current known violations as explicit allowlist entries with a
      linked candidate fix ID.
- [ ] Add a second test that fails on new concrete worker/benchmark slug
      branches in generic composition modules.
- [ ] Document how to update the allowlist when a refactor removes a violation.

Verification:

- Test fails with a clear list of violating import edges.
- Current exceptions are named in one allowlist with comments.

Acceptance gate:

- [ ] Architecture test passes with only reviewed exceptions.
- [ ] Adding `from ergon_cli.commands...` to a builtin tool fails the test.
- [ ] Adding `worker_slug == "some-example"` to generic composition fails or is
      caught by the branch-pattern test.

### TB-2: Add CLI benchmark-run characterization tests

**Issue fixed:** The benchmark-run path combines DB setup, experiment
composition, persistence, cohort creation, run creation, event dispatch, and
polling. Refactoring it without characterization tests risks changing behavior
while only moving imports around.

Before changing composition or registry resolution, lock down the current
observable `ergon benchmark run` setup path without requiring a live Inngest
run:

- `ensure_db()` is called before persistence.
- `build_experiment()` receives CLI args unchanged.
- `experiment.validate()` runs before `experiment.persist()`.
- cohort resolution uses the explicit cohort or benchmark slug.
- `create_run()` receives the persisted definition.
- `WorkflowStartedEvent` carries the run ID and definition ID.
- polling reads `RunRecord` until a terminal status.

Candidate location: `tests/unit/cli/test_benchmark_run_flow.py`.

Suggested cases:

- `benchmark run` persists before dispatching.
- explicit `--cohort` is used when present.
- default cohort name falls back to benchmark slug.
- timeout returns a timeout handle without pretending the run completed.
- terminal failed/cancelled status exits non-zero.

Test approach:

- Monkeypatch `ensure_db`, `build_experiment`, `experiment_cohort_service`,
  `create_run`, `inngest_client.send`, and `get_session`.
- Use a fake session whose `get(RunRecord, run.id)` returns a sequence of
  statuses.
- Avoid real Postgres, real Inngest, and real builtins imports unless the test
  is explicitly about registry wiring.

Verification:

- Tests use fakes/mocks at service boundaries, not real Postgres or real
  Inngest.
- Refactors of composition/import paths keep this test green.

Acceptance gate:

- [ ] A future rewrite of `run_benchmark` can move code around but cannot skip
      validate, persist, run creation, event dispatch, or terminal polling.
- [ ] The test names describe user-visible behavior, not private helper calls.

### TB-3: Add registry protocol contract tests

**Issue fixed:** Once registry lookup becomes injectable, there is no shared
contract proving that the builtins adapter and test fakes behave the same way.

Once a registry/resolver protocol exists, test it independently from CLI and
runtime orchestration:

- known worker/benchmark/evaluator slugs resolve;
- unknown slugs produce a typed error or clear `KeyError`;
- optional install hints remain available;
- model backend registration side effects still happen exactly once.

Candidate location: `tests/unit/runtime/test_runtime_registry_contract.py` or
`tests/unit/api/test_registry_contract.py`, depending on ownership.

Verification:

- Same contract runs against the builtins-backed registry adapter and a small
  fake registry used by tests.

Files:

- Test: `tests/unit/runtime/test_runtime_registry_contract.py`.
- Fixture/helper: a fake registry implementation near the test or under
  `ergon_core.test_support`.
- Optional test: `tests/unit/architecture/test_registry_imports.py`.

Steps:

- [ ] Write the contract tests against a fixture parameter named `registry`.
- [ ] Run the same tests against the builtins adapter and fake registry.
- [ ] Assert missing-slug behavior explicitly.
- [ ] Assert install hints do not require importing data-heavy optional extras.
- [ ] Assert model backend registration remains idempotent.

Acceptance gate:

- [ ] Runtime services can be tested with fake registries.
- [ ] Builtins adapter passes the same contract as the fake implementation.
- [ ] Contract tests fail if a registry lookup imports CLI code.

### TB-4: Reclassify `tests/unit/state` by contract type

**Issue fixed:** The `state` test tier mixes workflow commands, persisted
runtime transitions, worker/tool behavior, benchmark composition, and fixture
behavior under one vague label.

Add comments, module names, or a README that explains what the "state" tier
means. Then split or rename tests where the current grouping hides intent.

Suggested categories:

- workflow command behavior;
- persisted graph/task state transitions;
- worker/tool state interaction;
- research-rubrics benchmark/worker composition;
- fixture-only behavior.

Verification:

- A reader can tell why each state test exists without knowing the historical
  branch that introduced it.
- No test loses coverage during renaming or movement.

Files:

- Add: `tests/unit/state/README.md` or rename/split tests into clearer
  directories.
- Review:
  `tests/unit/state/test_research_rubrics_workers.py`.
- Review:
  `tests/unit/state/test_research_rubrics_benchmark.py`.
- Review workflow/tool state tests in the same directory.

Steps:

- [ ] Inventory each state test file and classify it as workflow command,
      persisted graph/task transition, worker/tool behavior, benchmark
      composition, or fixture behavior.
- [ ] Rename files only when the existing name hides the contract.
- [ ] Move fixture-only behavior under a fixture/test-support category if it is
      not testing runtime state.
- [ ] Add README language that "state" is a test tier, not a production domain
      package.

Acceptance gate:

- [ ] Every file in `tests/unit/state` has an obvious contract category.
- [ ] No test import path changes require production code changes.

### TB-5: Add fast artifact-health tests for real-LLM assumptions

**Issue fixed:** Some real-LLM artifact assumptions are only checked in opt-in
credentialed paths, so artifact schema or parser regressions can slip past the
fast local suite.

The real-LLM artifact-health harness is opt-in, but some assumptions should be
validated without credentials:

- rollout artifact directories are named and shaped consistently;
- required metadata fields are present;
- failed/incomplete runs produce diagnosable artifacts;
- fixture artifacts exercise the same reader/parser used by real runs.

Candidate location: extend
`tests/unit/runtime/test_real_llm_rollout_artifact_health.py` or split a helper
contract test nearby.

Verification:

- Fast tests run without `ERGON_REAL_LLM`.
- Real-LLM tests remain opt-in but rely on the same artifact validation helper.

Files:

- Review/extend:
  `tests/unit/runtime/test_real_llm_rollout_artifact_health.py`.
- Review:
  `tests/real_llm/artifact_health.py`.
- Review:
  `tests/real_llm/rollout.py`.

Required cases:

- artifact directory with complete healthy rollout passes;
- missing required metadata fails with actionable error;
- partial failed rollout still produces enough diagnostic fields;
- worker slug extraction handles both snake_case and camelCase shapes;
- fixture artifact parser is the same parser used by real-LLM checks.

Acceptance gate:

- [ ] Unit artifact-health tests pass without network credentials.
- [ ] Real-LLM path delegates to the same validation helper.
- [ ] Failure messages name the missing artifact or field.

### TB-6: Replace sentinel-aware runtime tests with fake provider tests

**Issue fixed:** Tests that rely on stub sandbox IDs or sentinel parsing
encourage production runtime code to understand test/provider implementation
details.

Where runtime tests currently require stub or sentinel sandbox identities,
introduce fake provider implementations that satisfy public provider protocols.
The runtime should observe provider behavior, not parse provider-specific
sentinel strings.

Verification:

- Tests still cover skipped, failed, cancelled, and cleanup paths.
- Production runtime modules no longer need helpers such as
  `is_stub_sandbox_id`.

Files:

- Review tests touching sandbox cleanup, cancellation, skipped tasks, and
  propagation.
- Add fake provider helpers under `ergon_core/ergon_core/test_support/` only if
  they are reusable across test tiers.
- Pair with code cleanup in `core/providers/sandbox/manager.py` only after
  characterization tests exist.

Steps:

- [ ] Inventory tests that assert or construct stub sandbox IDs.
- [ ] Define fake provider behavior in terms of public provider methods:
      create, reconnect, terminate, publish resources.
- [ ] Replace tests that expect sentinel parsing with tests that assert provider
      method calls and runtime state transitions.
- [ ] Add an architecture test blocking runtime imports of
      `is_stub_sandbox_id`.

Acceptance gate:

- [ ] Runtime behavior for skipped/failed/cancelled cleanup is still covered.
- [ ] Runtime code no longer branches on provider-specific sentinel strings.
- [ ] Test fakes live under test support, not production provider modules.

## Phase gates for the test stream

### Phase T1 — Boundary tests first

Scope:

- `tests/unit/architecture/test_package_boundaries.py`.
- Allowlist current violations with links to `DI-*` / `CQ-*`.

Acceptance:

- [ ] Boundary tests pass and fail when a deliberate forbidden import is added
      locally.

### Phase T2 — Characterization before refactor

Scope:

- CLI benchmark-run characterization.
- Registry contract tests.
- Artifact-health fast contracts.

Acceptance:

- [ ] Refactor candidates have tests that describe the behavior they preserve.
- [ ] No new test requires real Postgres, real Inngest, or real LLM credentials.

### Phase T3 — Ratchet allowlists down

Scope:

- After dependency-inversion and code-quality refactors land, remove resolved
  allowlist entries.

Acceptance:

- [ ] Import-boundary allowlist shrinks over time.
- [ ] New exceptions require an RFC or explicit architecture-doc note.

## Migration / risk

The main risk is over-constraining architecture too early. The first pass
should allow existing known exceptions with comments, then ratchet them down as
refactors land.

The second risk is test churn without confidence gain. New tests should be
written around observable behavior and import contracts, not around temporary
helper names introduced during the refactor.

## Open questions

- Should architecture tests live under `tests/unit/architecture`, or should
  there be a dedicated `tests/architecture` tier?
- Which tests should be required before accepting dependency-inversion work?
- Should real-LLM artifact-health checks define a small golden contract that
  can run without external model credentials?
