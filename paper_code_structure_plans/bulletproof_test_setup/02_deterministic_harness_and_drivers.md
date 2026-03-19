# Deterministic Harness And Drivers

This document specifies the shared testing infrastructure that should exist before the broader suite is rewritten.

## Goal

Provide a default harness that lets tests run:

- without live model calls
- with real sandboxes by default when sandbox behavior is part of the contract
- without long polling
- with strong access to transcript and persisted state

## Deliverables

Build these shared support modules under a test support package such as:

```text
tests/
└── support/
    ├── scripted_model.py
    ├── recorded_model.py
    ├── sandbox_driver.py
    ├── sandbox_faults.py
    ├── run_transcript.py
    ├── db_assertions.py
    └── factories.py
```

Exact paths can change, but the capabilities should remain.

## Proposed Concrete Module Layout

The recommended first implementation should use these exact modules unless there is a strong reason to differ:

```text
tests/
├── conftest.py
├── support/
│   ├── __init__.py
│   ├── scripted_model.py
│   ├── recorded_model.py
│   ├── sandbox_driver.py
│   ├── sandbox_faults.py
│   ├── run_transcript.py
│   ├── harness.py
│   ├── db_assertions.py
│   ├── workflow_fixtures.py
│   └── seeded_state.py
├── state/
├── transcript/
└── contracts/
```

Purpose of each module:

- `scripted_model.py`
  - deterministic model behavior for most tests
- `recorded_model.py`
  - Arcane-level replay of recorded model interactions
- `sandbox_driver.py`
  - real sandbox wrapper with test ergonomics
- `sandbox_faults.py`
  - fault injection around real sandbox behavior
- `run_transcript.py`
  - transcript event models, recorder, and assertion helpers
- `harness.py`
  - the top-level test harness entrypoint and result object
- `db_assertions.py`
  - concise state assertion helpers
- `workflow_fixtures.py`
  - canonical test workflows and benchmark fixtures
- `seeded_state.py`
  - helpers for building persisted state for state and browser tests

## Proposed Public Interfaces

These do not need to match this text exactly, but the first implementation should stay close enough that an engineer can start building from this document.

### `tests/support/scripted_model.py`

```python
from typing import Any
from pydantic import BaseModel


class ToolCallStep(BaseModel):
    tool_name: str
    args: dict[str, Any]


class FinalTextStep(BaseModel):
    text: str


class FinalStructuredStep(BaseModel):
    payload: dict[str, Any]


class ScriptedModelDriver:
    def __init__(self, steps: list[ToolCallStep | FinalTextStep | FinalStructuredStep]): ...

    async def next_response(self, *, transcript, messages, available_tools) -> Any: ...
```

Behavior requirements:

- consume steps in order
- fail loudly on unexpected extra model turns
- validate that a referenced tool exists before returning a tool call
- append all model-visible behavior into the transcript

### `tests/support/recorded_model.py`

```python
from pathlib import Path


class RecordedModelDriver:
    def __init__(self, recording_path: Path): ...

    async def next_response(self, *, transcript, messages, available_tools) -> Any: ...
```

Behavior requirements:

- replay a pre-recorded Arcane-native interaction
- fail if the live code requests a turn not present in the recording
- expose a simple helper to regenerate or refresh recordings explicitly later

### `tests/support/sandbox_faults.py`

```python
from pydantic import BaseModel


class SandboxFaultPlan(BaseModel):
    fail_create: bool = False
    fail_terminate: bool = False
    missing_final_outputs: bool = False
    fail_upload_paths: set[str] | None = None
    fail_download_paths: set[str] | None = None
```

The first implementation should keep this intentionally small.

Add new fault knobs only when an actual test case needs them.

### `tests/support/sandbox_driver.py`

```python
from pathlib import Path
from uuid import UUID


class RealSandboxDriver:
    def __init__(self, fault_plan=None, transcript=None): ...

    async def create(self, *, task_id: UUID, run_id: UUID, skills_dir: Path | None, envs: dict[str, str] | None) -> str: ...
    async def upload_inputs(self, *, task_id: UUID, resources) -> None: ...
    async def upload_file(self, *, task_id: UUID, local_path: str, sandbox_path: str) -> None: ...
    async def list_files(self, *, task_id: UUID, sandbox_dir: str = "/workspace") -> list[str]: ...
    async def download_all_outputs(self, *, task_id: UUID, output_dir: Path): ...
    async def reset_timeout(self, *, task_id: UUID, timeout_minutes: int = 30) -> bool: ...
    async def terminate(self, *, task_id: UUID, reason: str = "completed") -> None: ...
```

