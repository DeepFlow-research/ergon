# Agent Workflow And Repo Guidance

This document explains how the testing strategy should be encoded for chat-driven agents working in Arcane.

## Goal

Make the testing philosophy operational for:

- Cursor agents
- Claude-style agents
- human engineers following the same workflow

## Repository Guidance Artifacts

These files should exist and stay aligned:

- `CLAUDE.md`
- `.cursor/skills/arcane-testing/SKILL.md`
- `.cursor/rules/test-strategy.mdc`

## What These Artifacts Must Teach

### TDD Default

For non-trivial behavior changes:

1. choose the smallest test layer
2. plan the strongest compact assertions
3. add or update the test first when practical
4. implement the change
5. run the narrowest relevant suite

### Ask-Before-Deviating Rule

Agents may deviate when they believe it is correct.

But they must ask first before:

- skipping a lower-layer test
- using a live test where a deterministic one should work
- deferring tests
- relying only on manual verification

### Low-Mock Preference

Agents should learn:

- determinism matters
- but over-mocking is not the goal
- low-mock near-end-to-end tests are often preferable

### Compactness Preference

Agents should optimize for:

- small tests
- strong assertions
- meaningful failure paths

not:

- lots of tiny obvious tests
- repetitive coverage with little extra signal

## When The Guidance Should Trigger

These rules and skills should apply whenever an agent is:

- changing backend behavior
- changing orchestration behavior
- changing sandbox behavior
- changing model or tool behavior
- changing dashboard behavior
- deciding where test coverage belongs

## Keeping Guidance In Sync

When the testing architecture changes, update:

1. the implementation docs in this folder
2. `19_BULLETPROOF_TEST_SETUP.md`
3. `CLAUDE.md`
4. the Cursor skill
5. the Cursor rule

Do not let the operational guidance drift away from the actual test architecture.

## Acceptance Criteria

This slice is complete when:

- agents have a clear, persistent policy for test placement and test style
- deviations require explicit confirmation
- the repo's guidance artifacts reflect the same philosophy as the main testing plan
