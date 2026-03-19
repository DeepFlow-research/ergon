# Sandbox Lifecycle Tests

This document defines the dedicated test strategy for sandbox-related behavior.

## Goal

Catch sandbox regressions through deterministic tests first, then a tiny real-E2B probe layer.

The most important thing this slice must prove is not just that "a sandbox exists."

It must prove that:

- tools are actually runnable in real containers
- the container has the dependencies, paths, and filesystem layout the tools assume
- final artifacts are downloaded from the correct container locations
- the state seen during rollout is compatible with the state later used for evaluation or reward modeling

If Arcane gets this boundary wrong, benchmark quality can collapse even when the orchestration layer appears healthy.

## Why Sandbox Tests Need Their Own Spec

Sandbox behavior is one of Arcane's most important external boundaries.

It affects:

- file inputs
- file outputs
- execution environment setup
- cleanup correctness
- run safety and cost

It is also the place where slow, flaky live tests are most tempting.

This document exists to keep most of that coverage deterministic.

## The Critical Boundary

The critical sandbox boundary is:

- "Can Arcane run the benchmark tools in a real container, persist the right container state, and later evaluate against the right outputs and environment assumptions?"

This boundary has several concrete failure modes that deserve first-class tests:

- the sandbox starts but required tool dependencies are missing
- benchmark-specific setup runs partially and leaves the container unusable
- tools write files successfully, but Arcane downloads the wrong files or the wrong directory
- rollout writes outputs in one container state, while evaluation assumes a different state or different path semantics
- final outputs exist in the container, but persistence links the wrong artifacts into PG
- cleanup hides or destroys evidence needed for evaluation, or leaves stale sandbox state that contaminates later runs

This document should therefore treat "tool execution in real containers" and "rollout/eval container parity" as primary contracts, not side details.

## Default Layer Split

### Deterministic Coverage

Lives primarily in:

- `tests/state/`
- `tests/contracts/`

Uses:

- `RealSandboxDriver`
- narrow sandbox fault injection around the real path
- real persistence
- transcript capture where helpful

Default rule:

- if the contract under test depends on container behavior, the sandbox should stay real
- use synthetic model behavior, not synthetic container behavior, as the main source of determinism

### Live Coverage

Lives in:

- `tests/live/`

Uses:

- real E2B
- minimal smoke-style probes only

Purpose:

- validate the vendor boundary itself
- catch failures that only appear when talking to live E2B infrastructure
- avoid turning every sandbox test into a slow live benchmark run

## Required Behaviors To Cover

### Sandbox Creation

Need tests for:

- create succeeds
- create stores sandbox ID
- create does not duplicate an existing sandbox for the same task when idempotency is intended
- create failure is surfaced correctly
- create records enough state for later output persistence and cleanup

### Directory And Path Setup

Need tests for:

- expected inputs and output paths
- workspace path creation
- path registration behavior
- created file registry behavior
- benchmark-specific tool directories exist where tools expect them
- rollout and evaluation path contracts are explicit and stable

### Tool Execution In Real Containers

Need tests for:

- benchmark tools execute successfully in a real sandbox container
- tools can access the dependencies installed during benchmark-specific setup
- tools can read expected input locations and write expected final-output locations
- failure is explicit when setup is incomplete or container dependencies are missing
- benchmark-specific commands that matter for evaluation behave the same way inside the container during deterministic tests as they do in production

This is one of the highest-signal areas in the entire sandbox suite.

It should prove things like:

- MiniF2F tools can actually use the Lean and Mathlib environment they depend on
- ResearchRubrics tools can actually read and modify files inside the container at the paths the runtime expects
- benchmark-specific skills are not only "called" but actually usable within the container filesystem and environment

### Input Uploads

Need tests for:

- single file upload
- multi-resource upload
- registry mapping from local path to sandbox path
- missing file handling where relevant
- uploaded inputs are visible to the tools that need them inside the container

### Output Download And Persistence

Need tests for:

- final output files downloaded correctly
- only final output area is considered for persistence
- missing output file behavior
- partial download failure behavior
- final persisted artifacts correspond to the actual files produced by tools inside the container
- scratchpad or tool-internal files do not get mistaken for final evaluation artifacts

### Rollout/Evaluation Container Parity

Need tests for:

- rollout writes the exact artifact shape that evaluation later expects
- evaluation reads the artifact from the same persisted file/path contract that rollout produced
- benchmark-specific verification or reward-model logic is not accidentally pointed at a different container path or stale artifact
- any required setup for evaluation uses the same effective container assumptions as rollout

Primary question:

- "Would a successful rollout artifact still be the artifact that reward modeling or evaluation sees?"

This is especially important for benchmarks where:

- tools write to a required final-output path
- evaluation inspects benchmark-specific files
- the evaluator uses a real or sandbox-backed environment to verify the result

### Timeout And Long-Run Semantics

Need tests for:

- timeout reset success
- timeout reset when sandbox is missing
- behavior when timeouts or not-found conditions occur during reads

### Teardown

Need tests for:

- normal termination
- teardown when sandbox already absent
- teardown when kill fails
- registry cleanup regardless of kill success
- teardown does not destroy or misplace the artifacts that were already persisted for evaluation

## Strongest Assertions

