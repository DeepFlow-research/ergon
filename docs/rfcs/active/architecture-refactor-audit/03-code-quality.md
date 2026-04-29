---
status: active
opened: 2026-04-27
author: GPT-5.5
architecture_refs:
  - docs/architecture/README.md
  - docs/architecture/01_public_api.md
  - docs/architecture/02_runtime_lifecycle.md
  - docs/architecture/06_builtins.md
supersedes: []
superseded_by: null
---

# RFC: Code Quality, Duplication, And Complexity

## Problem

Fast iteration has left parts of Ergon with high-complexity functions,
branch-heavy example paths, duplicated orchestration logic, and names that no
longer communicate precise ownership. The project already uses Ruff, ty,
slopcop, xenon, and radon-related tooling, but current configuration mostly
documents pre-existing debt rather than defining a refactor target.

This audit defines the code-quality lens for behavior-preserving cleanup.

## Current findings

### Known complexity debt is already listed

The root `pyproject.toml` has explicit complexity ignores for files such as
experiment persistence, experiment validation, RL rollout/extraction, MiniF2F
loading, file evidence collection, transformer message formatting, and scripts.
Those comments are useful because they identify areas where orchestration has
grown large enough to need ownership review.

### Generic paths contain example-specific branches

`ergon_cli.composition.build_experiment` has special branches for smoke workers
and `researchrubrics-workflow-cli-react`. These branches preserve necessary
behavior today, but the pattern does not scale. Generic composition code should
not need to know every benchmark or worker family that requires extra bindings.

### Tool and workflow code can duplicate service behavior

CLI command modules, builtin tools, and runtime services all touch workflow
semantics. Without a shared application service boundary, the same concept can
be parsed, validated, or executed in multiple places.

### Names sometimes encode historical implementation

Names such as "stub" can mean test double, development default, or lightweight
implementation depending on context. Ambiguous names make it harder to enforce
production/test boundaries and public/private API rules.

### Deep nesting often reflects missing concepts

When functions perform lookup, construction, validation, persistence, event
dispatch, and rendering in one flow, nesting and branch count increase. The
answer is not mechanical extraction; it is naming the concepts that already
exist and moving them to the owner that can enforce their invariants.

## Target shape

Code quality should be judged against architecture, not only metrics:

- A module should have one clear owner and one reason to change.
- Public APIs should describe stable concepts, not current storage or CLI
  mechanics.
- Composition should be declarative where possible and isolated where it must
  branch.
- Runtime orchestration should read as a sequence of named domain operations.
- Tests should cover behavior before complexity-reducing rewrites.

## Standards proposed

- Treat new high-complexity ignores as design review triggers, not routine
  lint suppressions.
- Prefer small domain objects or command/result types when a function is
  passing many loosely related parameters across package boundaries.
- Keep branch-heavy compatibility paths local to adapters or composition
  modules, not inside core runtime services.
- Deduplicate only after confirming the duplicated code represents the same
  concept. Similar code in different domains may deserve different names.
- Rename "stub", "smoke", and "test" concepts when they are production
  defaults or examples rather than test doubles.
- Use architecture docs to record anti-patterns and accepted exceptions so
  refactors do not rely on tribal memory.

## Candidate fixes

Each candidate below should be concrete enough to become a scoped PR or a
section in an implementation plan. The intent is not generic "clean code"; the
intent is to find where the project encoded missing domain concepts as
duplicated services, private helpers, slug branches, or lint suppressions.

### CQ-1: Create a complexity ledger from current ignores

**Issue fixed:** Complexity suppressions are documented inline in
`pyproject.toml`, but there is no owner, smell classification, priority, or
exit criterion for paying the debt down.

Turn the existing `pyproject.toml` complexity-ignore comments into an explicit
ledger that ranks each offender by risk, ownership, and likely refactor path.

Initial entries should include:

- `ExperimentPersistenceService.persist_definition`
- `Experiment.validate`
- RL rollout/extraction helpers
- MiniF2F problem loading
- file evidence collection
- transformer message formatting
- standalone scripts ignored for CLI/script reasons

Candidate output: a section in this RFC, or a separate
`complexity-ledger.md` in this folder if the list gets long.

Verification:

- Every current C901 ignore has an owner, reason, and intended disposition:
  keep, split, move, rename, or delete.
- New C901 ignores require adding an entry to the ledger.

Ledger fields:

```markdown
| Item | File | Current reason | Domain owner | Smell | Candidate fix | Gate |
|---|---|---|---|---|---|---|
```

Smell taxonomy:

- orchestration doing persistence work;
- validation rules hidden in one large method;
- example-specific branch in generic path;
- private helper cluster that wants a domain object;
- duplicate service responsibility;
- optional dependency/test fallback mixed into production flow.

Steps:

- [ ] Convert each current C901 ignore into a ledger row.
- [ ] Run `rg "^def _|^    def _|class .*Service" ergon_core/ergon_core/core/runtime/services`
      and add obvious private-helper clusters to the ledger even if not C901.
- [ ] Rank rows by "blocks dependency inversion", "blocks test confidence",
      and "local cleanup only".
- [ ] Add a policy that any new C901 ignore must cite a ledger row or RFC.

Acceptance gate:

- [ ] The ledger exists and covers every current complexity ignore.
- [ ] The ledger includes at least the large service/private-helper clusters in
      `task_management_service.py`, `workflow_service.py`,
      `graph_repository.py`, `task_execution_service.py`, and
      `experiment_persistence_service.py`.

### CQ-2: Split experiment composition into generic pipeline plus descriptors

**Issue fixed:** Generic experiment composition currently knows about concrete
worker families and fixture behavior, which turns every special example into a
potential new branch in shared CLI code.

Refactor `ergon_cli.composition.build_experiment` so the generic path performs
only these steps:

1. load registry;
2. construct benchmark/evaluator;
3. ask the selected benchmark/worker for any composition descriptor;
4. build the `Experiment` from descriptors and defaults.

Current smoke and research-rubrics branches become descriptor providers. This
preserves behavior but removes the pattern where each special worker adds a new
generic CLI branch.

Verification:

- Existing smoke and research-rubrics composition tests pass.
- A new fake descriptor test proves a worker can request extra bindings without
  changing `build_experiment`.

Files:

- Modify: `ergon_cli/ergon_cli/composition/__init__.py`.
- Add descriptor type where selected by `DI-4`.
- Modify smoke fixture registration and research-rubrics registration to
  provide descriptors.
- Test: `tests/unit/cli/test_build_experiment_composition.py`.

Implementation steps:

- [ ] Write tests that fail on current hard-coded branches being required for
      smoke and research-rubrics composition.
- [ ] Add descriptor support with a no-op default.
- [ ] Move smoke branch logic into smoke-owned descriptor provider.
- [ ] Move research-rubrics branch logic into research-rubrics-owned descriptor
      provider.
- [ ] Delete `_is_smoke_worker`, `_build_smoke_experiment`, and
      `_build_researchrubrics_workflow_experiment` from generic composition
      once descriptors cover them.
- [ ] Add an architecture test that blocks new `if worker_slug ==` branches in
      generic composition code.

Acceptance gate:

- [ ] `ergon_cli.composition` no longer contains concrete worker slug checks.
- [ ] Existing smoke and research-rubrics unit tests pass.
- [ ] New descriptor test demonstrates extension without modifying CLI
      composition.

### CQ-3: Split workflow command execution from CLI rendering

**Issue fixed:** Workflow parsing, execution, and CLI rendering are coupled
together, causing non-CLI callers to import CLI command modules and making
workflow behavior harder to test independently.

Separate workflow command concerns into three layers:

- parser: command string/argv to typed command;
- executor: typed command plus context/session/service to result;
- renderer: result to CLI stdout/stderr text.

The CLI owns rendering. Builtin agent tools call parser/executor and format
tool-friendly strings. Runtime services own state changes.

Verification:

- CLI tests assert the same stdout/stderr behavior.
- Builtin workflow tool tests no longer import `ergon_cli.commands.workflow`.
- Parser/executor tests cover invalid commands, missing context, dry-run paths,
  and successful resource/topology operations.

Files:

- Add shared parser/executor module selected by `DI-3`.
- Modify: `ergon_cli/ergon_cli/commands/workflow.py`.
- Modify: `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`.
- Test: `tests/unit/cli/test_workflow_cli.py`.
- Test: builtin workflow tool test under `tests/unit/state` or a clearer
  renamed location.

Acceptance gate:

- [ ] CLI rendering remains byte-for-byte compatible where tests already assert
      output.
- [ ] Builtin tools no longer import CLI command modules.
- [ ] Shared executor accepts typed context rather than raw argparse namespace.

