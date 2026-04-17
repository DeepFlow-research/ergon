# ergon_builtins — agents & fixtures reference

Every worker / benchmark / evaluator / criterion registered in
`ergon_builtins/registry_core.py`, plus a cheat-sheet for picking the right
one when you're testing dashboard panels or RL plumbing.

**Source of truth**: `ergon_builtins/ergon_builtins/registry_core.py`. If you
add a new component, update the dicts there *and* this doc.

---

## Quick recipes — "I want to see X"

| Goal | Command |
|---|---|
| Populate **OUTPUTS** (RunResource rows, clickable file viewers) deterministically — no LLM, no cloud | `ergon benchmark run researchrubrics-smoke --worker researchrubrics-stub` (needs E2B sandbox) |
| Populate **SANDBOX** panel (stdin/stdout events) with no LLM | `ergon benchmark run smoke-test --worker smoke-test-worker` |
| Populate **GENERATIONS** without calling a model | `ergon benchmark run smoke-test --worker training-stub` |
| Populate **EVALUATION** with a passing gate, no LLM | any benchmark + `--evaluator stub-rubric` |
| Populate **EVALUATION** with varied scores (RL reward-shape test) | any benchmark + `--evaluator varied-stub-rubric` |
| Test a real ReAct agent end-to-end | `ergon benchmark run smoke-test --worker react-v1 --model openai:gpt-4o` |
| Test manager → researcher delegation with a real LLM | `ergon benchmark run delegation-smoke --worker manager-researcher --model openai:gpt-4o` |
| Test Lean 4 proof verification | `ergon benchmark run minif2f --worker minif2f-react --model openai:gpt-4o` (needs Lean sandbox) |

### ⚠️ Common footgun: `delegation-smoke --worker manager-researcher` with no files

The `delegation-smoke` benchmark spawns `researcher` sub-agents.  In the
current registry:

```python
"researcher": StubWorker,   # registry_core.py:49
```

…`researcher` is aliased to **`StubWorker`** — a no-op that produces one
plain-text `GenerationTurn` and nothing else.  No RunResource rows, no
sandbox events.  That's why the OUTPUTS panel stays empty.

If you want delegation **with** file-producing sub-agents, see the
`researcher-stub` worker on the `feature/run-visibility` branch (not yet
merged to main), or swap the benchmark composition manually.

---

## Dashboard panel population matrix

Which worker emits what.  `—` = not applicable, `✗` = nothing emitted.

| Worker | GENERATIONS | OUTPUTS | SANDBOX | COMMUNICATION |
|---|---|---|---|---|
| `stub-worker` | ✓ (1 turn, plain text) | ✗ | ✗ | ✗ |
| `training-stub` | ✓ (multi-turn synthetic w/ logprobs) | ✗ | ✗ | ✗ |
| `smoke-test-worker` | ✓ | ✗ | ✓ (writes `/outputs/ci_marker.txt`) | ✗ |
| `react-v1` | ✓ | ✗ | ✗ | ✓ (system/user/assistant/thinking/tool calls) |
| `minif2f-react` | ✓ | ✓ (proof artifact) | ✓ (Lean files) | ✓ |
| `manager-researcher` | ✓ | ✗ | ✓ (bash tool) | ✓ (delegation flow) |
| `researcher` *(alias → `stub-worker`)* | ✓ | ✗ | ✗ | ✗ |
| `researchrubrics-stub` | ✓ | ✓ (RunResource kind=REPORT) | ✓ (writes `final_output/report.md`) | ✗ |

EVALUATION is populated by whichever **evaluator** you pass with
`--evaluator`; see table below.

---

## Workers (`WORKERS` in registry_core.py)

| slug | class | requires | notes |
|---|---|---|---|
| `stub-worker` | `workers/baselines/stub_worker.py` | none | Minimal no-op; returns a fixed string. |
| `training-stub` | `workers/baselines/training_stub_worker.py` | none | Emits synthetic multi-turn data with fake logprobs/token_ids — exercises the RL extraction path without a real model. |
| `smoke-test-worker` | `workers/baselines/smoke_test_worker.py` | E2B sandbox | Writes a marker file to the sandbox for the CI round-trip test. |
| `react-v1` | `workers/baselines/react_worker.py` | LLM | Generic ReAct-style worker built on pydantic-ai.  Used by most real benchmarks. |
| `minif2f-react` | `workers/baselines/minif2f_react_worker.py` | LLM + Lean 4 sandbox | ReAct pre-wired with `write_lean_file`, `check_lean_file`, `verify_lean_proof`.  Produces a proof artifact in `WorkerOutput`. |
| `manager-researcher` | `workers/baselines/manager_researcher_worker.py` | LLM + E2B sandbox | Manager with `add_subtask`, `plan_subtasks`, `refine_task`, `cancel_task`, `bash` tools — drives dynamic delegation. |
| `researcher` | alias → `StubWorker` | none | Bound as the sub-agent in delegation compositions.  Currently a stub; producing no files / sandbox events. |
| `researchrubrics-stub` | `workers/research_rubrics/stub_worker.py` | E2B sandbox (`ResearchRubricsSandboxManager`) | Writes a canned research report to `/workspace/final_output/report.md`, then calls `SandboxResourcePublisher.sync()` so it shows up as a RunResource. **The deterministic "populates OUTPUTS" worker.** |