Behavior requirements:

- use the real sandbox manager path underneath
- capture lifecycle events into the transcript
- allow narrow fault injection without forking the main code path
- expose enough state for assertions without hiding the real vendor boundary

Implementation note:

This should be a wrapper or adapter around the real sandbox lifecycle, not a parallel sandbox implementation.

### `tests/support/run_transcript.py`

```python
from typing import Any
from pydantic import BaseModel


class TranscriptEvent(BaseModel):
    kind: str
    payload: dict[str, Any]


class RunTranscript:
    def __init__(self): ...

    def append(self, kind: str, **payload) -> None: ...
    def events_of_kind(self, kind: str) -> list[TranscriptEvent]: ...
    def contains(self, kind: str) -> bool: ...
    def to_snapshot(self) -> list[dict[str, Any]]: ...
```

The first version should optimize for:

- stable ordering
- readability in failing assertions
- easy partial matching

### `tests/support/harness.py`

```python
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session


class ArcaneTestResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    experiment_id: str
    transcript: object
    db_session: Session


async def run_arcane_test(
    *,
    task,
    model_driver,
    sandbox_driver=None,
    db_session: Session,
) -> ArcaneTestResult: ...
```

The exact task input can be a task tree, workflow fixture, or persisted experiment fixture depending on implementation convenience.

The key is that the first harness should:

- run without long polling
- return transcript plus DB access
- stay narrow and deterministic

## Fixture Strategy

The first implementation should not start from benchmark-sized fixtures.

Create a small set of canonical fixtures in `workflow_fixtures.py`:

- `single_task_workflow()`
- `linear_workflow()`
- `parallel_workflow()`
- `failure_cleanup_workflow()`

And a small set of data fixtures in `seeded_state.py`:

- `seed_run_with_success()`
- `seed_run_with_failure()`
- `seed_run_with_evaluation()`

These should be compact and deliberately reusable across:

- state tests
- transcript tests
- contract tests
- later browser tests

## Canonical Benchmark Fixture Corpus

The first implementation should not stop at generic workflow shapes like `single_task_workflow()`.

It should also define a small benchmark-aware fixture corpus so scripted model tests use representative, high-signal scenarios instead of toy prompts.

These fixtures should live alongside `workflow_fixtures.py`, either in that module or a sibling such as:

```text
tests/support/benchmark_fixtures.py
```

Each fixture should specify:

- benchmark name
- task archetype
- minimal input resources
- canonical scripted model chain
- expected persisted actions
- expected final outputs
- one or two meaningful failure variants

### Fixture Design Rule

Use the smallest scenario that still exercises:

- the benchmark's real tool surface
- the benchmark's real file and output semantics
- at least one non-trivial failure or retry path where appropriate

Do not invent synthetic prompts that have little relation to real benchmark behavior.

Prefer:

- reduced real benchmark examples
- benchmark-shaped tasks with minimal but realistic files
- stable handcrafted fixtures that mirror genuine workflows

## Fixture Tiers

The fixture corpus should be intentionally tiered.

Do not make every fixture equally long.

Instead, define three classes of fixtures:

### Tier 1: compact canonical fixtures

Purpose:

- prove one core benchmark archetype cleanly

Typical length:

- 3 to 6 tool calls

Use for:

- narrow transcript tests
- state and contract tests
- failure variants with very explicit assertions

### Tier 2: toolkit-coverage fixtures

Purpose:

- exercise a large fraction of a benchmark toolkit in one realistic chain

Typical length:

- 6 to 12 tool calls

Use for:

- high-signal integration-style transcript tests
- "did this benchmark toolkit still basically work end to end?" checks
- catching regressions in tool interoperability, output conventions, and path handling

These are the fixtures that should feel more like near-end-to-end benchmark walkthroughs.

### Tier 3: property and fuzz seeds

Purpose:

- act as seeds for generated permutations, retries, partial failures, and ordering variants

Typical length:

- start from a Tier 1 or Tier 2 fixture and vary key branch points

Use for:

- property tests
- failure injection
- sequencing and idempotency coverage

## Coverage Principle

At least a couple of fixtures across the suite should be long toolkit-coverage chains.

For each major benchmark, the fixture corpus should aim to collectively exercise almost every tool in the toolkit.

Important nuance:

- not every tool needs to appear in one giant chain
- but the benchmark's canonical fixture set should collectively cover nearly the whole toolkit surface