### CQ-4: Audit and rename ambiguous "stub" concepts

**Issue fixed:** The word "stub" is used across test doubles, development
defaults, smoke fixtures, and lightweight implementations, making it unclear
which code is production behavior and which code is test support.

Classify every "stub" usage into one of four buckets:

- test double;
- smoke fixture;
- development default;
- lightweight production implementation.

Then rename where the current name lies about ownership. For example, a
production default should not be named like a test double, while a test fake
should live under test support and use fake/test naming consistently.

Verification:

- `rg "stub|smoke|test_harness|test_support"` has an reviewed allowlist for
  production packages.
- User-facing CLI defaults do not imply test-only implementations unless they
  really are test-only.

Files:

- Review: `ergon_core/ergon_core/core/sandbox/manager.py`.
- Review: `ergon_core/ergon_core/core/runtime/inngest/benchmark_run_start.py`.
- Review: `ergon_core/ergon_core/core/rl/eval_runner.py`.
- Review: `ergon_core/ergon_core/test_support/smoke_fixtures/`.
- Review user-facing CLI defaults in `ergon_cli/ergon_cli/main.py`.

Steps:

- [ ] Produce a `stub-smoke-test-naming` section in the complexity ledger or a
      small adjacent audit file.
- [ ] Rename test doubles to `Fake*` or `Test*` and move them under
      test-support when possible.
- [ ] Rename lightweight production defaults to names that describe their
      behavior, not their historical test role.
- [ ] Make production request contracts require explicit worker/evaluator
      choices where defaulting to a stub hides behavior.
- [ ] Add tests for any compatibility aliases that must remain.

Acceptance gate:

- [ ] Production runtime modules do not branch on "stub" identity.
- [ ] User-facing docs/defaults no longer imply that test doubles are production
      defaults.

### CQ-5: Refactor `persist_definition` behind smaller persistence writers

**Issue fixed:** Experiment definition persistence is concentrated in one
high-complexity method, so table-writing mechanics and experiment invariants
are hard to review independently.

`ExperimentPersistenceService.persist_definition` is allowed to be complex
today because it writes a full experiment graph. Keep the transaction boundary,
but split the implementation into named private writer methods or helper
objects:

- definition row writer;
- worker/evaluator writer;
- instance/task/dependency writer;
- assignment writer;
- task-evaluator link writer.

The goal is not to change schema or behavior; it is to make persistence
invariants reviewable in smaller units.

Verification:

- Existing persistence tests pass.
- Add a focused test for multi-worker assignments if one does not already
  cover the branch that motivated CLI special cases.
- Transaction rollback behavior remains unchanged.

Files:

- Modify:
  `ergon_core/ergon_core/core/runtime/services/experiment_persistence_service.py`.
- Potential new helpers under
  `ergon_core/ergon_core/core/persistence/definitions/` if the extracted code
  is persistence-model-specific rather than runtime-service-specific.
- Test existing experiment persistence tests, plus add focused tests if missing.

Implementation steps:

- [ ] Add characterization tests for single-worker, multi-worker, dependency,
      assignment, and evaluator-link persistence.
- [ ] Extract private writer methods without changing transaction boundaries.
- [ ] Name each writer by domain concept, not table name only.
- [ ] Keep `Experiment.persist()` public behavior unchanged.
- [ ] Remove or reduce the C901 ignore only if the extracted shape makes that
      honest.

Acceptance gate:

- [ ] The service reads as orchestration over named writer steps.
- [ ] Rollback behavior remains a single transaction.
- [ ] Multi-worker assignment behavior is covered by tests.

### CQ-6: Refactor `Experiment.validate` into rule objects or named validators

**Issue fixed:** Experiment validation rules are concentrated in one
high-complexity public method, which makes it hard to tell which invariant
failed and hard to add tests for individual rule families.

Split validation by invariant category while preserving the public
`Experiment.validate()` entrypoint:

- task uniqueness and dependency validity;
- worker assignment validity;
- evaluator requirement coverage;
- multi-worker/subtask binding validity.

This makes future public API changes easier to reason about without changing
the caller contract.

Verification:

- Existing validation tests pass.
- Each validator has at least one direct test for its failure mode.
- Error messages stay at least as actionable as current messages.

Files:

