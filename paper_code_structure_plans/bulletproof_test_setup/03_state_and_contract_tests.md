# State And Contract Tests

This document specifies the benchmark-aware backend correctness suite that should replace most of the current slow E2E confidence loop.

It is the first major consumer of the harness defined in `02_deterministic_harness_and_drivers.md`.

## Goal

Use deterministic scripted benchmark runs plus real persistence to assert backend correctness through:

- exact Postgres state
- lifecycle transitions
- boundary contracts
- cleanup semantics

with:

- fake or recorded model behavior
- real sandbox behavior when sandbox semantics are involved
- transcript checks as secondary evidence, not the primary oracle

## Primary Oracle

For this suite, the primary source of truth is persisted Postgres state.

The key question is:

- "Given a deterministic benchmark-shaped run, did Arcane persist exactly the correct state and clean up correctly?"

Transcript assertions are still useful, but they are supporting evidence.

If there is a conflict between:

- a pretty transcript
- incorrect persisted state

the persisted state wins.

## Relationship To The Other Test Specs

- `02_deterministic_harness_and_drivers.md`
  - builds the harness, scripted model drivers, real sandbox driver, fixtures, and DB assertion helpers
- `03_state_and_contract_tests.md`
  - uses those harnesses to prove persisted correctness across benchmarks
- `04_transcript_and_recording_tests.md`
  - focuses on transcript integrity, tool sequencing, and recording behavior

## Two Primary Backend Layers

### `tests/state/`

Purpose:

- validate what the system stores and how it transitions

Best for:

- run status
- task status
- sandbox ID persistence and clearing
- output persistence
- evaluation aggregation
- idempotent cleanup
- benchmark-specific persisted outputs

### `tests/contracts/`

Purpose:

- validate interactions between orchestration runners and business services

Best for:

- event emission order
- DTO shapes
- boundary persistence semantics
- cleanup follow-up behavior
- dashboard event contracts

## Harness Coupling Requirement

`03` should explicitly use the deterministic harness from `02`.

That means:

- scripted or recorded model behavior drives the run
- real sandbox behavior is used when sandbox semantics are part of the contract
- the test finishes by asserting exact PG state

The first required coupling should be:

- a deterministic run with a real sandbox
- followed by exact DB assertions over the resulting terminal state

## Benchmark Scope

This suite should be benchmark-aware from the start.

It should define deterministic state and contract tests for:

- GDPEval
- MiniF2F
- ResearchRubrics

Each benchmark should have:

- at least one compact canonical happy-path case
- at least one meaningful failure-path case
- at least one toolkit-coverage case where the broader tool chain adds real signal

## Core Persisted Assertions

Every benchmark-backed state test should assert as many of these as are relevant.

### `Experiment`

Assert:

- correct `benchmark_name`
- correct task archetype or task description
- correct benchmark-specific metadata shape
- expected input-resource linkage where relevant

### `Run`

Assert:

- exact terminal status
- expected `error_message` or absence of error
- `e2b_sandbox_id` lifecycle, including clearing after cleanup
- expected final score if evaluation ran
- no inconsistent terminal state

### `Action`

Assert:

- exact action count
- exact action names in order
- key payload fields
- success or failure representation
- correct relation to run and task

### `ResourceRecord`

Assert:

- expected output files exist
- expected final output paths or names are represented
- scratchpad-only outputs do not masquerade as final outputs
- no required final output is missing

### `Evaluation` And `CriterionResult`

Assert:

- evaluation row exists when it should
- criterion results exist when they should
- aggregate scores are populated consistently
- failure states are captured correctly

### Cleanup Invariants

Assert:

- sandbox ID cleared on terminal runs
- cleanup remains idempotent
- no terminal run retains sandbox state
- no impossible task and run combination remains after cleanup

## Required State Test Domains

### Run State Machine

Need tests for:

- pending -> running -> completed
- pending -> running -> failed
- failure followed by cleanup
- repeated cleanup on an already terminal run

Primary assertions:

- final `Run.status`
- `error_message`
- `e2b_sandbox_id`
- terminal-state consistency