That gives some "fuzz for free" through realistic tool interaction coverage, while still keeping individual tests understandable.

### Proposed Pydantic Fixture Shape

```python
from typing import Any, Literal
from pydantic import BaseModel


class BenchmarkFixtureSpec(BaseModel):
    name: str
    benchmark_name: Literal["gdpeval", "minif2f", "researchrubrics"]
    task_archetype: str
    task_description: str
    input_files: dict[str, str]
    scripted_steps: list[Any]
    expected_action_names: list[str]
    expected_output_paths: list[str]
    notes: list[str] = []
```

The first version can keep `scripted_steps` loose and typed later once the scripted model API settles.

## Required Canonical Fixtures

The first harness implementation should define at least one high-signal happy-path fixture per major benchmark and at least one failure-oriented variant where it adds meaningful coverage.

### GDPEval: document extraction to artifact creation

Suggested fixture name:

- `gdpeval_pdf_to_docx_summary_case()`

Task archetype:

- read a document-like input and produce a structured deliverable

Minimal inputs:

- one small PDF fixture with extractable text
- optionally one small CSV if the scenario needs tabular reasoning

Canonical scripted chain:

1. `read_pdf(file_path="/inputs/source.pdf")`
2. `execute_python_code(code="...summarize or transform extracted content...")`
3. `create_docx(content=[...], output_path="/workspace/final_output/report.docx")`

Expected persisted actions:

- `read_pdf`
- `execute_python_code`
- `create_docx`

Why this is high-signal:

- covers input reading
- covers sandbox code execution
- covers final artifact generation
- covers final output path semantics

Good failure variant:

- python step succeeds but final artifact is missing from `/workspace/final_output`

That variant should prove:

- evaluation or persistence gating behaves correctly
- missing outputs are surfaced cleanly

#### Fully specified golden example: `gdpeval_pdf_to_docx_summary_case()`

This should be the first fully specified GDPEval golden fixture.

It is strong because it exercises:

- stakeholder clarification
- PDF ingestion
- sandbox Python execution
- final DOCX artifact creation

Suggested fixture spec:

```python
BenchmarkFixtureSpec(
    name="gdpeval_pdf_to_docx_summary_case",
    benchmark_name="gdpeval",
    task_archetype="pdf-summary-to-docx",
    task_description=(
        "Read a short PDF brief, summarize the key findings, and produce a "
        "formal DOCX memo in final_output."
    ),
    input_files={
        "/inputs/source.pdf": "small fixture PDF with extractable text",
    },
    scripted_steps=[
        ToolCallStep(
            tool_name="ask_stakeholder",
            args={"question": "Should the final memo be formal or concise?"},
        ),
        ToolCallStep(
            tool_name="read_pdf",
            args={"file_path": "/inputs/source.pdf"},
        ),
        ToolCallStep(
            tool_name="execute_python_code",
            args={
                "code": (
                    "summary = 'Key findings: revenue up 12%, costs stable, risk concentrated in Q4.'\\n"
                    "print(summary)"
                )
            },
        ),
        ToolCallStep(
            tool_name="create_docx",
            args={
                "content": (
                    "# Quarterly Memo\\n\\n"
                    "Key findings: revenue up 12%, costs stable, risk concentrated in Q4."
                ),
                "output_path": "/workspace/final_output/report.docx",
                "title": "Quarterly Memo",
                "template_style": "formal",
            },
        ),
        FinalTextStep(text="Memo written to final_output/report.docx"),
    ],
    expected_action_names=[
        "ask_stakeholder",
        "read_pdf",
        "execute_python_code",
        "create_docx",
    ],
    expected_output_paths=["/workspace/final_output/report.docx"],
    notes=[
        "The stakeholder answer should prefer a formal memo style.",
        "Cost fields should follow the scripted-run policy used across deterministic fixtures.",
    ],
)
```

Suggested scripted stakeholder answer:

- `"Use a formal memo style with one short findings section."`

Required first failure variant:

- keep the same chain, but write the DOCX to `/workspace/scratchpad/report.docx`
- then assert that no final output artifact is persisted for evaluation

### ResearchRubrics: search, synthesis, and report drafting

### GDPEval: toolkit-coverage chain

Suggested fixture name:

- `gdpeval_toolkit_sweep_case()`

Intent:

- cover most of the GDPEval toolkit in one realistic chain

Target chain length:

- 8 to 10 tool calls

Suggested scripted chain:

1. `ask_stakeholder(question="Which output formats matter most?")`
2. `read_pdf(file_path="/inputs/brief.pdf")`
3. `read_csv(file_path="/inputs/data.csv", max_rows=50)`
4. `read_excel(file_path="/inputs/supporting_metrics.xlsx", sheet_name="Sheet1")`
5. `ocr_image(file_path="/inputs/chart.png")`
6. `execute_python_code(code="...merge extracted evidence into a normalized table...")`
7. `create_csv(data=[...], output_path="/workspace/scratchpad/normalized.csv")`
8. `create_excel(sheets=[...], output_path="/workspace/final_output/analysis.xlsx")`
9. `create_docx(content=[...], output_path="/workspace/final_output/report.docx")`

Coverage notes:

- this should hit nearly every non-stakeholder GDPEval tool
- it should validate that multiple input types can coexist in one run
- it should validate both scratchpad and final-output semantics

### GDPEval: spreadsheet-style artifact generation

Suggested fixture name:

- `gdpeval_csv_to_excel_case()`

Canonical scripted chain:

1. `read_csv(file_path="/inputs/table.csv", max_rows=50)`
2. `execute_python_code(code="...aggregate metrics...")`
3. `create_excel(sheets=[...], output_path="/workspace/final_output/result.xlsx")`

Use this fixture only if it materially adds file-format coverage not already captured by the PDF-to-DOCX case.

### MiniF2F: proof authoring with verification loop

Suggested fixture name:

- `minif2f_two_pass_proof_case()`

Task archetype:

- write an initial proof attempt, inspect failure, refine, then verify

Minimal inputs:

- one reduced Lean problem statement fixture

Canonical scripted chain:

1. `write_lean_file(file_path="/workspace/scratchpad/solution.lean", content="initial proof")`
2. `check_lean_file(file_path="/workspace/scratchpad/solution.lean")`
3. `search_lemmas(query="relevant lemma query")`
4. `write_lean_file(file_path="/workspace/final_output/final_solution.lean", content="revised proof")`
5. `verify_lean_proof(file_path="/workspace/final_output/final_solution.lean")`

Expected persisted actions:

- `write_lean_file`
- `check_lean_file`
- `search_lemmas`
- `write_lean_file`
- `verify_lean_proof`

Why this is high-signal:

- covers iterative authoring
- covers an actual correction loop
- covers final-output semantics
- covers proof verification instead of only syntax checking

Good failure variant:

- initial file checks but final verification fails

That variant should prove:

- failure handling around benchmark-specific verification
- cleanup and terminal-state semantics

#### Fully specified golden example: `minif2f_two_pass_proof_case()`

This should be the first benchmark fixture that is written down almost completely, because it is a good example of:

- a real benchmark-shaped workflow
- a non-trivial refinement loop
- a final artifact with strict path semantics
- benchmark-specific verification behavior
- a scripted stakeholder clarification trace

Suggested fixture spec:

```python
BenchmarkFixtureSpec(
    name="minif2f_two_pass_proof_case",
    benchmark_name="minif2f",
    task_archetype="iterative-proof-repair",
    task_description=(
        "Prove a small Lean theorem by writing an initial attempt, checking it, "
        "searching for a relevant lemma, refining the proof, and verifying the final file."
    ),
    input_files={
        "/inputs/problem.txt": (
            "Theorem: forall n : nat, n + 0 = n\\n"
            "Write the final proof to /workspace/final_output/final_solution.lean"
        ),
    },
    scripted_steps=[
        ToolCallStep(
            tool_name="ask_stakeholder",
            args={"question": "Should I prefer a short direct proof if one exists?"},
        ),
        ToolCallStep(
            tool_name="write_lean_file",
            args={
                "file_path": "/workspace/scratchpad/solution.lean",
                "content": (
                    "import data.nat.basic\\n\\n"
                    "theorem add_zero_test (n : nat) : n + 0 = n := by\\n"
                    "  sorry\\n"
                ),
            },
        ),
        ToolCallStep(
            tool_name="check_lean_file",
            args={"file_path": "/workspace/scratchpad/solution.lean"},
        ),
        ToolCallStep(
            tool_name="search_lemmas",
            args={"query": "#check nat.add_zero"},
        ),
        ToolCallStep(
            tool_name="write_lean_file",
            args={
                "file_path": "/workspace/final_output/final_solution.lean",
                "content": (
                    "import data.nat.basic\\n\\n"
                    "theorem add_zero_test (n : nat) : n + 0 = n := by\\n"
                    "  exact nat.add_zero n\\n"
                ),
            },
        ),
        ToolCallStep(
            tool_name="verify_lean_proof",
            args={"file_path": "/workspace/final_output/final_solution.lean"},
        ),
        FinalTextStep(text="Proof verified and final solution written."),
    ],
    expected_action_names=[
        "ask_stakeholder",
        "write_lean_file",
        "check_lean_file",
        "search_lemmas",
        "write_lean_file",
        "verify_lean_proof",
    ],
    expected_output_paths=["/workspace/final_output/final_solution.lean"],
    notes=[
        "First draft intentionally contains sorry to exercise the refinement loop.",
        "Final proof must live in final_output to be evaluated.",
        "The scripted stakeholder answer should recommend a short direct proof if available.",
    ],
)
```

