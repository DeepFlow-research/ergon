# Implementation Plan And Acceptance

This document turns the testing strategy into an implementation sequence.

## Goal

Provide an engineer with an ordered rollout that is:

- realistic
- incrementally valuable
- easy to validate after each step

## Phase 1: Build The Harness

Implement:

- `ScriptedModelDriver`
- `FakeSandboxDriver`
- `RunTranscript`
- shared DB assertion helpers

Target outcome:

- one deterministic sandbox lifecycle test
- one deterministic worker sequencing test

## Phase 2: Replace The Highest-Value Slow E2E Coverage

Start with the current `tests/e2e` intent and rewrite the most valuable paths into:

- backend state tests
- contract tests
- transcript tests

Start with:

1. sandbox lifecycle
2. workflow completion
3. one worker tool path

## Phase 3: Add Recordings

Implement:

- Arcane-level model recordings
- provider-level VCR for selected provider tests

Target outcome:

- prompt-sensitive regressions can be replayed locally without live calls

## Phase 4: Add Browser Coverage

Implement:

- seeded-state browser fixtures
- controlled-event browser fixtures
- a minimal dashboard test suite

Target outcome:

- most UI regressions can be caught without live runs

## Phase 5: Add Smoke And Live Probe Layer

Implement:

- one sandbox smoke probe
- one provider or recording-backed smoke path
- one browser smoke probe

Target outcome:

- explicit small top-of-pyramid confidence layer

## Phase 6: Add Property And Fuzz Coverage

Implement:

- cleanup idempotency property tests
- task ordering property tests
- state-machine invariant tests

Target outcome:

- compact protection against high-risk orchestration regressions

## Suggested Work Breakdown

### First Pull Request

- support harness skeleton
- fake sandbox driver
- one state test for sandbox lifecycle

### Second Pull Request

- scripted model driver
- transcript capture
- one worker sequencing test

### Third Pull Request

- workflow completion contract tests
- cleanup failure-path tests

### Fourth Pull Request

- browser seeded-state fixtures
- one graph rendering test

### Fifth Pull Request

- provider recordings
- one live sandbox probe

## Definition Of Done For The Overall Program

This program is done when:

- `pytest` is fast and deterministic by default
- most important regressions are caught below the live layer
- sandbox lifecycle is strongly covered
- model-facing paths are testable without live providers
- dashboard behavior is mostly covered by seeded-state browser tests
- live probes are few, explicit, and valuable
- agents working in the repo can follow the test strategy without reinterpretation

## Recommended Immediate Next Slice

If only one slice is implemented now, make it:

- `FakeSandboxDriver`
- shared DB assertions
- `test_sandbox_lifecycle.py`

That slice should validate whether the overall strategy produces materially better signal than the current slow E2E loop.
