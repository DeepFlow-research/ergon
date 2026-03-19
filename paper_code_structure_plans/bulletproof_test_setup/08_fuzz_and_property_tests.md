# Fuzz And Property Tests

This document defines how Arcane should use fuzzing and property testing.

## Goal

Protect the system against lifecycle, sequencing, and state-machine regressions with compact property-driven tests.

## What To Fuzz

Arcane should fuzz:

- orchestration orderings
- retries
- cleanup flows
- valid-but-unusual tool-call sequences
- task DAG completion orderings
- partial failure cases

Arcane should usually not fuzz:

- long-form model prose quality
- arbitrary string variation with no behavioral consequence

## Why This Matters

Many of Arcane's most dangerous bugs are not:

- "the final answer text looked odd"

They are:

- cleanup did not happen
- state machine entered an impossible state
- repeated events produced duplicated side effects
- sibling completion order broke parent finalization

These are ideal property-test targets.

## High-Value Properties

### Cleanup Idempotency

Property:

- repeated cleanup does not leave retained sandbox state or inconsistent run state

### Terminal State Safety

Property:

- terminal runs do not retain sandbox IDs

### Ordering Safety

Property:

- out-of-order but valid sibling completions do not produce impossible parent state

### Evaluation Gating

Property:

- evaluation does not run before required outputs exist

### Dashboard Consistency

Property:

- dashboard terminal state never contradicts DB terminal state

## Fuzz Input Families

Use generated or parameterized inputs for:

- task completion orders
- child failure vs success combinations
- cleanup event duplication
- tool error placement
- missing output presence or absence
- stakeholder question counts near limits

## Relationship To Toolkit-Coverage Fixtures

Long toolkit-coverage fixtures are useful, but they are not a substitute for actual fuzz or property testing.

What long fixtures give us:

- realistic interoperability coverage across many tools
- strong signal that multi-step chains still basically work
- some incidental variation coverage "for free"

What they do not give us by themselves:

- systematic exploration of ordering permutations
- systematic failure placement
- proof that invariants hold across many combinations

Recommended approach:

1. build compact canonical fixtures
2. build a few longer toolkit-coverage fixtures
3. use both as seeds for parameterized or property-driven variants

## Test Style

Prefer:

- compact property tests
- generated permutations with clear invariants
- small counterexample-friendly fixtures

Avoid:

- giant random tests with weak assertions
- fuzzing that only increases runtime without covering new invariants

## Suggested File Layout

```text
tests/state/
└── test_state_properties.py

tests/contracts/
└── test_orchestration_properties.py
```

or a dedicated:

```text
tests/fuzz/
├── test_cleanup_properties.py
└── test_ordering_properties.py
```

Use whichever layout keeps ownership clear.

## Acceptance Criteria

This slice is complete when:

- key lifecycle invariants are covered by compact property-style tests
- repetitive one-off edge-case tests can be replaced by a small number of stronger generated tests
