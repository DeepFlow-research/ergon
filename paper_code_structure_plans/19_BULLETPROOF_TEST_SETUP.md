# Bulletproof Test Setup

This document reframes the current Arcane testing story around one goal:

**make the default test suite fast, deterministic, and state-assertive, while keeping a very small number of live end-to-end probes for real-world confidence.**

It is meant as a follow-on to `17_E2E_TEST_SUITE.md`.

For implementation-ready breakdowns, see:

- `paper_code_structure_plans/bulletproof_test_setup/00_INDEX.md`

That earlier document had the right instinct:

- test the real system boundaries
- assert against persisted state
- avoid meaningless isolated tests

But the current implementation still lands in an awkward middle ground:

- it is slow enough to feel like end-to-end testing
- it still depends on live services and runtime orchestration
- most assertions are closer to "did something finish?" than to "did the system behave correctly?"

So the problem is not that the current suite is useless.

The problem is that it is too expensive to run often, and too weak in its assertions to be the main source of confidence.

## Executive Summary

The recommended testing model is:

1. make deterministic, no-network, no-live-sandbox tests the default
2. prefer minimum mocking while preserving determinism and speed
3. record and replay model/provider interactions when prompt behavior matters
4. assert strongly against run, task, action, evaluation, dashboard, and cleanup state
5. keep browser tests narrow and state-driven
6. keep live provider and live sandbox tests tiny, explicit, and opt-in

In practice, that means Arcane should have five layers:

- `tests/state/`
  - fast deterministic state-contract tests
- `tests/transcript/`
  - scripted or recorded model/tool execution tests
- `tests/contracts/`
  - persistence, event, and orchestration boundary tests
- `tests/browser/`
  - Playwright tests against seeded state and controlled event streams
- `tests/live/`
  - tiny set of real OpenAI, Exa, E2B, and full-stack smoke probes

The main shift is:

**completion is not the primary assertion anymore.**

Instead, tests should assert:

- exact or partial lifecycle transcripts
- exact persisted database invariants
- exact serialized UI-visible state
- exact cleanup and resource release behavior

## What Is Wrong With The Current E2E Shape

The current `tests/e2e` suite is slow because it combines:

- real benchmark loading
- Inngest orchestration
- asynchronous polling
- database persistence
- real or semi-real external dependencies
- benchmark-specific runtime behavior

And despite paying that cost, the shared assertion model is still intentionally lightweight:

- run reached terminal success
- evaluation exists
- scores exist
- failures are printed for a human to inspect

That is a useful operational probe, but it is not a strong development test loop.

For local development, we want:

- tests that run in seconds
- failures that pinpoint the broken contract
- deterministic reproduction
- no accidental live model calls
- no accidental live sandbox creation

## Design Principles

### 1. Fast By Default

Running `pytest` should not require:

- OpenAI credentials
- Exa credentials
- E2B credentials
- a worker process
- a real sandbox
- long polling loops

The default test run should stay entirely inside a deterministic harness.

### 2. Minimum Mocking, Not Maximum Isolation

Arcane prefers tests that are as real as they can be while still being:

- deterministic
- fast
- cheap to run
- easy to reason about

That means we do not want to reflexively mock every dependency just because a test can be called a unit test.

Instead, prefer:

- low-mock deterministic tests
- seeded-state integration tests
- fake drivers only where they preserve real contracts while removing cost or nondeterminism

The ideal is often:

- near-end-to-end behavior
- minimal mocks
- deterministic inputs
- strong state assertions

### 3. State Is The Source Of Truth

Tests should assert specific persisted and emitted state, not just final status.

Examples:

- `Run.status` transitions correctly
- `Run.e2b_sandbox_id` is populated and then cleared
- expected `Action` rows exist with expected payloads
- expected `Evaluation` and `CriterionResult` rows exist
- the dashboard-visible data model matches database state
- cleanup occurs on both success and failure

### 4. Live Calls Must Be Explicit

Arcane should default to "no live provider requests" in the same spirit as PydanticAI's testing guidance.

