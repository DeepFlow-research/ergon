# Smoke, Live, And Provider Tests

This document defines the tiny top of the test pyramid.

## Goal

Keep a very small number of tests that validate real external boundaries and end-to-end wiring without turning the whole suite into a slow system test.

## Three Distinct Categories

### Smoke Tests

Purpose:

- cheap confidence that a key path is still wired correctly

Properties:

- small
- fast
- deterministic where possible
- narrow in scope

### Recorded Provider Tests

Purpose:

- validate provider-facing integration behavior with replayable cassettes

Properties:

- more realistic than scripted tests
- cheaper and more stable than repeated live calls

### Live Probes

Purpose:

- validate a real external boundary where the vendor or network behavior itself matters

Properties:

- explicit
- opt-in
- tiny in count

## Smoke Test Recommendations

Keep smoke tests for:

- one sandbox lifecycle path
- one dashboard health path
- one recording-backed model or provider path

Smoke tests should not become the main correctness layer.

They should answer:

- is the system still wired together?

not:

- did we comprehensively test every contract?

## Provider Recording Strategy

Use provider recordings for:

- OpenAI request and response compatibility
- Exa integration behavior
- reproduction of previously reported provider bugs

Recordings should be:

- small
- one behavior per cassette where possible
- easy to refresh explicitly

## Live Probe Recommendations

Keep only tests that give unique confidence.

Suggested set:

### one real E2B probe

### one real provider probe

### one real full-stack browser probe

If a live probe is not providing unique information, remove it.

## Gating Recommendations

Recommended usage:

- local default: do not run
- CI default: do not run unless explicitly requested
- nightly or pre-release: run
- manual debugging: run on demand

## Marker Recommendations

- `smoke`
- `recorded`
- `live`
- `sandbox_live`
- `provider_live`
- `browser_live`

## Anti-Patterns

Avoid:

- many live probes
- benchmark-scale live suites
- live tests that are not clearly more informative than a deterministic or recorded version

## Acceptance Criteria

This slice is complete when:

- Arcane has a small stable smoke layer
- provider behavior can be validated with recordings
- only a minimal set of opt-in live probes remains