Key reasons this fixture is strong:

- it uses real MiniF2F tool names
- it exercises both scratchpad and final-output file semantics
- it includes an intermediate diagnostic step rather than a one-shot proof
- it produces a single final artifact that is easy to assert in PG
- it exercises the stakeholder communication path in a benchmark-shaped way

Suggested scripted stakeholder answer:

- `"Yes. Prefer a short direct proof if a standard lemma closes the theorem cleanly."`

Runtime and cost policy for this fixture:

- `Run.started_at` must be populated
- `Run.completed_at` must be populated on terminal completion
- each persisted `Action` should have `started_at`, `completed_at`, and `duration_ms`
- `Run.questions_asked` should equal `1`
- token and cost fields must not be left ambiguous:
  - either the scripted harness explicitly populates synthetic token and cost values and the fixture should specify them exactly
  - or the scripted harness treats cost as unavailable and the test should explicitly assert `total_cost_usd is None` and message or action token fields are `None`

The first implementation should choose one of those policies and document it consistently across all deterministic scripted fixtures.

Required first failure variant:

- keep the same chain, but write a final file that still contains `sorry`
- then `verify_lean_proof` should report `verified=False`

That failure fixture should share as much structure as possible with the happy-path fixture so regressions are easy to compare.

### MiniF2F: toolkit-coverage chain

Suggested fixture name:

- `minif2f_iterative_proof_sweep_case()`

Intent:

- use the full MiniF2F toolkit in a realistic iterative loop

Target chain length:

- 7 to 10 tool calls

Suggested scripted chain:

1. `ask_stakeholder(question="Should I optimize for readability or terseness?")`
2. `search_lemmas(query="initial theorem search")`
3. `write_lean_file(file_path="/workspace/scratchpad/attempt1.lean", content="initial draft")`
4. `check_lean_file(file_path="/workspace/scratchpad/attempt1.lean")`
5. `search_lemmas(query="follow-up lemma search after error")`
6. `write_lean_file(file_path="/workspace/scratchpad/attempt2.lean", content="refined draft")`
7. `check_lean_file(file_path="/workspace/scratchpad/attempt2.lean")`
8. `write_lean_file(file_path="/workspace/final_output/final_solution.lean", content="final proof")`
9. `verify_lean_proof(file_path="/workspace/final_output/final_solution.lean")`

Coverage notes:

- this should use every major MiniF2F tool
- it should validate repeated author-check-refine loops, not just one-pass proof generation

### ResearchRubrics: search, synthesis, and report drafting

Suggested fixture name:

- `researchrubrics_search_synthesize_report_case()`

Task archetype:

- perform search, fetch content, draft a report, revise it, and read it back

Minimal inputs:

- no large local input files required
- deterministic recorded or scripted search returns

Canonical scripted chain:

1. `exa_search_tool(query="benchmark topic", num_results=3, include_domains=None)`
2. `exa_get_content_tool(url="https://example.com/source-1")`
3. `exa_get_content_tool(url="https://example.com/source-2")`
4. `write_report_draft_tool(content="initial synthesis", output_path="/workspace/final_output/report.md")`
5. `edit_report_draft_tool(target_path="/workspace/final_output/report.md", instructions="tighten and cite")`
6. `read_report_draft_tool(file_path="/workspace/final_output/report.md")`

Expected persisted actions:

- `exa_search_tool`
- `exa_get_content_tool`
- `exa_get_content_tool`
- `write_report_draft_tool`
- `edit_report_draft_tool`
- `read_report_draft_tool`

Why this is high-signal:

- covers multi-source retrieval
- covers synthesis flow
- covers in-place draft editing
- covers final artifact readability

Good failure variant:

- search succeeds but one content fetch fails, followed by degraded but valid reporting behavior

That variant should prove:

- partial failure tolerance
- report-path behavior under incomplete evidence

#### Fully specified golden example: `researchrubrics_search_synthesize_report_case()`

This should be the first fully specified ResearchRubrics golden fixture.

It is strong because it exercises:

- stakeholder clarification
- search and retrieval
- question-answer style synthesis
- report drafting and editing in final output

Suggested fixture spec:

```python
BenchmarkFixtureSpec(
    name="researchrubrics_search_synthesize_report_case",
    benchmark_name="researchrubrics",
    task_archetype="research-synthesis-report",
    task_description=(
        "Research a focused topic, gather two sources, synthesize the evidence, "
        "and produce a concise markdown report."
    ),
    input_files={},
    scripted_steps=[
        ToolCallStep(
            tool_name="ask_stakeholder_tool",
            args={"question": "Should the report prioritize risks or opportunities?"},
        ),
        ToolCallStep(
            tool_name="exa_search_tool",
            args={
                "query": "AI chip supply chain concentration risks 2025",
                "num_results": 3,
                "category": "news",
            },
        ),
        ToolCallStep(
            tool_name="exa_qa_tool",
            args={
                "question": "What are the main risks in AI chip supply concentration?",
                "num_results": 3,
            },
        ),
        ToolCallStep(
            tool_name="exa_get_content_tool",
            args={"url": "https://example.com/source-1"},
        ),
        ToolCallStep(
            tool_name="exa_get_content_tool",
            args={"url": "https://example.com/source-2"},
        ),
        ToolCallStep(
            tool_name="write_report_draft_tool",
            args={
                "content": (
                    "# Supply Chain Risk Report\\n\\n"
                    "Initial draft: concentration risk is high due to limited foundry capacity."
                ),
                "file_path": "/workspace/final_output/report.md",
            },
        ),
        ToolCallStep(
            tool_name="edit_report_draft_tool",
            args={
                "old_string": "Initial draft:",
                "new_string": "Revised synthesis:",
                "file_path": "/workspace/final_output/report.md",
            },
        ),
        ToolCallStep(
            tool_name="read_report_draft_tool",
            args={"file_path": "/workspace/final_output/report.md"},
        ),
        FinalTextStep(text="Research report completed in final_output/report.md"),
    ],
    expected_action_names=[
        "ask_stakeholder_tool",
        "exa_search_tool",
        "exa_qa_tool",
        "exa_get_content_tool",
        "exa_get_content_tool",
        "write_report_draft_tool",
        "edit_report_draft_tool",
        "read_report_draft_tool",
    ],
    expected_output_paths=["/workspace/final_output/report.md"],
    notes=[
        "The stakeholder answer should prioritize risk emphasis.",
        "The final report should remain a markdown artifact in final_output.",
    ],
)
```

Suggested scripted stakeholder answer:

- `"Prioritize risks, but include one short paragraph on upside so the report stays balanced."`

Required first failure variant:

- keep the same chain, but make one `exa_get_content_tool` call fail
- still require a final markdown report
- assert degraded but valid persisted state rather than total collapse

### ResearchRubrics: toolkit-coverage chain

Suggested fixture name:

- `researchrubrics_full_research_sweep_case()`

Intent:

- use nearly the entire ResearchRubrics toolkit in one realistic research flow

Target chain length:

- 8 to 11 tool calls

Suggested scripted chain:

1. `ask_stakeholder_tool(question="Which angle should the report prioritize?")`
2. `exa_search_tool(query="primary topic search", num_results=5, include_domains=None)`
3. `exa_qa_tool(question="What are the main debates on this topic?")`
4. `exa_get_content_tool(url="https://example.com/source-1")`
5. `exa_get_content_tool(url="https://example.com/source-2")`
6. `write_report_draft_tool(content="first draft", output_path="/workspace/final_output/report.md")`
7. `read_report_draft_tool(file_path="/workspace/final_output/report.md")`
8. `edit_report_draft_tool(target_path="/workspace/final_output/report.md", instructions="add synthesis and caveats")`
9. `read_report_draft_tool(file_path="/workspace/final_output/report.md")`

Coverage notes:

- this should use almost the entire toolkit surface
- it should validate both retrieval and iterative editing semantics

### Stakeholder interaction fixture

Suggested fixture name:

- `clarification_then_execute_case()`

Benchmark applicability:

- use wherever stakeholder interaction is genuinely part of the benchmark behavior

Canonical scripted chain:

1. `ask_stakeholder(...)`
2. benchmark-specific tool sequence
3. final output write