- Modify: `ergon_core/ergon_core/api/experiment.py`.
- Potential create: `ergon_core/ergon_core/api/experiment_validation.py`.
- Test: existing experiment API tests or new
  `tests/unit/api/test_experiment_validation.py`.

Implementation steps:

- [ ] Snapshot current validation failure messages for representative invalid
      experiments.
- [ ] Extract validators for task graph, assignments, evaluator coverage, and
      worker bindings.
- [ ] Keep `Experiment.validate()` as the single public entrypoint.
- [ ] Avoid introducing a new public validation framework unless tests show it
      pays for itself.

Acceptance gate:

- [ ] Public caller behavior is unchanged.
- [ ] Validation rules are testable independently.
- [ ] The original C901 ignore can be removed or justified with a smaller
      remaining scope.

### CQ-7: Establish a "no new branch-if example path" rule

**Issue fixed:** The codebase has no enforceable guardrail preventing new
example-specific slug checks from being added to generic composition or runtime
paths.

Add code review guidance and, where possible, tests that reject new generic
composition branches keyed to a specific benchmark or worker slug. The standard
should be: if an example needs special composition, it must declare that need
through a descriptor/hook owned by the example package.

Verification:

- Architecture or lint-style test detects new `if worker_slug ==` branches in
  generic composition modules, with an allowlist during migration.
- Architecture docs record the accepted extension point.

Files:

- Test: `tests/unit/architecture/test_no_ad_hoc_slug_branching.py`.
- Update: `docs/architecture/06_builtins.md` after descriptor/composition
  extension point is accepted.

Rules to enforce:

- No concrete benchmark/worker/evaluator slug comparisons in generic CLI
  composition.
- No suffix parsing for a worker family in generic composition.
- No test-support imports from generic composition unless behind an approved
  plugin/harness boundary.
- Slug checks are allowed inside the package that owns the slug family.

Suggested test inputs:

- Scan `ergon_cli/ergon_cli/composition`.
- Scan generic runtime services after registry injection is introduced.
- Allowlist current branches only until `CQ-2` lands.

Acceptance gate:

- [ ] Adding a new concrete slug branch to generic composition fails tests.
- [ ] Approved extension point is documented.

### CQ-8: Add module ownership headers only where boundaries are unclear

**Issue fixed:** Some modules repeatedly attract code from neighboring domains
because their ownership boundary is implicit and only understood by recent
contributors.

For modules that repeatedly attract misplaced code, add a short top-level
docstring stating what the module owns and what does not belong there. Good
targets are composition, workflow command execution, registry adapters, and
test-support bootstrap modules.

Verification:

- Headers are short and enforceable, not narrative.
- Any new ownership statement points to the relevant architecture doc or RFC.

Candidate modules:

- `ergon_cli/ergon_cli/composition/__init__.py`.
- Shared workflow command executor introduced by `CQ-3`.
- Registry protocol/adapter modules introduced by `DI-1`.
- Smoke fixture bootstrap modules.
- Runtime services that remain broad after the DDD audit.

Acceptance gate:

- [ ] Header says what belongs and what does not belong.
- [ ] Header does not duplicate implementation details.
- [ ] Reviewers can use it to reject misplaced future code.

### CQ-9: Audit runtime services using DDD-style boundaries

**Issue fixed:** The runtime services folder contains many service-shaped
modules, but it is not clear which are true domain/application services and
which are duplicated lifecycle fragments or repositories wearing service names.

The services folder currently contains many service-shaped modules. Some may be
right-sized; others may be procedural clusters that hide duplicate domain
concepts. Audit the folder using domain-driven ownership questions before
moving code:

- What aggregate or lifecycle does this service own?
- What invariant does it enforce?
- What repositories/providers does it depend on?
- Which other services duplicate the same decision?
- Which private helpers are really domain policies?

Initial service map to audit:

```text
ergon_core/ergon_core/core/runtime/services/
  task_management_service.py
  task_execution_service.py
  workflow_service.py
  workflow_initialization_service.py
  workflow_finalization_service.py
  graph_repository.py
  task_cleanup_service.py
  task_propagation_service.py
  subtask_cancellation_service.py
  subtask_blocking_service.py
  task_inspection_service.py
  experiment_persistence_service.py
  evaluator_dispatch_service.py
  evaluation_persistence_service.py
  rubric_evaluation_service.py
  run_service.py
  run_read_service.py
  cohort_service.py
  cohort_stats_service.py
  communication_service.py
```

