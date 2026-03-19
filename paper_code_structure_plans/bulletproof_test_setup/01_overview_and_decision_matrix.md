# Overview And Decision Matrix

This document answers one question:

**given a change, what test should we write, where should it live, and what should it assert?**

## Primary Philosophy

Arcane prefers tests that are:

- deterministic
- low-mock where possible
- fast enough for constant local use
- compact relative to the amount of behavior they validate
- focused on real contracts, failure paths, and invariants

Arcane does **not** want:

- trivial unit tests for obvious behavior
- broad live E2E tests as the default development loop
- log-based or completion-only assertions when stronger state assertions are available

## The Test Pyramid

### `tests/state/`

Use for:

- persisted state transitions
- cleanup behavior
- invariants
- lifecycle bookkeeping
- aggregation logic

This is the default layer.

### `tests/transcript/`

Use for:

- model and tool-call sequencing
- execution traces
- deterministic agent behavior
- transcript snapshots

This is the default model-facing layer.

### `tests/contracts/`

Use for:

- runner/service boundaries
- orchestration contracts
- persistence plus event emission
- dashboard event contracts

This is the default orchestration layer.

### `tests/browser/`

Use for:

- graph rendering
- detail panes
- live update visibility
- dashboard state correctness

Default strategy:

- seed state
- load app
- assert rendered state

### `tests/live/`

Use only when the real external system boundary is the point of the test:

- real E2B behavior
- real provider compatibility
- one small full-stack probe

## Decision Matrix

| Change Type | Preferred Test Layer | Typical Driver Strategy | Strongest Assertions |
|-------------|----------------------|-------------------------|----------------------|
| DB writes, run status, cleanup | `tests/state/` | real DB + fake model, sandbox only if needed | row values, lifecycle transitions, no orphaned state |
| worker/tool ordering | `tests/transcript/` | scripted model + real sandbox if sandbox semantics matter | ordered tool calls, transcript events, persisted actions |
| runner/service integration | `tests/contracts/` | real persistence + fake model, real sandbox only when relevant | emitted events, DTO shape, terminal state semantics |
| dashboard rendering | `tests/browser/` | seeded DB + controlled events | graph structure, visible detail, status rendering |
| provider API compatibility | `tests/live/` or recorded test | provider VCR or live | request/response compatibility, stable integration |
| sandbox vendor behavior | `tests/live/` | real E2B | create/upload/download/cleanup probe |

## The Low-Mock Rule

When choosing between:

- a heavily mocked unit test
- a deterministic low-mock integration-style test

prefer the low-mock test if it is still:

- fast
- reliable
- explicit about assertions

Use fakes to remove:

- nondeterminism
- external cost
- network dependencies

Do not use fakes to remove the core contract you are trying to validate.

## Canonical Benchmark Fixture Rule

Arcane should not rely on vague or low-signal synthetic agent data.

For benchmark-facing transcript and harness tests, prefer a small canonical corpus of fixtures that are:

- derived from real benchmark archetypes
- reduced to the smallest form that still exercises the real contract
- representative of meaningful tool chains and failure modes
- shared across transcript, state, and browser tests where possible

The fixture question should always be:

- "what smallest benchmark-shaped scenario gives us high signal?"

not:

- "what toy prompt is easiest to invent?"

## The Compactness Rule

Before implementing a test, ask:

1. What real behavior or invariant am I proving?
2. What is the shortest test that proves it?
3. Can one well-designed fixture replace five repetitive tests?
4. Am I asserting the contract rather than restating the implementation?

## Required Failure-Path Bias

A good Arcane test should usually cover at least one of:

- failure behavior
- cleanup behavior
- retry behavior
- invalid ordering
- missing data
- inconsistent intermediate state

If it covers none of those and only proves obvious happy-path behavior, it is probably too weak.

## Test Selection Workflow

1. Write down the behavior change in one sentence.
2. Identify the lowest test layer that can prove it.
3. Decide whether a fake driver preserves the real contract.
4. Define the strongest state, transcript, or UI assertions.
5. Only then implement the test and code.

## Ask-Before-Deviating Rule

If an engineer or agent believes a broader test is the correct choice, that is allowed.

But they must ask first before:

- skipping a lower-layer test
- replacing a deterministic test with a live one
- writing only manual verification steps
- omitting tests for a non-trivial behavioral change