### Task State And Propagation

Need tests for:

- leaf task completion
- parent waits for children
- dependency gating
- failed child blocks parent completion where appropriate

Primary assertions:

- task statuses
- completion ordering
- parent/child semantics
- persisted task graph correctness where relevant

### Action Persistence

Need tests for:

- successful tool calls
- failed tool calls
- serialized payloads
- ordering of persisted actions

Primary assertions:

- action type
- payload content
- success or error representation
- relation to run and task

### Output Persistence

Need tests for:

- final outputs written to expected final-output paths
- missing-output behavior
- multi-artifact runs
- benchmark-specific output conventions

Primary assertions:

- output resource rows
- output filenames or paths
- output count and type expectations where relevant

### Evaluation Persistence

Need tests for:

- evaluation row creation
- criterion result creation
- score aggregation
- behavior when one criterion fails

Primary assertions:

- total score
- criterion counts
- failure capture
- relation to run

### Cleanup Invariants

Need tests for:

- cleanup after success
- cleanup after failure
- cleanup when sandbox is already absent
- cleanup when sandbox termination itself errors

Primary assertions:

- sandbox ID cleared
- terminal status preserved or corrected
- cleanup remains idempotent

## Required Contract Test Domains

### Workflow Start Contract

Validate:

- incoming request data becomes correct persisted run and experiment state
- initial follow-up events are emitted as expected
- any setup data needed by downstream execution is present

### Task Execute Contract

Validate:

- runner invokes the right service boundary
- task execution persistence happens once
- downstream events and follow-ups are emitted correctly

### Workflow Complete Contract

Validate:

- finalization aggregates state correctly
- dashboard completion event shape is correct
- cleanup follow-up is emitted
- persisted state and contract side effects agree

### Dashboard Event Contracts

Validate:

- event payload fields
- stable identifiers
- status mapping
- ordering expectations for consuming UI code

## Suggested File Layout

```text
tests/state/
├── test_gdpeval_state.py
├── test_minif2f_state.py
├── test_researchrubrics_state.py
├── test_sandbox_lifecycle.py
└── test_run_invariants.py

tests/contracts/
├── test_workflow_start_contract.py
├── test_task_execute_contract.py
├── test_workflow_complete_contract.py
└── test_dashboard_event_contracts.py
```

## Benchmark-Specific State Suites

### GDPEval state suite

Should include:

- one compact document-processing case
- one broader toolkit-coverage case
- one missing-final-output or similar failure case

Core PG assertions:

- expected artifact rows for DOCX, CSV, or XLSX outputs
- expected action ordering across input reading, Python execution, and artifact creation
- cleanup semantics after terminal completion

#### Fully specified golden state example: `gdpeval_pdf_to_docx_summary_case`

For the fixture defined in `02_deterministic_harness_and_drivers.md`:

- fixture name: `gdpeval_pdf_to_docx_summary_case`
- scripted action order:
  1. `ask_stakeholder`
  2. `read_pdf`
  3. `execute_python_code`
  4. `create_docx`

##### `Experiment` assertions

Assert:

- `benchmark_name == "gdpeval"`
- task description matches the fixture description
- any benchmark-specific task metadata expected by the fixture is persisted correctly

##### `Run` assertions

Assert:

- exactly one run exists for the fixture
- `Run.status == COMPLETED`
- `Run.e2b_sandbox_id is None` after cleanup
- `Run.error_message is None`
- `Run.started_at` is populated
- `Run.completed_at` is populated
- `Run.completed_at >= Run.started_at`
- `Run.questions_asked == 1`

Cost policy:

- use the same explicit deterministic-scripted-run policy as MiniF2F
- do not leave `Run.total_cost_usd` unasserted accidentally

##### `Action` assertions

Assert exactly 4 persisted action rows in this order:

1. `ask_stakeholder`
2. `read_pdf`
3. `execute_python_code`
4. `create_docx`

Assert key payload fields:

- `ask_stakeholder`
  - question asks whether the memo should be formal or concise
- `read_pdf`
  - `file_path == "/inputs/source.pdf"`
