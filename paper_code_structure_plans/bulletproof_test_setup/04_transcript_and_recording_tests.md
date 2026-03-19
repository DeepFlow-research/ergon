# Transcript And Recording Tests

This document covers how Arcane should test model-facing behavior without defaulting to live provider calls.

## Goal

Make model-adjacent tests:

- deterministic by default
- realistic when needed
- compact
- strong on sequencing and contract assertions

## The Core Distinction

There are two different things to test:

1. Arcane behavior given a model interaction pattern
2. provider integration correctness

Most development work is the first category, not the second.

## `tests/transcript/`

This should be the main home for model-facing development tests.

Use it for:

- tool call sequencing
- retry or fallback behavior
- prompt-to-tool orchestration behavior
- transcript snapshots
- final output formation

## `RunTranscript` Requirements

Every transcript test should be able to assert:

- ordered model turns
- ordered tool calls and returns
- task status transitions
- sandbox lifecycle events if relevant
- output persistence events

Transcript assertions should support both:

- exact snapshots for narrow stable paths
- partial assertions for broader flows

## Scripted Model Tests

Use `ScriptedModelDriver` when:

- the exact tool sequence matters
- the branch behavior matters
- you want very fast local coverage

Typical tests:

- agent reads file then analyzes data
- agent asks stakeholder before proceeding
- agent retries once after tool error
- agent fails when given an impossible next step

Required assertions:

- tool call order
- arguments
- resulting persisted `Action` rows
- transcript integrity

## Benchmark-Specific Scripted Chains

Transcript tests should not rely on generic placeholder chains if the benchmark has a meaningful tool surface.

The first suite should define and reuse a small set of canonical benchmark-specific chains.

These should not all be the same size.

Use both:

- compact canonical chains
- longer toolkit-coverage chains

The longer chains are important because they give some interoperability coverage "for free" by exercising many tools in a realistic order.

### GDPEval canonical chain

Use a reduced document-processing case with a chain like:

1. `read_pdf`
2. `execute_python_code`
3. `create_docx`

Why:

- exercises file ingestion, sandbox code execution, and final artifact creation in one compact path

### GDPEval toolkit-coverage chain

Add at least one longer chain that uses most of:

- `ask_stakeholder`
- `read_pdf`
- `read_csv`
- `read_excel`
- `ocr_image`
- `execute_python_code`
- `create_csv`
- `create_excel`
- `create_docx`

This should be around:

- 8 to 10 tool calls

### MiniF2F canonical chain

Use a reduced proof-repair case with a chain like:

1. `write_lean_file`
2. `check_lean_file`
3. `search_lemmas`
4. `write_lean_file`
5. `verify_lean_proof`

Why:

- captures the iterative nature of proof authoring better than a one-shot happy path

### MiniF2F toolkit-coverage chain

Add at least one longer chain that uses:

- `ask_stakeholder`
- `search_lemmas`
- `write_lean_file`
- `check_lean_file`
- repeated refinement
- `verify_lean_proof`

This should be around:

- 7 to 10 tool calls

### ResearchRubrics canonical chain

Use a reduced research-synthesis case with a chain like:

1. `exa_search_tool`
2. `exa_get_content_tool`
3. `exa_get_content_tool`
4. `write_report_draft_tool`
5. `edit_report_draft_tool`
6. `read_report_draft_tool`

Why:

- captures retrieval, synthesis, editing, and final artifact validation in one compact path

### ResearchRubrics toolkit-coverage chain

Add at least one longer chain that uses most of:

- `ask_stakeholder_tool`
- `exa_search_tool`
- `exa_qa_tool`
- `exa_get_content_tool`
- `write_report_draft_tool`
- `edit_report_draft_tool`
- `read_report_draft_tool`

This should be around:

- 8 to 11 tool calls

### Clarification-first chain

For any benchmark where stakeholder interaction matters, add a chain like:

1. `ask_stakeholder`
2. benchmark-specific core tool sequence
3. final output write or verification

Why:

- Arcane cares about clarification behavior; tests should not ignore it entirely

## Recording Selection Rules

When choosing what to record or script, prefer scenarios that:

- map to real benchmark archetypes
- use actual tool names and output paths
- include at least one non-trivial branch, retry, or refinement step

Avoid recordings that are:

- pure toy prompts
- single-call happy paths with no meaningful sequencing
- so broad that they cover many unrelated behaviors at once

Avoid the opposite mistake too:

- making every scripted chain tiny enough that it never exercises multi-tool interoperability

The suite should contain a few longer benchmark-shaped chains on purpose.

## Recorded Model Tests

Use `RecordedModelDriver` when:

- prompt phrasing matters
- structured provider responses matter
- you want realistic behavior without a live call

Recording format should store Arcane-level request and response objects, not just provider HTTP.

Required behavior:

- deterministic replay
- readable diffs when behavior diverges
- easy regeneration by explicit command or fixture flow

## Provider-Level VCR

Use raw HTTP VCR only when validating provider boundaries:

- OpenAI request serialization
- Exa request compatibility
- authentication or SDK integration behavior

This is not the default for ordinary model-facing development tests.

## Test File Suggestions

```text
tests/transcript/
├── test_worker_tool_paths.py
├── test_retry_and_recovery.py
├── test_stakeholder_interaction.py
├── test_recorded_research_flow.py
└── fixtures/
    ├── model_recordings/
    └── transcript_snapshots/
```

## Assertions That Matter

Prefer:

- ordered transcript events
- exact tool names
- exact arguments when behavior depends on them
- persisted side effects
- final output structure

Avoid relying only on:

- free-form text matching
- "the worker completed"
- provider token counts unless the test is explicitly about them

## Anti-Patterns

Avoid:

- live model calls in ordinary transcript tests
- snapshots that include unstable, irrelevant noise
- giant recordings that cover many unrelated flows at once

Prefer:

- one recording per meaningful behavior
- small replay fixtures
- transcripts that fail clearly when the contract changes
- benchmark-shaped scripted chains rather than generic toy chains

## Acceptance Criteria

This slice is complete when:

- most worker and tool-sequencing regressions can be tested with scripted model behavior
- prompt-sensitive paths can be replayed without live provider calls
- provider compatibility remains separately covered through VCR or live tests where appropriate
