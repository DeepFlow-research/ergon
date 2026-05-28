# ergon_builtins — agents & fixtures reference

This document is a cheat-sheet for built-in object-bound workers, benchmarks,
evaluators, criteria, and sandbox classes when testing dashboard panels or RL
plumbing.

**Source of truth**: the benchmark packages themselves. If you add a new
component, expose it through explicit package imports or CLI discovery and
update this doc in the same PR.

---

## Quick recipes — "I want to see X"

| Goal | Command |
|---|---|
| Populate **SANDBOX** panel (stdin/stdout events) with no LLM | Use a Python submit script that builds a `ResearchRubricsEnvironment` with the canonical smoke worker and calls `Experiment.submit(...)`. |
| Populate **GENERATIONS** without calling a model | Use a Python submit script with an environment bound to `TrainingStubWorker`; inspect with `ergon sample show <sample-id>`. |
| Populate **EVALUATION** with a passing gate, no LLM | Bind `stub-rubric` in the environment's evaluator list. |
| Populate **EVALUATION** with varied scores (RL reward-shape test) | Bind `varied-stub-rubric` in the environment's evaluator list. |
| Test a real ReAct agent end-to-end | Build the relevant builtin environment in Python with the ReAct worker and submit it through `Experiment.submit(...)`. |
| Test manager -> researcher delegation with a real LLM | Build `ResearchRubricsEnvironment` in Python with `researchrubrics-researcher` and submit it through `Experiment.submit(...)`. |
| Test Lean 4 proof verification | Build `MiniF2FEnvironment` in Python with the MiniF2F worker/rubric and submit it through `Experiment.submit(...)` (needs Lean sandbox). |

---

## Dashboard panel population matrix

Which worker emits what.  `—` = not applicable, `✗` = nothing emitted.

| Worker | GENERATIONS | OUTPUTS | SANDBOX | COMMUNICATION |
|---|---|---|---|---|
| `training-stub` | ✓ (multi-turn synthetic w/ logprobs) | ✗ | ✗ | ✗ |
| `canonical-smoke` | ✓ | ✓ (per-env leaf SampleResource) | ✓ (via per-env leaf) | ✗ |
| `react-v1` | ✓ | ✗ | ✗ | ✓ (system/user/assistant/thinking/tool calls) |
| `minif2f-react` | ✓ | ✓ (proof artifact) | ✓ (Lean files) | ✓ |
| `researchrubrics-researcher` | ✓ | ✓ (SampleResource kind=REPORT) | ✓ (writes `final_output/report.md`) | ✗ |

EVALUATION is populated by the **evaluators** bound to the submitted
environment; see table below.

---

## Workers

| slug | class | requires | notes |
|---|---|---|---|
| `training-stub` | `workers/baselines/training_stub_worker.py` | none | Emits synthetic multi-turn data with fake logprobs/token_ids — exercises the RL extraction path without a real model. |
| `canonical-smoke` | `workers/stubs/canonical_smoke_worker.py` | per-env leaf + its sandbox | Dispatches to a per-environment smoke leaf (`SweBenchSmokeRubric`, `ResearchRubricsSmokeRubric`, `MiniF2FSmokeRubric`) — the RFC 2026-04-21 canonical smoke path. |
| `react-v1` | `workers/baselines/react_worker.py` | LLM | Generic ReAct-style worker built on pydantic-ai.  Used by most real benchmarks. |
| `minif2f-react` | `workers/baselines/minif2f_react_worker.py` | LLM + Lean 4 sandbox | ReAct pre-wired with `write_lean_file`, `check_lean_file`, `verify_lean_proof`.  Produces a proof artifact in `WorkerOutput`. |
| `researchrubrics-researcher` | `workers/research_rubrics/researcher_worker.py` | LLM + E2B sandbox (`ResearchRubricsSandboxManager`) | Writes a research report to `/workspace/final_output/report.md` and publishes it as a SampleResource. |

---

## Environments

| slug | class | task count | requires |
|---|---|---|---|
| `minif2f` | `environments/minif2f.py` | ~14k Lean 4 theorems from HuggingFace `minif2f-v2c` | Lean 4 sandbox |
| `researchrubrics` | `environments/researchrubrics.py` | ResearchRubrics dataset rows | E2B sandbox |
| `swebench-verified` | `environments/swebench_verified.py` | curated SWE-Bench instances | Docker sandbox (ships with repo snapshots) |
| `gdpeval` | `environments/gdpeval.py` | GDP document-processing tasks | E2B sandbox |