If a test wants to hit:

- OpenAI
- Exa
- E2B
- a live frontend/backend stack

it should opt into that explicitly with markers and fixtures.

### 5. Recordings Beat Polling For Most Confidence Loops

When we care about prompt or provider behavior, recording and replaying interactions is better than repeatedly rerunning the full live stack.

Raw HTTP VCR is useful, but Arcane also needs a higher-level recording format for its own domain boundaries.

### 6. Avoid Trivial Test Suites

AI agents often drift toward tests that are technically valid but strategically weak:

- obvious unit tests for simple getters or one-line transformations
- tests that mirror the implementation instead of the contract
- tests that never exercise meaningful failure paths

Arcane should actively resist that pattern.

Prefer tests that:

- cover non-trivial failure paths
- validate state transitions and integration contracts
- exercise cleanup, retries, and edge cases
- stress meaningful invariants

Avoid tests whose main value is only:

- line coverage on obvious behavior
- making the suite look larger
- restating what the code already obviously does

### 7. Compactness Matters

We want tests with a high signal-to-lines-of-code ratio.

That means:

- fewer tests is fine if each one proves a real contract
- shorter tests are preferred when they still assert the important behavior
- broad but deterministic fixtures are often better than many tiny repetitive tests

Before implementing, plan:

- the behavior being changed
- the test layer that should cover it
- the failure paths or invariants worth asserting
- the most compact assertion set that still gives strong confidence

### 8. Keep The Tip Of The Pyramid Tiny

True live end-to-end tests should exist, but only as a small set of probes:

- one or two sandbox lifecycle probes
- one browser health path
- one provider-backed model path
- one full-stack "new run appears in UI and completes" path

Anything broader should be moved down to a deterministic layer.

## Proposed Test Pyramid

### Layer 1: Deterministic State Tests

These are the new default.

They should use:

- a test database
- fake or in-memory model drivers
- fake or in-memory sandbox drivers
- direct invocation of services or runners without polling

These tests assert exact contracts:

- task graph persistence
- task state transitions
- action serialization
- output persistence
- evaluation aggregation
- cleanup idempotency

These should be the highest-volume tests in the suite.

They should also usually be the first place to look before adding narrow trivial unit tests.

### Layer 2: Transcript Tests

These test the execution story, not just the final rows.

Each test produces a `RunTranscript` that captures:

- model prompts
- model responses
- tool calls
- tool returns
- sandbox lifecycle events
- run and task status transitions
- emitted dashboard events

Tests can then assert:

- exact transcript snapshots for narrow deterministic paths
- selected invariants over transcript content for broader paths

This is the Arcane equivalent of capturing model messages in PydanticAI.

### Layer 3: Contract Tests

These validate boundaries between Arcane subsystems:

- runner to service
- service to persistence
- service to event emission
- service to dashboard updates
- service to sandbox manager

They should run against real DB persistence where that matters, but still use deterministic drivers for model and sandbox behavior.

### Layer 4: Browser Tests

These should mostly be state-driven, not full live-agent-driven.

Recommended pattern:

1. seed Postgres with a known run/task/action/evaluation shape
2. start backend and dashboard locally
3. optionally inject a controlled websocket or dashboard event stream
4. assert that the UI renders the expected graph, statuses, logs, and detail panes

Only a very small number of tests should drive a genuinely live run through the UI.

### Layer 5: Live Probes

These are explicitly opt-in and should be small in number.

Suggested examples:

- one real E2B sandbox create -> upload -> cleanup probe
- one real Exa-backed benchmark toolkit probe
- one real model request with provider recording refresh
- one full-stack browser smoke test

These should be suitable for nightly runs or explicit pre-release checks, not the default inner loop.

## Core Testing Primitives

The key to making this work is introducing a small set of explicit test abstractions.

### `ScriptedModelDriver`

This is the Arcane analogue of PydanticAI's `FunctionModel`.

It should let a test specify:

- what the model sees
- what tool calls it makes
- what final answer it returns