- `execute_python_code`
  - code contains the summary-generation snippet
- `create_docx`
  - `output_path == "/workspace/final_output/report.docx"`
  - `title == "Quarterly Memo"`
  - `template_style == "formal"`

Assert key response semantics:

- stakeholder output contains the scripted memo-style preference
- `read_pdf` persisted result indicates successful extraction
- `create_docx` persisted result indicates successful file creation

Assert action timing fields:

- every action has `started_at`
- every action has `completed_at`
- every action has `duration_ms`

##### `ResourceRecord` assertions

Assert:

- exactly one final output artifact exists for `report.docx`
- the output artifact is associated with the correct run
- no scratchpad artifact is counted as a final deliverable

##### Stakeholder trace assertions

Assert:

- exactly one worker-stakeholder thread exists for the run
- exactly two thread messages exist
- the first is the worker question
- the second is the stakeholder answer

##### `Evaluation` and `CriterionResult` assertions

If evaluation runs on this path, assert:

- one `Evaluation` row exists
- one or more `CriterionResult` rows exist
- scores are populated consistently

If evaluation is intentionally deferred for this exact path, assert the expected absence explicitly.

##### Failure twin

For the scratchpad-output failure variant, assert:

- `create_docx` may succeed technically, but no final output artifact is persisted for evaluation
- the run reaches the benchmark's expected non-success or gating behavior
- cleanup still clears sandbox state

### MiniF2F state suite

Should include:

- one iterative proof success case
- one verification failure case
- one broader toolkit-coverage case if it adds signal

Core PG assertions:

- expected Lean file outputs
- expected proof-checking and verification actions
- expected failed or completed terminal state
- cleanup semantics after verification success or failure

#### Fully specified golden state example: `minif2f_two_pass_proof_case`

`03` should not stop at saying "MiniF2F should have a proof success case."

It should specify at least one concrete golden fixture and the exact persisted state to assert for it.

For the fixture defined in `02_deterministic_harness_and_drivers.md`:

- fixture name: `minif2f_two_pass_proof_case`
- scripted action order:
  1. `ask_stakeholder` with a proof-strategy clarification
  2. `write_lean_file` to `/workspace/scratchpad/solution.lean`
  3. `check_lean_file` on `/workspace/scratchpad/solution.lean`
  4. `search_lemmas` with `#check nat.add_zero`
  5. `write_lean_file` to `/workspace/final_output/final_solution.lean`
  6. `verify_lean_proof` on `/workspace/final_output/final_solution.lean`

The corresponding PG assertions should be explicit.

##### `Experiment` assertions

Assert:

- `benchmark_name == "minif2f"`
- task description matches the fixture description
- benchmark-specific data contains the reduced theorem metadata if that is how the fixture is persisted

##### `Run` assertions

Assert:

- exactly one run exists for the fixture
- `Run.status == COMPLETED`
- `Run.e2b_sandbox_id is None` after cleanup
- `Run.error_message is None`
- `Run.started_at` is populated
- `Run.completed_at` is populated
- `Run.completed_at >= Run.started_at`
- `Run.questions_asked == 1`
- if evaluation runs on this path, `Run.final_score` is populated consistently with the evaluation row

Cost and token assertion policy must be explicit:

- if deterministic scripted runs do not synthesize cost, assert `Run.total_cost_usd is None`
- if deterministic scripted runs do synthesize cost, assert the exact expected value from the fixture spec

Do not leave cost assertions implicit.

##### `Action` assertions

Assert exactly 6 persisted action rows in this order:

1. `ask_stakeholder`
2. `write_lean_file`
3. `check_lean_file`
4. `search_lemmas`
5. `write_lean_file`
6. `verify_lean_proof`

Assert the key payload fields:

- `ask_stakeholder`
  - question asks whether a short direct proof is preferable
- first `write_lean_file`
  - `file_path == "/workspace/scratchpad/solution.lean"`
  - content includes `sorry`
- `check_lean_file`
  - `file_path == "/workspace/scratchpad/solution.lean"`
- `search_lemmas`
  - query contains `nat.add_zero`