Every meaningful sandbox test should consider asserting:

- sandbox ID state on the run
- registry contents before and after cleanup
- uploaded and downloaded paths
- emitted sandbox lifecycle events
- absence of orphaned sandbox state after terminal completion
- exact container paths used by the tool under test
- exact persisted artifact selected for evaluation
- parity between rollout-produced output and evaluation-consumed output

## Strongest Tool-Execution Assertions

For the most important sandbox/tool tests, assert all of:

- the tool was executed against a real sandbox container, not a fake substitute
- the container setup steps required by the benchmark actually completed
- the tool output shows evidence of real execution, not just a mocked success payload
- the expected final artifact exists at the benchmark-defined final-output path
- the downloaded artifact bytes match the file that was present in the container
- the persisted `ResourceRecord` points at that final artifact and not a scratchpad or intermediate file
- the evaluation path, if present, consumes that same persisted artifact rather than reconstructing a different one

## Recommended Deterministic Test Set

### `test_create_persists_sandbox_id`

### `test_upload_inputs_registers_expected_paths`

### `test_download_all_outputs_only_reads_final_output_dir`

### `test_cleanup_clears_registry_even_if_kill_fails`

### `test_timeout_reset_returns_false_when_sandbox_missing`

### `test_terminal_run_never_retains_sandbox_id`

### `test_real_tool_executes_in_container_with_expected_dependencies`

Purpose:

- prove a benchmark-critical tool can actually run inside the real container setup, not merely be invoked

Suggested shape:

- MiniF2F variant:
  - create real sandbox
  - verify Lean/Mathlib setup
  - run a benchmark tool path such as write/check/verify on a minimal theorem artifact
- ResearchRubrics variant:
  - create real sandbox
  - run report write/edit/read flow against real container files

Assert:

- tool response indicates real execution success
- expected file exists in the container
- expected final output is downloadable
- no dependency/setup assumption was silently missing

### `test_rollout_output_is_the_same_artifact_evaluation_consumes`

Purpose:

- prove rollout/evaluation parity for sandbox-produced artifacts

Suggested shape:

- run a deterministic case with real sandbox behavior
- persist outputs
- run the evaluator or verification step against the persisted artifact

Assert:

- evaluation references the same persisted output resource created from rollout
- output names and file paths match benchmark expectations
- there is no mismatch between rollout final-output path and evaluator lookup behavior

### `test_missing_container_dependency_fails_loudly`

Purpose:

- catch the benchmark-killing class of failures where the sandbox exists but tools are unusable

Suggested shape:

- inject a narrow fault into benchmark setup or required path availability
- run the real tool path that depends on that setup

Assert:

- failure is explicit in action output or error state
- PG state records a real failure, not a silent degraded success
- cleanup still clears sandbox state

### `test_downloaded_final_output_matches_container_bytes`

Purpose:

- prove Arcane downloads the correct final artifact from the container

Suggested shape:

- write a distinctive final-output artifact inside the sandbox
- download outputs
- persist resource

Assert:

- downloaded file content matches the exact bytes written in the container
- the selected output came from `/workspace/final_output` or the benchmark-specific approved final path
- intermediate or scratchpad files are excluded

### `test_tool_internal_state_and_evaluator_state_use_same_path_contract`

Purpose:

- prove rollout and evaluation are not drifting onto different path conventions

Suggested shape:

- run a benchmark path where the tool writes a required output file
- run the corresponding evaluation/verification path

Assert:

- the evaluator looks at the same output contract the tool wrote
- success/failure changes if and only if that output artifact changes
- there is no hidden second source of truth for evaluation

## Live E2B Probe Set

Keep this tiny.

Recommended:

### `test_e2b_probe_create_upload_roundtrip_cleanup`

Assert:

- sandbox creates
- a trivial file round-trip works
- cleanup succeeds or reports a safe already-gone condition
- the probe proves we can execute a trivial command inside the real container, not just create and destroy it

### `test_e2b_probe_final_output_download`

Assert:

- writing into final output produces a retrievable artifact

### `test_e2b_probe_real_tool_environment`

Assert:

- a minimal benchmark-representative tool command can run in the live container
- the dependencies or paths that tool expects are actually present

Keep this probe tiny:

- it should validate the vendor/container boundary, not re-run the whole benchmark

Only keep this if it covers behavior not already proven by the first live probe.

## Anti-Patterns

Avoid:

- broad benchmark E2E runs as the main way to validate sandbox lifecycle
- live sandbox coverage for every tool path
- tests that assert only that no exception was thrown
- tests that only prove sandbox creation while never proving a real tool worked inside the container
- tests that verify rollout outputs without proving evaluator or reward-model parity
- tests that use fake container behavior for contracts that are really about real filesystem or dependency setup

## Acceptance Criteria

This slice is complete when:

- sandbox create, upload, output, timeout, and teardown behavior are covered deterministically
- cleanup invariants are strongly asserted
- only a tiny live E2B probe set remains necessary
- at least one benchmark-critical tool path is proven to execute correctly inside a real container
- the suite proves that rollout-produced outputs and evaluation-consumed outputs follow the same container and persistence contract
- container setup failures that would make tools unusable are caught by explicit tests rather than surfacing only as degraded benchmark scores later