This enables fast, precise, deterministic tests of:

- worker behavior
- tool call ordering
- branching logic
- retry behavior
- task completion logic

Example shape:

```python
model = ScriptedModelDriver(
    steps=[
        ToolCall("read_file", {"file_path": "/inputs/data.csv"}),
        ToolCall("analyze_data", {"data_description": "summarize"}),
        FinalText("Summary complete."),
    ]
)
```

### `RecordedModelDriver`

This replays a previously captured Arcane-native model transcript.

This is useful when:

- prompt wording matters
- structured model responses matter
- we want a realistic transcript without paying for live provider calls

This recording should be higher-level than raw HTTP VCR.

It should store the request and response objects Arcane actually sees and consumes.

### `LiveModelDriver`

This is only for explicit integration tests.

Normal tests should fail fast if a live model driver is used without opting in.

### `FakeSandboxDriver`

This is one of the most important additions.

It should emulate:

- sandbox creation
- filesystem upload and download
- command execution
- timeout resets
- teardown

without talking to E2B.

This enables deterministic tests for:

- sandbox lifecycle bookkeeping
- resource path registration
- output persistence
- cleanup semantics
- failure handling

### `LiveSandboxDriver`

This keeps the real E2B integration path available, but only for a tiny, explicit test subset.

## `RunTranscript`: The Missing Artifact

Arcane needs a first-class testing artifact that makes execution easy to inspect and assert.

Suggested contents:

- run metadata
- ordered task state transitions
- model turns
- tool calls and returns
- sandbox lifecycle events
- persisted outputs
- evaluation events
- cleanup events
- dashboard events

Example shape:

```python
assert result.transcript.events == [
    SandboxCreated(task_id=task.id),
    ToolCalled(name="read_file"),
    ToolReturned(name="read_file", success=True),
    TaskStatusChanged(task_id=task.id, status="completed"),
    SandboxClosed(task_id=task.id, reason="completed"),
]
```

This gives us a much better testing primitive than:

- waiting on polling loops
- scanning terminal output
- printing failures for human review as the main signal

## What We Should Assert

### Sandbox Lifecycle Assertions

These should be explicit and common.

For every relevant test, assert:

- sandbox created exactly once for the task
- sandbox ID stored on the run when setup completes
- inputs uploaded to expected sandbox paths
- output files downloaded from expected final-output paths
- sandbox timeout reset when expected
- cleanup clears `Run.e2b_sandbox_id`
- termination is attempted on both success and failure
- sandbox registry entries are removed even if kill fails

### Persistence Assertions

Tests should assert exact persisted shape, including:

- `Experiment`
- `Run`
- `Action`
- `Evaluation`
- `CriterionResult`
- `ResourceRecord`
- communication records where relevant

This should include exact field values where practical, not just existence checks.

### Orchestration Assertions

Tests should assert:

- event emission order
- child task propagation order
- retry and failure semantics
- parent completion gating
- cleanup on every terminal path

### Frontend Assertions

Browser tests should assert:

- a run appears in the UI with the right identity and status
- task graph nodes and edges match persisted task structure
- action and evaluation details match persisted rows
- terminal and failure states render clearly
- live updates appear in the expected order

## How VCR Should Work In Arcane

Arcane should support two recording layers.

### 1. Provider-Level VCR

Use normal HTTP recording for:

- OpenAI
- Exa
- other external HTTP integrations

This is useful for:

- reproducing bug reports
- validating request/response serialization
- ensuring provider integrations stay compatible over time

### 2. Arcane-Level Recordings

This is more important for everyday testing.

Instead of only recording raw HTTP, Arcane should be able to record:

- model requests and responses as Arcane sees them
- tool calls and returns
- possibly selected sandbox interactions

This gives us recordings that are:

- provider-agnostic
- stable at the application boundary
- much easier to assert against than raw HTTP cassettes

The mental model is:

- use provider VCR when validating a provider boundary
- use Arcane recordings when validating Arcane behavior

## Smoke Tests

Smoke tests are valuable here.

They should be:

- tiny
- cheap
- deterministic where possible
- focused on verifying that a critical path is still wired correctly

Good smoke tests:

- one minimal sandbox lifecycle probe
- one minimal dashboard health path
- one minimal provider or recording-backed path

Smoke tests should give fast confidence, not become the main correctness layer.

## Fuzz Testing Strategy

We should fuzz orchestration contracts more than natural-language outputs.

The right question is not:

- "did the LLM produce a perfect answer?"

The right questions are:

- can the system tolerate unexpected but valid tool-call patterns?
- can the system tolerate partial failure?
- does cleanup remain correct under retries and interruption?
- do task and run states remain valid?

Good fuzz targets:

- tool call sequences within a task budget
- repeated stakeholder questions up to `max_questions`
- partial sandbox failures
- missing output files
- duplicate cleanup events
- task retries after partial progress
- out-of-order completions for sibling tasks

The properties to assert:

- no impossible task states
- no orphaned sandbox IDs after terminal completion
- cleanup is idempotent
- evaluation does not run before required outputs exist
- dashboard state never contradicts DB terminal state

The goal is compact, property-driven coverage, not giant random test files.

## Frontend Testing Strategy

The frontend should not rely on full live agent execution for most coverage.

Recommended split:

### Seeded-State Browser Tests

These are the default browser tests.

They:

- seed known run/task/action/evaluation state into Postgres
- start the app
- assert the UI reflects the seeded state correctly

This is the fastest and most trustworthy way to verify visualization correctness.

### Controlled-Event Browser Tests

These start from a seeded baseline and then inject or replay dashboard events.

They assert:

- progressive task status updates
- run completion transitions
- error rendering
- log and detail panel updates

### Tiny Live Browser Probes

Keep only a tiny number of truly live browser tests:

- create or observe one real run
- confirm it appears in the dashboard
- confirm it reaches a terminal state
- confirm the terminal state matches persisted DB state

## Suggested Test Layout

```text
tests/
├── state/
│   ├── test_task_persistence.py
│   ├── test_run_state_machine.py
│   ├── test_sandbox_lifecycle.py
│   └── test_evaluation_persistence.py
├── transcript/
│   ├── test_scripted_worker_paths.py
│   ├── test_recorded_model_runs.py
│   └── fixtures/
├── contracts/
│   ├── test_workflow_start_contract.py
│   ├── test_task_execute_contract.py
│   ├── test_workflow_complete_contract.py
│   └── test_dashboard_event_contracts.py
├── browser/
│   ├── test_run_graph.spec.ts
│   ├── test_live_updates.spec.ts
│   └── test_failure_rendering.spec.ts
├── live/
│   ├── test_e2b_probe.py
│   ├── test_provider_recording_refresh.py
│   └── test_full_stack_smoke.spec.ts
└── support/
    ├── scripted_model.py
    ├── recorded_model.py
    ├── fake_sandbox.py
    ├── run_transcript.py
    └── db_assertions.py
```

## Pytest Defaults And Markers

Recommended defaults:

- `pytest`
  - no live model requests
  - no live sandbox creation
  - deterministic only
- `pytest -m recorded`
  - replay model or provider recordings
- `pytest tests/browser`
  - run seeded or controlled-event browser tests
- `pytest -m live`
  - explicit live integrations only

Suggested markers:

- `recorded`
- `browser`
- `live`
- `sandbox_live`
- `provider_live`

## Representative Tests We Actually Want

### 1. Sandbox Create And Cleanup Contract

Use fake sandbox driver.

Assert:

- sandbox created once
- run stores sandbox ID
- cleanup clears sandbox ID
- cleanup emits close event
- registry is empty afterward

### 2. Worker Tool Sequence Contract

Use scripted model driver.

Assert:

- expected tools are called in expected order
- resulting `Action` rows contain the expected payloads
- final output persistence matches transcript

### 3. Workflow Completion Contract

Use deterministic task graph fixture.

Assert:

- parent task waits for children
- run final score is persisted
- finalization emits completion and cleanup follow-up