- second `write_lean_file`
  - `file_path == "/workspace/final_output/final_solution.lean"`
  - content does not include `sorry`
- `verify_lean_proof`
  - `file_path == "/workspace/final_output/final_solution.lean"`

Assert the key response semantics:

- `ask_stakeholder` persisted output contains the scripted hint recommending a short direct proof if available
- `check_lean_file` persisted result indicates the draft was checked successfully
- `verify_lean_proof` persisted result indicates `verified=True`

Assert action timing fields:

- every action has `started_at`
- every action has `completed_at`
- every action has `duration_ms`
- for every action, `completed_at >= started_at`

Assert action cost fields according to the same explicit fixture policy:

- either action token and cost fields are all `None`
- or exact synthetic totals are asserted from the fixture spec

Do not leave these fields unasserted by accident.

##### `ResourceRecord` assertions

Assert:

- exactly one final output artifact exists for the proof file
- its persisted path or name corresponds to `final_solution.lean`
- the final artifact is associated with the correct run

Do not count the scratchpad file as a final output artifact.

##### Stakeholder trace assertions

Assert:

- exactly one `Thread` exists for the worker-stakeholder topic used by the toolkit
- exactly two `ThreadMessage` rows exist in that thread
- first message is the worker question
- second message is the stakeholder response
- both thread messages are associated with the correct run and experiment

If the benchmark path also persists top-level `Message` rows for this exchange, assert those explicitly as well.

##### `Evaluation` and `CriterionResult` assertions

If evaluation runs on this path, assert:

- one `Evaluation` row exists for the run
- one or more `CriterionResult` rows exist
- aggregate scores are populated

If the first implementation defers evaluation for this exact fixture, then the doc should say so explicitly and the test should assert the expected absence instead of leaving it ambiguous.

##### Cleanup assertions

Assert:

- no terminal run retains a sandbox ID
- cleanup left the run in a consistent completed state
- no impossible state remains after the final verification step

#### MiniF2F golden failure variant

For the failure twin of this fixture:

- keep the same overall sequence
- write a final proof that still contains `sorry`
- let `verify_lean_proof` persist `verified=False`

Then assert:

- `Run.status == FAILED` or the benchmark's chosen non-success terminal behavior, but the expected semantics must be explicit
- `Run.questions_asked == 1`
- `Run.started_at` and terminal timing fields are still populated
- `verify_lean_proof` action row persists the failed verification details
- final artifact may still exist, but it must not be treated as a verified success
- cleanup still clears sandbox state

### ResearchRubrics state suite

Should include:

- one compact search-and-report case
- one broader toolkit-coverage case
- one partial retrieval failure case

Core PG assertions:

- expected report artifact persistence
- expected retrieval and drafting action rows
- expected evaluation rows if evaluation is part of the path
- cleanup semantics after success or degraded success

#### Fully specified golden state example: `researchrubrics_search_synthesize_report_case`

For the fixture defined in `02_deterministic_harness_and_drivers.md`:

- fixture name: `researchrubrics_search_synthesize_report_case`
- scripted action order:
  1. `ask_stakeholder_tool`
  2. `exa_search_tool`
  3. `exa_qa_tool`
  4. `exa_get_content_tool`
  5. `exa_get_content_tool`
  6. `write_report_draft_tool`
  7. `edit_report_draft_tool`
  8. `read_report_draft_tool`

##### `Experiment` assertions

Assert:

- `benchmark_name == "researchrubrics"`
- task description matches the fixture description
- any benchmark-specific metadata expected by the fixture is persisted correctly

##### `Run` assertions

Assert:

- exactly one run exists for the fixture
- `Run.status == COMPLETED`
- `Run.e2b_sandbox_id is None` after cleanup
- `Run.error_message is None`
- `Run.started_at` is populated
- `Run.completed_at` is populated
- `Run.completed_at >= Run.started_at`
- `Run.questions_asked == 1`

Cost policy:

- use the same explicit deterministic-scripted-run policy as the other benchmark golden fixtures

##### `Action` assertions

Assert exactly 8 persisted action rows in this order:

1. `ask_stakeholder_tool`
2. `exa_search_tool`
3. `exa_qa_tool`
4. `exa_get_content_tool`
5. `exa_get_content_tool`
6. `write_report_draft_tool`
7. `edit_report_draft_tool`
8. `read_report_draft_tool`

Assert key payload fields:

- `ask_stakeholder_tool`
  - question asks whether to prioritize risks or opportunities
- `exa_search_tool`
  - query contains `AI chip supply chain concentration risks`
- `exa_qa_tool`
  - question asks for the main risks
- both `exa_get_content_tool` actions
  - URLs match the fixture URLs
- `write_report_draft_tool`
  - `file_path == "/workspace/final_output/report.md"`
- `edit_report_draft_tool`
  - old string contains `Initial draft:`
  - new string contains `Revised synthesis:`
- `read_report_draft_tool`
  - `file_path == "/workspace/final_output/report.md"`

Assert key response semantics:

- stakeholder output contains the scripted risk-prioritization guidance
- retrieval actions persist successful outputs
- final report read returns the edited markdown content

Assert action timing fields:

- every action has `started_at`
- every action has `completed_at`
- every action has `duration_ms`

##### `ResourceRecord` assertions

Assert:

- exactly one final output artifact exists for `report.md`
- the report artifact is associated with the correct run

##### Stakeholder trace assertions

Assert:

- exactly one worker-stakeholder thread exists for the run
- exactly two thread messages exist
- the first is the worker question
- the second is the stakeholder answer

##### `Evaluation` and `CriterionResult` assertions

If evaluation runs on this path, assert:

- one `Evaluation` row exists
- criterion rows exist
- score fields are populated consistently

##### Failure twin

For the partial retrieval failure variant, assert:

- one `exa_get_content_tool` action persists a failure or degraded response state
- a final markdown report still exists
- the run reaches the benchmark's expected degraded-success or failure semantics, but the expected behavior must be explicit
- cleanup still clears sandbox state

## First Required Test

The first concrete state test that should be built against the harness is:

- `tests/state/test_sandbox_lifecycle.py::test_real_sandbox_create_upload_cleanup`

It should prove:

- the harness can drive a deterministic run
- the real sandbox lifecycle works
- final persisted state in Postgres is exactly correct
- cleanup happens and clears sandbox state

This should be treated as the first proving ground for the `02` harness.

## Test Style Requirements

- prefer real DB persistence
- prefer scripted or recorded model behavior
- prefer real sandbox behavior when sandbox semantics are under test
- keep tests short and assertion-heavy
- avoid replicating runner internals in the test body
- make Postgres assertions the main oracle

## Example High-Value Tests

### `test_real_sandbox_create_upload_cleanup`

Proves:

- harness viability
- real sandbox lifecycle
- persisted output correctness
- cleanup correctness

### `test_sandbox_id_cleared_after_failed_run`

Proves:

- failure path
- cleanup semantics
- terminal state consistency

### `test_parent_task_does_not_complete_before_children`

Proves:

- dependency contract
- orchestration correctness

### `test_workflow_complete_emits_cleanup_followup`

Proves:

- completion side effects
- runner/service boundary correctness
- persisted state agrees with the contract

## Anti-Patterns

Avoid:

- tests that only assert a function returned a value when the real contract is persisted state
- tests that mock out persistence entirely for persistence-oriented behavior
- tests that duplicate orchestration steps line by line without asserting the resulting state or event contract
- treating transcript correctness as a substitute for persisted-state correctness

## Acceptance Criteria

This slice is complete when:

- the main run/task lifecycle paths are covered by deterministic benchmark-aware state tests
- cleanup invariants are covered in both success and failure modes
- each major benchmark has at least one strong PG-backed deterministic state suite
- the thick orchestration runners have contract tests around their main side effects
- the team can diagnose most backend regressions from state and contract failures alone
- deterministic benchmark state tests pass both individually and back-to-back within the same test session
- the deterministic state suite is expected to support concurrent execution of distinct benchmark cases over time, and any current limits on true concurrent execution are documented explicitly rather than being left as accidental global-state coupling
