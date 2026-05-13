---
title: Unit test audit and prune
date: 2026-05-13
status: approved
---

# Unit test audit and prune

## Context

`pnpm run test:be:fast` runs 619 unit tests in 23.86s wall / 106.84s CPU
(`-n auto` across 8 workers, this machine). Time is uniformly distributed:
the top 50 slowest tests account for ~16s of CPU; the remaining ~570 tests
account for ~91s. There is no concentrated set of slow offenders to kill;
the suite is large and the cost per test averages ~170ms.

The user's hypothesis — old/brittle tests that no longer earn their keep,
plus tests that could be consolidated — is consistent with the data.

## Goal

Cut 25–30% of unit tests without losing meaningful coverage. Wall-clock
improvement follows from count reduction.

## Deletion rubric

A test is a deletion candidate if any of:

1. **Type-system shadowing** — asserts what Pydantic/ty already enforces
   (field exists, type is `str`, default is `None`).
2. **Test-double dominance** — every meaningful collaborator is mocked;
   the test verifies the mock setup, not the code under test.
3. **Trivial delegation** — exercises a one-line wrapper or pass-through.
4. **Redundant architecture check** — duplicates another architecture
   test's invariant on the same code paths.
5. **Dead-code coverage** — covers code no production caller reaches
   (often left over from deleted features).
6. **Parametrize bloat** — N parametrized cases that all hit the same
   branch (vs. genuinely covering different ones).

## Consolidation rubric

Multiple tests share setup and assert facets of one operation that a
single well-named test could cover.

## Must-keep rubric

A test MUST be kept if:

- It pins behavior derived from the May 2026 authoring API redesign
  postmortem (per CLAUDE.md "Agent regression guardrails").
- It is the only test exercising a public-API contract.
- It exercises a non-trivial branch or invariant the codebase relies on.

## Domain ordering (highest-ROI first)

1. **`ergon_core/tests/unit/architecture/`** (9 files) — highest redundancy
   suspected; tests do FS/AST walks of the source tree.
2. **Contract tests** (`test_*_contract.py` across packages) — likely
   Pydantic/ty overlap.
3. **State/schema tests** (`tests/unit/state/` in each pkg) — same.
4. **Registry/catalog tests** — moderate value; check for redundancy.
5. **Runtime tests** (`ergon_core/tests/unit/runtime/`) — highest signal,
   touch last; cut here only if obviously bloated.
6. **CLI tests** — keep most; prune duplicate command-shape assertions.
7. **`smoke_base/` and postmortem-linked tests** — audit ONLY with
   explicit per-file approval.

## Per-domain process

1. List every test file in the domain with a one-line "what does this
   prove" summary per test.
2. Classify each test: **KEEP / CONSOLIDATE / DELETE** with one-line
   reasoning.
3. Present the classification table; wait for user approval before any
   deletion.
4. Implement changes; run that domain's tests + the full unit suite.
5. Commit on `feature/copy-authoring-api-redesign-v2-rfcs` (current
   branch) with message `audit: prune <domain> (-N tests, -Ms wall)`.

## Safety rules

- Each domain is its own commit (revertable individually).
- After each domain: run `pnpm run test:be:fast` AND
  `pnpm run test:be:integration` to surface coverage gaps.
- Each deletion's commit message names the surviving test (or invariant
  enforced elsewhere) that still covers the same property — or
  explicitly states "no replacement; accepted gap because X."
- Postmortem-linked tests excluded unless user OKs each one.
- Stage only audit files. Do not touch user's WIP (CLAUDE.md, RFC docs,
  untracked AGENTS.md/CODEX.md/etc.).

## Measurement

- Baseline: 619 tests / 23.86s wall / 106.84s CPU (this machine,
  `-n auto`).
- Each domain commit records new count + wall + CPU in the message body.
- Final summary lives in the PR description.

## Stop criteria

Whichever first:
- <5% prunable in the next domain.
- Wall-clock under 15s.
- User calls it.

## Out of scope

- Folder restructure (top-level `/tests` consolidation, type-vs-domain
  split). Discussed and parked.
- Integration / e2e / real_llm audits — different cost structure.
- Strategy A (session-scoped FS-walk fixture for architecture tests) —
  may or may not be needed after domain 1; revisit at that point.