### 4. Failure Cleanup Contract

Inject a sandbox or tool failure.

Assert:

- run reaches failed state
- cleanup still executes
- sandbox ID is cleared
- dashboard reflects failure

### 5. Browser Run Graph Rendering

Seed a known workflow graph and action history.

Assert:

- UI graph nodes match persisted tasks
- statuses render correctly
- task detail panel shows expected action and evaluation data

### 6. One True Live Sandbox Probe

Run against E2B.

Assert:

- sandbox comes up
- a trivial file round-trip works
- cleanup succeeds

This should stay tiny and explicit.

### 7. Compact Property Test For Cleanup And State Invariants

Use fuzzed or parameterized inputs.

Assert:

- terminal runs never retain sandbox IDs
- cleanup can be repeated safely
- invalid event orderings do not produce impossible final state

This should replace many repetitive one-off tests.

## Recommended Implementation Order

### Phase 1: Establish The Harness

Build:

- `ScriptedModelDriver`
- `FakeSandboxDriver`
- `RunTranscript`
- shared DB assertion helpers

This phase should unlock most of the fast deterministic suite.

### Phase 2: Replace Slow E2E Coverage

Take the current `tests/e2e` intent and recast it as:

- state tests
- transcript tests
- contract tests

The goal is not to delete all E2E testing.

The goal is to stop using slow live orchestration as the default way to test correctness.

### Phase 3: Add Recordings

Add:

- provider-level VCR for selected OpenAI and Exa tests
- Arcane-native model transcript recordings for replayable integration tests

### Phase 4: Add Browser Layer

Add Playwright with:

- seeded-state tests first
- controlled-event tests second
- one live browser probe last

### Phase 5: Trim The Live Tip

Keep only the live probes that provide unique confidence.

Everything else should move to deterministic or recorded layers.

### Phase 6: Encode The Strategy For Agents

Because this repository is expected to be developed largely through chat-driven agents, the testing philosophy should also be encoded as repository guidance.

That guidance should live in:

- `CLAUDE.md`
  - repository-level development and testing defaults
- `.cursor/skills/arcane-testing/SKILL.md`
  - operational guidance for choosing the correct test layer
- `.cursor/rules/test-strategy.mdc`
  - concise always-on rule reinforcing the test matrix

These artifacts should teach agents:

- to default to test-driven development for non-trivial changes
- to prefer the smallest deterministic layer that proves the behavior
- to use recordings and seeded-state tests before live integrations
- to ask the user before deviating from the preferred test matrix

This is not just documentation polish.

It is part of the test architecture, because the agents doing implementation need a clear operational policy for where coverage should live and when broader testing is justified.

## Non-Goals

This strategy is not trying to:

- fully eliminate live integration tests
- mock every important system boundary forever
- avoid testing real provider integrations

It is trying to:

- make the default suite fast enough to run constantly
- make failures precise and actionable
- reserve live integration cost for the places where it truly buys confidence

## Success Criteria

We should consider this effort successful when:

- `pytest` runs quickly and without external credentials
- the default suite uses few mocks unless mocking is necessary for determinism or cost control
- most behavioral regressions are caught by deterministic tests
- the suite contains very few trivial tests that only cover obvious behavior
- sandbox lifecycle bugs are caught by direct state assertions
- browser regressions are caught by seeded-state Playwright tests
- smoke tests provide cheap health signals
- fuzz tests protect key invariants and lifecycle semantics
- tests stay compact relative to the amount of behavior they cover
- provider and sandbox breakage are still covered by a very small live probe layer
- the team no longer needs to rely on long-running benchmark E2E tests as the main correctness loop

## Recommended First Concrete Step

If we want to start small, the highest-leverage first slice is:

1. add `FakeSandboxDriver`
2. add `ScriptedModelDriver`
3. add `RunTranscript`
4. write `test_sandbox_lifecycle.py`
5. rewrite one current E2E path as a deterministic contract test

That single slice should show whether the new testing model feels materially better in day-to-day development.
