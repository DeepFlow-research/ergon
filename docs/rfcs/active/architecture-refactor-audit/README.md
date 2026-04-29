---
status: active
opened: 2026-04-27
author: GPT-5.5
architecture_refs:
  - docs/architecture/README.md
  - docs/architecture/01_public_api.md
  - docs/architecture/02_runtime_lifecycle.md
  - docs/architecture/04_persistence.md
  - docs/architecture/06_builtins.md
  - docs/architecture/07_testing.md
supersedes: []
superseded_by: null
---

# RFC: Architecture Refactor Audit

## Problem

Ergon has moved quickly enough that useful behavior now lives beside accidental
structure: direct package coupling, special-case composition branches,
duplicated setup logic, test-support leakage, and high-complexity orchestration
code. The immediate goal is not to redesign product behavior. It is to make the
existing behavior easier to understand, test, extend, and preserve.

This RFC folder starts an audit-driven refactor program. It separates the work
into three lenses so each proposal can stay concrete:

- [`01-dependency-inversion.md`](01-dependency-inversion.md) covers package
  boundaries, public API shape, registry resolution, and cross-package imports.
- [`02-test-brittleness-and-gaps.md`](02-test-brittleness-and-gaps.md) covers
  brittle tests, fixture boundaries, missing contract tests, and real-LLM/e2e
  confidence gaps.
- [`03-code-quality.md`](03-code-quality.md) covers duplication, branch-heavy
  example paths, excessive nesting, cyclomatic complexity, naming drift, and
  file ownership.

## Refactor rule

Behavior stays the same unless a follow-up RFC explicitly changes it. The
program should first extract boundaries, name concepts, move code to better
owners, and add characterization tests around risky flows. Any behavioral
change discovered during cleanup should be split into a separate bug or RFC.

## Target architecture principles

1. **Core owns contracts, not default implementations.** `ergon_core` should
   expose stable interfaces and runtime services; concrete benchmark, worker,
   evaluator, model, and sandbox registrations should be injected through an
   explicit composition boundary.
2. **Builtins are plugins, not runtime prerequisites.** `ergon_builtins` should
   implement public contracts and provide a default registry bundle without
   requiring core runtime imports to know about that bundle.
3. **CLI is an adapter.** `ergon_cli` should parse user input and call shared
   application services. Agent tools and core runtime code should not depend on
   CLI command modules.
4. **Tests are consumers of public contracts.** Test support may provide
   fixtures, fake providers, and smoke registrations, but core code should not
   branch on test identities or sentinel values.
5. **Complexity should be paid down near ownership boundaries.** Large
   orchestration functions should be split by responsibility only when the
   split clarifies invariants or makes behavior easier to test.

## Proposal

Adopt this RFC folder as the tracking document for an architecture audit. Each
child document should collect concrete findings, define the target shape, and
list candidate refactors in dependency order. Accepted follow-up RFCs and
implementation plans can then pull from these findings without turning this
folder into a single mega-plan.

The initial work should prioritize:

1. Dependency inversion and composition boundaries, because package coupling
   makes every later cleanup harder.
2. Test brittleness and missing contract coverage, because behavior-preserving
   refactors need confidence.
3. Code quality and complexity cleanup, because it benefits most after the
   owning modules and contracts are clearer.

## Invariants affected

This audit does not change runtime invariants by itself. It may produce
follow-up RFCs that update:

- `docs/architecture/01_public_api.md` if public API ownership changes.
- `docs/architecture/02_runtime_lifecycle.md` if runtime composition or task
  orchestration boundaries change.
- `docs/architecture/06_builtins.md` if registry/plugin semantics change.
- `docs/architecture/07_testing.md` if test tier responsibilities change.

## Migration

No code migration is proposed in this folder directly. Migration guidance lives
inside each child audit document and should be converted into implementation
plans only after the target architecture is accepted.

Before implementation, each refactor should have:

- A characterization test or existing test reference for the behavior being
  preserved.
- A clear package-boundary statement: what module owns the new abstraction and
  which packages may import it.
- A rollback path if the refactor uncovers behavior that differs from the docs.

## Alternatives considered

### One giant architecture RFC

This would be easy to create, but it would encourage broad, vague findings and
make acceptance difficult. Dependency inversion, tests, and code quality have
different audiences and different risk profiles.

### Three unrelated top-level RFCs

This would make each stream independently acceptable, but it would hide the
shared refactor goal. The folder keeps the audit cohesive while preserving
focused documents.

### Immediate code cleanup without an audit

This risks preserving the current accidental architecture under new names.
Because the goal is behavior-preserving refactor, the first deliverable should
be shared understanding and standards.

## Open questions

- Which package boundary should own registry resolution: core, a new
  composition package, or the CLI/application layer?
- How much backward compatibility is required for current import paths inside
  the repo?
- Should complexity thresholds become CI-enforced once the first cleanup pass
  lands, or should they remain advisory until the major offenders are reduced?

## On acceptance

When this RFC folder is accepted:

- Move the folder or accepted child docs under `docs/rfcs/accepted/`.
- Link the first implementation plan in `docs/superpowers/plans/`.
- Update affected architecture docs with any new import-boundary or testing
  invariants.
