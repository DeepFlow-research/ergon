# Bulletproof Test Setup Index

This folder breaks the testing strategy into implementation-oriented documents.

The top-level overview still lives in `../19_BULLETPROOF_TEST_SETUP.md`.

This folder is the engineer-facing breakdown for turning that strategy into real code, fixtures, and tests.

## Goal

Make Arcane's default test loop:

- deterministic
- low-mock where possible
- compact
- state-assertive
- easy for chat-driven agents and human engineers to apply consistently

## Files

- `01_overview_and_decision_matrix.md`
  - repository-wide testing philosophy, decision rules, and where coverage should live

- `02_deterministic_harness_and_drivers.md`
  - the concrete testing harness, fake drivers, and shared support primitives to build first

- `03_state_and_contract_tests.md`
  - backend state tests and contract tests for runs, tasks, persistence, and orchestration boundaries

- `04_transcript_and_recording_tests.md`
  - model-facing test strategy, transcript capture, scripted model behavior, and recordings

- `05_sandbox_lifecycle_tests.md`
  - how to test sandbox creation, uploads, outputs, teardown, and cleanup invariants

- `06_browser_and_dashboard_tests.md`
  - seeded-state and controlled-event browser testing strategy for the dashboard

- `07_smoke_live_and_provider_tests.md`
  - smoke tests, live probes, provider VCR tests, and when to use each

- `08_fuzz_and_property_tests.md`
  - fuzz targets, invariants, property-test design, and what not to fuzz

- `09_agent_workflow_and_repo_guidance.md`
  - how agents should choose test layers, plan tests, and work within the repo rules

- `10_implementation_plan_and_acceptance.md`
  - phased rollout, file targets, success criteria, and recommended first slices

## Recommended Reading Order

1. `01_overview_and_decision_matrix.md`
2. `02_deterministic_harness_and_drivers.md`
3. `03_state_and_contract_tests.md`
4. `05_sandbox_lifecycle_tests.md`
5. `04_transcript_and_recording_tests.md`
6. `06_browser_and_dashboard_tests.md`
7. `07_smoke_live_and_provider_tests.md`
8. `08_fuzz_and_property_tests.md`
9. `09_agent_workflow_and_repo_guidance.md`
10. `10_implementation_plan_and_acceptance.md`

## Recommended Implementation Order

1. Build the deterministic harness and fake drivers.
2. Add backend state and contract coverage for sandbox lifecycle and workflow completion.
3. Add transcript capture and scripted model tests.
4. Add provider and model recordings.
5. Add seeded-state browser tests.
6. Add smoke and live probes.
7. Add fuzz and property coverage for invariants.

## Intended Outcome

An engineer should be able to pick one file from this folder and implement that slice without needing to reinterpret the whole strategy from scratch.