This should exist because question-asking is one of Arcane's core behavioral concerns.

## Toolkit Coverage Requirement

The fixture corpus should be evaluated with an explicit coverage checklist.

For each benchmark toolkit, track:

- which tools appear in Tier 1 canonical fixtures
- which tools appear in Tier 2 toolkit-coverage fixtures
- which tools only appear in fault or fuzz variants

The target should be:

- Tier 1 fixtures remain compact and readable
- Tier 2 fixtures collectively exercise almost every tool in each benchmark toolkit
- no important tool is left completely unrepresented in the deterministic fixture corpus

## Fixture Quality Bar

A canonical benchmark fixture is acceptable only if:

- it uses actual benchmark tool names
- it exercises the benchmark's real output conventions
- it resembles a real benchmark task archetype
- it would catch a plausible regression that a toy prompt would miss

If a fixture could be swapped with an arbitrary fake prompt and still test the same thing, it is probably too weak.

## Harness Lifecycle

The first harness should follow this lifecycle:

1. create or persist the workflow and run
2. attach transcript recorder
3. attach scripted or recorded model driver
4. attach real sandbox driver only if sandbox behavior is involved
5. invoke service or runner directly
6. return result object with transcript and DB access

The harness should not:

- hide persistence
- auto-retry silently
- swallow sandbox failures
- mix live model behavior into deterministic tests

## Canonical First Tests

The first implementation should explicitly aim to make these tests possible.

### 1. `tests/state/test_sandbox_lifecycle.py::test_real_sandbox_create_upload_cleanup`

Purpose:

- prove real sandbox lifecycle works in the deterministic harness

Assert:

- sandbox ID is stored on the run
- uploaded inputs land in expected paths
- final output download works
- cleanup clears sandbox ID
- transcript includes sandbox create and close events

### 2. `tests/state/test_sandbox_lifecycle.py::test_cleanup_still_clears_state_when_terminate_fails`

Purpose:

- prove teardown failure does not leave inconsistent state

Setup:

- real sandbox path plus `SandboxFaultPlan(fail_terminate=True)`

Assert:

- cleanup path executes
- sandbox ID is cleared from persisted run state
- transcript records the failure and close attempt

### 3. `tests/transcript/test_worker_tool_path.py::test_scripted_model_tool_sequence_is_persisted`

Purpose:

- prove deterministic model sequencing drives persisted actions correctly

Assert:

- tool calls occur in expected order
- action rows are persisted in the same order
- transcript matches expected event flow

### 4. `tests/contracts/test_workflow_complete_contract.py::test_workflow_complete_emits_cleanup_followup`

Purpose:

- prove the contract around workflow finalization and cleanup

Assert:

- final run state is correct
- cleanup follow-up occurs
- transcript and DB state agree

### 5. `tests/state/test_run_invariants.py::test_terminal_run_never_retains_sandbox_id`

Purpose:

- prove a core lifecycle invariant in compact form

Assert:

- completed runs do not retain sandbox IDs
- failed runs do not retain sandbox IDs after cleanup

## Recommended Build Order For This Doc

An engineer implementing this spec should build in this order:

1. `run_transcript.py`
2. `db_assertions.py`
3. `scripted_model.py`
4. `sandbox_faults.py`
5. `sandbox_driver.py`
6. `workflow_fixtures.py`
7. `harness.py`
8. the five canonical tests above

This order keeps the first slice small while still proving that the harness architecture actually works.

## Required Primitives

### `ScriptedModelDriver`

Purpose:

- deterministic replacement for live model behavior
- explicit control over tool call order and final outputs

Required capabilities:

- define a sequence of tool calls
- define final text or structured output
- fail if the system asks for an unexpected next step
- record all model turns into the transcript

Test value:

- worker behavior
- tool sequencing
- retry and fallback logic
- task completion logic

### `RecordedModelDriver`

Purpose:

- replay previously captured Arcane-native model interactions

Required capabilities:

- load a recording file
- replay model turns deterministically
- fail if the live code diverges from the recorded interaction shape
- expose the replay in transcript form

Test value:

- realistic model behavior without live provider dependence
- regression coverage for prompt-facing paths

### `RealSandboxDriver`

Purpose:

- real sandbox execution with test-oriented ergonomics and transcript capture

Why this should be the default:

- sandboxes are cheap enough to use in ordinary tests
- sandbox state is itself a major failure mode
- filesystem behavior, tool availability, path handling, and teardown semantics are too important to replace casually
- a fake sandbox would risk validating the fake instead of the contract with E2B and the real runtime environment