---

## Benchmarks (`BENCHMARKS` in registry_core.py)

| slug | class | task count | requires |
|---|---|---|---|
| `smoke-test` | `benchmarks/smoke_test/benchmark.py` | configurable DAG (single / linear / parallel / diamond) | none |
| `delegation-smoke` | `benchmarks/delegation_smoke/benchmark.py` | 1 (manager with instruction to spawn exactly 2 sub-tasks) | LLM (manager) |
| `minif2f` | `benchmarks/minif2f/benchmark.py` | ~14k Lean 4 theorems from HuggingFace `minif2f-v2c` | Lean 4 sandbox |
| `researchrubrics-smoke` | `benchmarks/researchrubrics/smoke.py` | 1 (instruction: "write a research report") | E2B sandbox |

---

## Evaluators / rubrics (`EVALUATORS` in registry_core.py)

| slug | class | requires | what it checks |
|---|---|---|---|
| `stub-rubric` | `evaluators/rubrics/stub_rubric.py` | none | Passes iff `worker.success == True`. |
| `varied-stub-rubric` | `evaluators/rubrics/varied_stub_rubric.py` | none | Returns a random score in `[0.1, 1.0)`; useful for GRPO reward-shape tests. |
| `smoke-test-rubric` | `benchmarks/smoke_test/rubric.py` | E2B sandbox | Verifies the marker file exists after `smoke-test-worker` ran. |
| `minif2f-rubric` | `benchmarks/minif2f/rubric.py` | Lean 4 sandbox | Compiles the final `.lean` in the sandbox; awards partial credit for syntactically-valid-but-unproved proofs. |
| `staged-rubric` | `benchmarks/gdpeval/rubric.py` | LLM (embedded `llm-judge` criteria) | Sequential-gate multi-stage evaluator used by GDPEval. |
| `researchrubrics-smoke-rubric` | `benchmarks/researchrubrics/smoke_rubric.py` | none (reads local RunResource) | Asserts a `REPORT` RunResource exists with required headers (`# Findings`, `## Sources`). |

---

## Criteria (atomic, composed by rubrics)

| slug | file | requires |
|---|---|---|
| `stub-criterion` | `evaluators/criteria/stub_criterion.py` | none |
| `varied-stub-criterion` | `evaluators/criteria/varied_stub_criterion.py` | none |
| `sandbox-file-check` | `evaluators/criteria/sandbox_file_check.py` | E2B sandbox |
| `stub-report-exists` | `evaluators/criteria/stub_report_exists.py` | reads RunResource blobs on disk |
| `llm-judge` | `evaluators/criteria/llm_judge.py` | LLM |
| `file-check` | `evaluators/criteria/file_check.py` | none |
| `code-check` | `evaluators/criteria/code_check.py` | none (lightweight path) |
| `trace-check` | `evaluators/criteria/trace_check.py` | none |
| `proof-verification` | `benchmarks/minif2f/rules/proof_verification.py` | Lean 4 sandbox |

---

## Sandbox managers (`SANDBOX_MANAGERS` in registry_core.py)

| slug | class | purpose |
|---|---|---|
| `gdpeval` | `benchmarks/gdpeval/sandbox.py` | GDPEval harness sandbox. |
| `minif2f` | `benchmarks/minif2f/sandbox_manager.py` | Lean 4 sandbox with the compiler pre-installed. |

(`ResearchRubricsSandboxManager` lives in `ergon_core/core/providers/sandbox/`
and is instantiated directly by `researchrubrics-stub`; it is not in
`SANDBOX_MANAGERS` because nothing else uses it.)

---

## Model backends (`MODEL_BACKENDS` in registry_core.py)

| prefix | file | notes |
|---|---|---|
| `vllm:` | `models/vllm_backend.py` | Points at a running vLLM server; supports logprobs. |
| `openai:`, `anthropic:`, `google:` | `models/cloud_passthrough.py` | Passes through to pydantic-ai's provider.  No logprobs. |
| *(no prefix)* | fallthrough | Handed to pydantic-ai's `infer_model` — may pick a default or fail. |

Default when `--model` is omitted: `openai:gpt-4o`
(`ergon_core/core/providers/generation/model_resolution.py:57`).

---

## CLI compositions (`ergon_cli/composition/__init__.py`)

The CLI rewrites some `--worker` / `--benchmark` combinations into
multi-worker experiments:

| trigger | what it wires |
|---|---|
| `--worker manager-researcher` (any benchmark) | `manager-researcher` on all static tasks + `researcher` bound as the sub-worker for dynamically-spawned subtasks |
| `--benchmark delegation-smoke` (any worker) | same as above — `delegation-smoke` is designed around this composition |

Everything else runs the single worker you pass, against every task.