Likely duplicate/overlap questions:

- Do `task_management_service`, `subtask_cancellation_service`,
  `subtask_blocking_service`, `task_cleanup_service`, and
  `task_propagation_service` encode one task-lifecycle domain or genuinely
  separate use cases?
- Does `workflow_service` duplicate graph/resource lookup logic that belongs in
  a graph/resource application service?
- Is `graph_repository` both persistence repository and mutation-domain
  service?
- Are evaluation dispatch, rubric evaluation, and evaluation persistence cleanly
  separated by responsibility?

Deliverable:

- Add `04-runtime-service-domain-audit.md` to this RFC folder, or add a
  detailed section here if the audit stays short.

Acceptance gate:

- [ ] Every service module has a one-sentence responsibility statement.
- [ ] Duplicate responsibilities are listed with candidate merge/split actions.
- [ ] No code moves happen until characterization tests cover the affected
      lifecycle.

### CQ-10: Audit private helpers as design-smell signals

**Issue fixed:** Large clusters of private helpers can hide missing domain
policies, query objects, DTO mappers, or misplaced responsibilities, but today
they are not audited as architecture signals.

Private `_` functions are not inherently bad, but clusters of private helpers
often mean the code is compensating for a missing domain object, policy, or
repository. Audit helpers before extracting them mechanically.

Initial findings to inspect:

- `task_management_service.py` has validation, invalidation, edge reset,
  execution lookup, and dispatch helpers.
- `workflow_service.py` has sandbox manager lookup, task/resource references,
  node scope resolution, descendant traversal, producer lookup, and copy
  destination helpers.
- `graph_repository.py` has row lookup, sequence allocation, mutation logging,
  cycle checks, DTO conversion, and snapshot helpers.
- `task_execution_service.py` has graph-native preparation, definition
  preparation, attempt numbering, and status emission.

Classification:

- **Keep private helper:** local readability helper with no independent
  invariant.
- **Promote to domain policy:** helper encodes a rule that needs tests and a
  name.
- **Move to repository/query:** helper is mostly persistence lookup.
- **Move to DTO/mapper:** helper converts persistence rows to transport/domain
  objects.
- **Delete after boundary change:** helper exists only because current package
  layering is wrong.

Acceptance gate:

- [ ] Helper audit identifies at least five helpers to promote/move/delete.
- [ ] Each promoted helper gets a direct test or is covered by an existing
      characterization test.
- [ ] No helper is extracted merely to reduce line count without a better name
      or owner.

## Phase gates for the code-quality stream

### Phase Q1 — Audit before movement

Scope:

- Complexity ledger.
- Runtime service domain audit.
- Private-helper audit.
- Ad hoc branch architecture tests with current allowlist.

Acceptance:

- [ ] Audits identify concrete files and candidate actions.
- [ ] Tests prevent new ad hoc slug branches.
- [ ] No production behavior changes.

### Phase Q2 — Composition and workflow cleanup

Scope:

- Descriptor-based experiment composition.
- Workflow parser/executor/renderer split.

Acceptance:

- [ ] Generic composition has no concrete example slug branches.
- [ ] Builtin tools no longer import CLI command modules.
- [ ] Characterization tests pass.

### Phase Q3 — Service/domain refactors

Scope:

- One lifecycle cluster at a time, chosen from the service domain audit.
- Start with the cluster that blocks dependency inversion or test clarity most.

Acceptance:

- [ ] Behavior is locked by characterization tests before moving code.
- [ ] Each extracted domain policy has a named owner and test.
- [ ] Complexity ignores shrink or have updated ledger justification.

## Migration / risk

The main risk is aesthetic refactoring that changes behavior or creates more
abstractions without reducing coupling. Refactors should be small enough to
review and should preserve public behavior unless a separate RFC says
otherwise.

The second risk is over-indexing on cyclomatic complexity. Some orchestration
is inherently sequential and readable. A lower branch count is only a win if
the resulting names clarify invariants and failure modes.

## Open questions

- Which complexity metric should become a hard CI gate after the first cleanup
  pass: Ruff C901, xenon rank, radon score, or a smaller custom import/size
  check?
- Should `ergon_cli.composition` remain one module after descriptors are
  introduced, or should it become a package with separate composition owners?
- Which naming changes are worth compatibility wrappers, and which can be
  changed directly because they are branch-local implementation details?