Required capabilities:

- create real sandboxes
- capture sandbox IDs and lifecycle events
- expose uploaded files and output paths for assertions
- expose command execution outcomes for assertions
- expose timeout reset behavior
- support deterministic test setup inside the sandbox
- support transcript capture around sandbox lifecycle

Test value:

- validates real filesystem layout
- validates real tool and package availability
- validates real path and output semantics
- validates real teardown behavior across the vendor boundary

### `SandboxFaultInjector`

Purpose:

- inject narrow failure modes around the real sandbox path without replacing the whole sandbox with a fake implementation

Required capabilities:

- fail create before sandbox startup when needed
- simulate teardown failure after real or synthetic sandbox allocation
- force missing-output scenarios
- force selected upload or download errors
- expose lifecycle events into the transcript

Test value:

- failure-path testing without abandoning the real sandbox contract
- narrow fault injection for rare or hard-to-trigger cases

### `RunTranscript`

Purpose:

- first-class test artifact for execution history

Required contents:

- run metadata
- task state transitions
- model turns
- tool calls and tool returns
- sandbox create and close events
- persisted output events
- evaluation events
- dashboard emission events

Required ergonomics:

- easy snapshotting
- easy partial assertions
- predictable ordering

### Shared DB Assertion Helpers

Purpose:

- make state assertions concise and high-signal

Required helpers:

- fetch run plus related tasks/actions/evaluations
- assert run status
- assert sandbox ID present or cleared
- assert action payloads
- assert evaluation and criterion results
- assert no orphaned resources or inconsistent terminal state

## Harness Shape

Tests should be able to do something conceptually like:

```python
result = run_arcane_test(
    workflow=fixtures.parallel_workflow(),
    model=ScriptedModelDriver([...]),
    sandbox=RealSandboxDriver(...),
)

assert_run_completed(result)
assert_sandbox_cleared(result)
assert_action_names(result, ["read_file", "analyze_data"])
assert result.transcript.contains("SandboxClosed")
```

The exact API can differ, but it should stay:

- compact
- explicit
- deterministic

Determinism here should come primarily from:

- scripted or recorded model behavior
- fixed workflow fixtures
- controlled sandbox setup inputs
- explicit assertions over persisted state and transcript events

## What The Harness Should Not Do

- silently fall back to live providers
- silently switch between fake and real sandbox modes
- hide ordering mismatches
- make transcript capture optional for deterministic tests

## Implementation Constraints

### Real DB, Fake Model, Real Sandbox

Default deterministic tests should prefer:

- real persistence
- fake model behavior
- real sandbox behavior where sandbox semantics are part of the thing being tested

That gives stronger confidence than a fake sandbox while still removing the biggest source of nondeterminism and cost: live model calls.

If a test does not meaningfully touch sandbox behavior, it does not need a sandbox at all.

If a test does touch sandbox behavior, the default should be to keep the sandbox real.

### Fake Sandbox Is Optional And Narrow

If a fake sandbox exists at all, it should be treated as a special-purpose tool, not the default harness.

Acceptable use cases:

- a tiny number of pure unit tests around helper logic that only depends on the sandbox interface
- impossible-to-trigger vendor failures that cannot be injected through a narrower fault layer
- extremely narrow local development scenarios where real sandbox startup would not add coverage

Even then, prefer a fault injector around the real sandbox path where possible.

### No Polling In The Default Harness

The harness should call services or runners directly wherever possible.

Polling-based behavior should be covered in:

- a small number of contract tests
- or explicit live/system tests

### Failure Injection Must Be Easy

An engineer should be able to cause:

- sandbox create failure
- sandbox teardown failure
- missing output file
- tool return error
- invalid event ordering

without building large custom fixtures each time.

For sandbox-specific failure cases, prefer:

- a real sandbox plus fault injection

over:

- replacing the sandbox entirely with a fake

## Acceptance Criteria

This slice is complete when:

- one backend state test can run with no live model and a real sandbox
- one transcript test can assert ordered tool calls
- one sandbox lifecycle test validates real filesystem and cleanup behavior
- one sandbox lifecycle test can inject teardown failure without replacing the real sandbox path
- shared DB assertions make tests short enough to stay readable
- distinct deterministic benchmark cases can run back-to-back in the same test session without leaking process-global runtime state
- the harness is designed so different deterministic benchmark cases can eventually run concurrently, and any remaining blockers to true concurrent execution are explicit infrastructure constraints rather than hidden global-state bugs
