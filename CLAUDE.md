# Arcane Agent Guidance

This repository is primarily developed through chat-driven agent workflows.

The default expectation is that agents do test-driven development:

1. identify the smallest test layer that can prove the change
2. add or update that test first when practical
3. implement the change
4. run the narrowest relevant test suite
5. only expand outward to slower integration coverage if needed

## Core Testing Philosophy

The testing strategy for Arcane is documented in `paper_code_structure_plans/19_BULLETPROOF_TEST_SETUP.md`.

The short version:

- fast deterministic tests are the default
- prefer minimum mocking, not maximum isolation
- state assertions matter more than "did it finish?"
- prefer compact tests that cover meaningful failure paths over obvious micro-unit tests
- recorded interactions are preferred to repeated live calls
- deterministic end-to-end or near-end-to-end tests with minimal mocks are highly valued
- smoke tests and fuzz tests are both encouraged when they add real coverage
- browser tests should usually be seeded-state tests
- live provider, live sandbox, and full-stack E2E tests should stay tiny and explicit

## Coverage Decision Rule

When making a change, prefer this order:

1. `tests/state/`
   - for business logic, persistence, lifecycle, and invariants
2. `tests/transcript/`
   - for model/tool-call flow, agent behavior, and execution traces
3. `tests/contracts/`
   - for orchestration, service boundaries, persistence, and emitted events
4. `tests/browser/`
   - for dashboard rendering, state visibility, and live update behavior
5. `tests/live/`
   - only when validating a real external boundary is the actual goal

## Non-Negotiable Defaults

- Do not default to live OpenAI, Exa, E2B, or full-stack E2E tests.
- Do not rely on long polling integration tests when a deterministic test can prove the same behavior.
- Do not stop at completion assertions when stronger persisted-state assertions are available.
- Do not move coverage up the pyramid unless a lower layer genuinely cannot validate the behavior.
- Do not write tests for trivial or obvious behavior when they do not exercise meaningful failure modes, state transitions, or integration contracts.
- Do not over-mock if a deterministic, low-mock test can validate the real contract quickly.

## Deviation Policy

Agents may deviate from the preferred test layer or TDD workflow if they believe it is correct, but **never without first asking the user and getting confirmation**.

That includes cases like:

- choosing a live integration test instead of a deterministic one
- skipping tests for a non-trivial change
- deferring test coverage to a later pass
- putting coverage in a broader or slower layer than the default matrix suggests

If unsure, ask.

## What Good Tests Assert

Prefer assertions about:

- database state
- lifecycle transitions
- serialized payloads
- cleanup behavior
- dashboard-visible state
- transcript or tool-call structure
- non-trivial failure paths
- invariants under repeated or unusual inputs

Prefer not to rely primarily on:

- printed logs
- manual inspection
- "no exception thrown"
- "run completed"

## Test Design Preferences

Prefer tests that are:

- deterministic
- minimal in mocking while still fast and reliable
- short in code length but high in behavioral coverage
- planned before implementation, rather than accreted ad hoc
- targeted at meaningful contracts, edge cases, smoke coverage, or fuzzable invariants

Prefer not to write:

- long verbose tests that mostly restate the implementation
- isolated unit tests for patently obvious behavior
- broad end-to-end tests when a near-end-to-end deterministic version would prove the same thing faster

## Sandbox And UI Expectations

When working on sandbox behavior, assert:

- creation
- ID persistence
- input and output path handling
- cleanup on success and failure
- registry cleanup and idempotency

When working on the dashboard, prefer:

- seeded-state browser tests
- controlled event-stream tests

before adding:

- true live end-to-end browser flows

## Operational Rule

If you touch behavior, you should usually either:

- add a new test, or
- explain why an existing test already covers the behavior

If neither is true, ask before proceeding.

Before implementing a substantial change, briefly plan:

- what behavior is changing
- which test layer should cover it
- what the strongest compact assertion is
