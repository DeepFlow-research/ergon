---
name: arcane-testing
description: Choose the correct Arcane test layer, prefer test-driven development, and place coverage in the smallest deterministic layer that proves the behavior. Use when changing backend orchestration, sandbox lifecycle, model or tool behavior, dashboard behavior, or when deciding where test coverage should live.
---
# Arcane Testing

Use this skill whenever you are changing behavior in `arcane_extension` and need to decide:

- what kind of test to write
- where that test should live
- what the test should assert
- whether a live integration test is actually justified

The detailed rationale lives in `paper_code_structure_plans/19_BULLETPROOF_TEST_SETUP.md`.

## Default Workflow

For non-trivial behavior changes, follow this order:

1. Identify the smallest test layer that can prove the behavior.
2. Prefer the version of that test with the fewest mocks that is still deterministic and fast.
3. Add or update that test first when practical.
4. Implement the code change.
5. Run the narrowest relevant test suite.
6. Only add slower or broader coverage if the lower layer cannot prove the behavior.

Before implementing, make a short plan for:

- the behavior being changed
- the intended test layer
- the main failure paths or invariants to cover
- the smallest strong assertion set

## Test Layer Matrix

### `tests/state/`

Use for:

- persistence behavior
- lifecycle state transitions
- cleanup behavior
- invariants
- task and run state machines

Prefer assertions on:

- exact DB rows or key fields
- state transitions
- cleanup side effects
- idempotency

### `tests/transcript/`

Use for:

- model and tool-call sequencing
- agent execution traces
- worker behavior driven by deterministic model inputs

Prefer assertions on:

- ordered transcript events
- tool call arguments
- tool return handling
- final serialized outputs

### `tests/contracts/`

Use for:

- runner-to-service boundaries
- orchestration contracts
- persistence plus emitted events
- dashboard event contracts

Prefer assertions on:

- emitted event shapes
- persistence writes
- boundary DTOs
- terminal state semantics

### `tests/browser/`

Use for:

- dashboard rendering
- graph visibility
- detail panes
- state updates in the UI

Default browser strategy:

- seed known DB state
- start app
- assert the UI reflects that state

Prefer controlled event-stream tests before true live browser E2E.

### `tests/live/`

Use only when the external boundary itself is what you are validating:

- real E2B behavior
- real provider requests
- one small full-stack smoke path

Keep this layer tiny.

## Default Rules

- Fast deterministic tests are the default.
- Minimum mocking is preferred when determinism and speed can be preserved.
- State assertions are stronger than completion assertions.
- Strong near-end-to-end tests with minimal mocks are preferred over fragile broad E2E and over-isolated micro-unit tests.
- Recorded interactions are better than repeated live calls for most development work.
- Seeded-state browser tests are preferred over live-agent-driven browser flows.
- Live provider and live sandbox tests must be explicit and minimal.
- Smoke tests are good when they cheaply validate system health.
- Fuzz tests are good when they stress invariants, sequencing, or lifecycle correctness.
- Compact tests with high signal are preferred over long verbose tests.

## Ask-Before-Deviating Rule

You may deviate from the preferred layer if you believe it is correct, but **never without first asking the user and getting confirmation**.

Ask before:

- skipping tests for a non-trivial change
- choosing a live integration test instead of a deterministic one
- placing coverage in a slower or broader test layer than the matrix suggests
- replacing a low-mock integration-style test with a heavily mocked unit test
- relying only on manual verification
- deferring tests to a later pass

## What Good Tests Assert

Prefer assertions about:

- persisted database state
- lifecycle transitions
- emitted events
- transcript structure
- cleanup behavior
- dashboard-visible data
- meaningful failure paths
- invariants under varied inputs or event orderings

Avoid relying primarily on:

- printed logs
- long polling
- manual inspection
- "completed successfully" without deeper checks

Avoid spending time on:

- tests for patently obvious behavior
- tests that mostly duplicate implementation structure
- tiny unit tests that do not cover failure paths, state changes, or contracts

## Sandbox Checklist

When changing sandbox behavior, assert:

- sandbox creation
- sandbox ID persistence on the run
- input upload paths
- output download and persistence
- timeout reset behavior if relevant
- cleanup on success
- cleanup on failure
- idempotent teardown

## Frontend Checklist

When changing dashboard behavior, prefer tests that assert:

- seeded run and task state renders correctly
- task graph structure matches persisted data
- action and evaluation details are visible
- failure states render clearly
- live updates appear in order

## Model And Tooling Checklist

When changing model-facing behavior, prefer:

1. scripted deterministic tests first
2. recorded interaction tests second
3. live provider tests only if the provider boundary itself matters

## Smoke And Fuzz Guidance

Use smoke tests when you want:

- a tiny, cheap confidence check that a key path is wired correctly
- confirmation that a major external boundary still works

Use fuzz tests when you want to stress:

- sequencing
- idempotency
- retries
- cleanup
- state-machine invariants
- unusual but valid input combinations

Fuzz tests should target behavioral properties, not random snapshots of model prose.

## Quick Decision Heuristic

Ask:

1. Can this be proven with a deterministic low-mock test?
2. If not, can it be proven with deterministic state plus fake drivers?
3. If not, can it be proven with a transcript or recording?
4. If not, can a seeded browser test prove it?
5. Only then consider a live integration test.

If the answer is still unclear, ask the user before choosing the broader layer.