---

## Evaluators / rubrics

| slug | class | requires | what it checks |
|---|---|---|---|
| `stub-rubric` | `evaluators/rubrics/stub_rubric.py` | none | Passes iff `worker.success == True`. |
| `varied-stub-rubric` | `evaluators/rubrics/varied_stub_rubric.py` | none | Returns a random score in `[0.1, 1.0)`; useful for GRPO reward-shape tests. |
| `minif2f-rubric` | `benchmarks/minif2f/rubric.py` | Lean 4 sandbox | Compiles the final `.lean` in the sandbox; awards partial credit for syntactically-valid-but-unproved proofs. |
| `minif2f-smoke-rubric` | `benchmarks/minif2f/smoke_rubric.py` | Lean sandbox | Canonical-smoke leaf for the MiniF2F env. |
| `staged-rubric` | `benchmarks/gdpeval/rubric.py` | LLM (embedded `llm-judge` criteria) | Sequential-gate multi-stage evaluator used by GDPEval. |
| `researchrubrics-smoke-rubric` | `benchmarks/researchrubrics/smoke_rubric.py` | none (reads local SampleResource) | Asserts a `REPORT` SampleResource exists with required headers (`# Findings`, `## Sources`). |
| `swebench-smoke-rubric` | `benchmarks/swebench_verified/smoke_rubric.py` | SWE-Bench sandbox | Canonical-smoke leaf for the SWE-Bench env. |
| `swebench-rubric` | `evaluators/rubrics/swebench_rubric.py` | SWE-Bench sandbox | Real SWE-Bench patch evaluation. |

---

## Criteria (atomic, composed by rubrics)

| slug | file | requires |
|---|---|---|
| `stub-criterion` | `evaluators/criteria/stub_criterion.py` | none |
| `varied-stub-criterion` | `evaluators/criteria/varied_stub_criterion.py` | none |
| `sandbox-file-check` | `evaluators/criteria/sandbox_file_check.py` | E2B sandbox |
| `stub-report-exists` | `evaluators/criteria/stub_report_exists.py` | reads SampleResource blobs on disk |
| `llm-judge` | `evaluators/criteria/llm_judge.py` | LLM |
| `file-check` | `evaluators/criteria/file_check.py` | none |
| `code-check` | `evaluators/criteria/code_check.py` | none (lightweight path) |
| `trace-check` | `evaluators/criteria/trace_check.py` | none |
| `proof-verification` | `benchmarks/minif2f/rules/proof_verification.py` | Lean 4 sandbox |

---

## Sandbox classes

| slug | class | purpose |
|---|---|---|
| `gdpeval` | `benchmarks/gdpeval/sandbox.py` | GDPEval harness sandbox. |
| `minif2f` | `benchmarks/minif2f/sandbox.py` | Lean 4 sandbox with the compiler pre-installed. |
| `researchrubrics` | `benchmarks/researchrubrics/sandbox.py` | ResearchRubrics E2B sandbox with Exa tooling. |
| `researchrubrics-vanilla` | `benchmarks/researchrubrics/sandbox.py` | Same sandbox setup for the vanilla benchmark variant. |
| `swebench-verified` | `benchmarks/swebench_verified/sandbox.py` | SWE-Bench instance sandbox; installs repo+deps in `_install_dependencies`. |

---

## Model targets (`resolve_model_target`)

| prefix | file | notes |
|---|---|---|
| `vllm:<base-url>[#<model>]` | `ergon_core/core/providers/generation/openai_compatible.py` | Points at a running vLLM server; supports logprobs. |
| `openai-compatible:<base-url>#<model>` | `ergon_core/core/providers/generation/openai_compatible.py` | Generic OpenAI-compatible endpoints such as Ollama. |
| `openai:`, `anthropic:`, `google:` | `ergon_core/core/providers/generation/openrouter.py` | Always routed through OpenRouter, not direct cloud APIs. |

Default when `--model` is omitted: `openai:gpt-4o`
(`ergon_core/core/providers/generation/model_resolution.py`).

---

## CLI compositions (`ergon_cli/composition/__init__.py`)

All worker slugs run the single worker you pass, against every task. Multi-worker compositions are wired at call sites by constructing an `Experiment` directly with explicit `workers` and `assignments` dicts.
