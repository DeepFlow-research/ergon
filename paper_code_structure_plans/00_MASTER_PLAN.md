# H-ARCANE Experiment Implementation Plan

## Vision

Build a focused experimental framework to study **decision-making under uncertainty** in agent-stakeholder interactions. A single worker agent must decide when to ask clarifying questions vs. execute a task, given uncertainty about stakeholder preferences (expressed as nested rubrics).

## Research Setting

**Current Focus: ReAct Baseline**

Measure natural LLM clarification behavior:
- When does an LLM-based worker spontaneously ask questions?
- Does asking improve task performance?
- What's the relationship between questions and score?

**Ground Truth**: Stakeholder holds the true nested rubric (from GDPEval)

## Simplified Architecture (vs. Full MA-Gym Rebuild)

| Full MA-Gym | H-ARCANE Paper |
|-------------|----------------|
| Manager + Workers | Single Worker (is the decision-maker) |
| Pre-execution + Execution phases | Single phase: clarify-or-execute loop |
| Complex task DAG | Single task per experiment |
| Many event types | Focused event set |

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Orchestration | Inngest | Event-driven workflow, async execution |
| Database | PostgreSQL + SQLModel | State persistence, experiment logs |
| LLM | OpenAI Agents SDK | Worker reasoning, stakeholder simulation |
| Rubrics | GDPEval StagedRubric | Ground truth preferences |

## Core Loop: ReAct with Clarification Tool

Simple execution flow:

```
1. Load experiment (task + StagedRubric)
2. Create stakeholder (holds ground truth, answers questions)
3. Execute task with ReAct worker:
   - Worker has access to ask_stakeholder + GDPEval tools
   - Worker decides organically when to ask
   - Q&A logged as Messages; tool calls logged as Actions
4. Evaluate: Score output against ground truth rubric
5. Record: questions asked, final score, cost
```

No hypothesis tracking or VoI calculations — just measure natural behavior.

## Key Entities

| Entity | Table | Purpose |
|--------|-------|---------|
| `Experiment` | `experiments` | GDPEval task + `StagedRubric` + input_files |
| `Run` | `runs` | Execution attempt + output text + output resource IDs |
| `Message` | `messages` | Worker↔Stakeholder Q&A |
| `Action` | `actions` | Flattened tool call trace |
| `Resource` | `resources` | Output files (worker-generated) |
| `EvaluationResult` | `evaluations` | Aggregate scores |
| `CriterionResult` | `criterion_results` | Per-criterion score + feedback + evaluated refs |

**7 tables** — flat, queryable, debuggable.

### Current Scope: ReAct Baseline Only

For now, we implement only the **ReAct baseline** — a worker that can ask questions organically during execution. No VoI calculations, no hypothesis tracking.

This lets us:
1. Build the infrastructure (experiments, runs, stakeholder, evaluation)
2. Measure natural LLM clarification behavior
3. Establish a baseline before adding VoI complexity

## Implementation Status

| Benchmark | Status | Description |
|-----------|--------|-------------|
| **GDPEval** | ✅ Complete | Document/spreadsheet/code tasks with staged rubric evaluation |
| **MiniF2F** | ✅ Complete | Formal mathematics (Lean proofs) with binary verification |
| **ResearchRubrics** | ❌ Pending | Deep research tasks with weighted criteria - see [12_RESEARCHRUBRICS_IMPLEMENTATION.md](./12_RESEARCHRUBRICS_IMPLEMENTATION.md) |

### Common Infrastructure (Complete)
- Generic Inngest orchestration via registry pattern
- `BaseStakeholder`, `BaseToolkit`, `BaseRubric` protocols
- Benchmark-specific factories and evaluators
- Discriminated unions for type-safe Pydantic serialization

## Plan Documents

| Document | Description |
|----------|-------------|
| [01_CORE_ENTITIES.md](./01_CORE_ENTITIES.md) | Domain models and database schema (7 tables: experiments, runs, messages, actions, etc.) |
| [03_EVENT_ARCHITECTURE.md](./03_EVENT_ARCHITECTURE.md) | Inngest events and execution flow |
| [04_EXPERIMENT_LAYOUT.md](./04_EXPERIMENT_LAYOUT.md) | GDPEval data loading, experiment batching, analysis |
| [05_EVALUATION_ARCHITECTURE.md](./05_EVALUATION_ARCHITECTURE.md) | Evaluation system: functional approach with criterion-level evaluation |
| [SANDBOX_ARCHITECTURE.md](./SANDBOX_ARCHITECTURE.md) | E2B sandbox integration: agent outside, tools inside sandbox |
| [06_CODE_RULE_CONVERSION.md](./06_CODE_RULE_CONVERSION.md) | One-off script to convert GDPEval code rules from (workflow, context) → (task_input, agent_reasoning, output_files) |
| [07_MULTI_BASELINE_ARCHITECTURE.md](./07_MULTI_BASELINE_ARCHITECTURE.md) | Multi-benchmark architecture: GDPEval, MiniF2F, ResearchRubrics |
| [10_BENCHMARK_FIRST_ARCHITECTURE.md](./10_BENCHMARK_FIRST_ARCHITECTURE.md) | Benchmark-first refactoring: decoupling core from benchmark-specific code |
| [11_GENERIC_ORCHESTRATION.md](./11_GENERIC_ORCHESTRATION.md) | Generic Inngest handlers via registry pattern |
| [12_RESEARCHRUBRICS_IMPLEMENTATION.md](./12_RESEARCHRUBRICS_IMPLEMENTATION.md) | **ResearchRubrics implementation plan** (deep research baseline) |
| [20_BENCHMARK_SETUP_CLI.md](./20_BENCHMARK_SETUP_CLI.md) | First-class onboarding and benchmark preparation CLI (`magym`) for compose, readiness checks, benchmark prep, and seeding |
| [PRE_BUILD_CHECKLIST.md](./PRE_BUILD_CHECKLIST.md) | What's left before building - decisions, prerequisites, build order |

## Current Scope: ReAct Baseline

Single worker implementation for now:

| Worker | Description |
|--------|-------------|
| `ReActWorker` | Asks organically during execution — natural LLM behavior |

### What We Measure

- How many questions does the worker ask?
- What kinds of questions?
- Does asking improve final score?
- Cost (tokens) vs. score trade-off

### Future: VoI Extension

Once baseline is working, we can add VoI-informed workers that use hypothesis tracking and explicit value-of-information calculations to decide when to ask.

## Metrics

| Metric | Description |
|--------|-------------|
| `normalized_score` | Output score against ground truth rubric (0-1) |
| `questions_asked` | Number of clarification questions |
| `total_tokens` | Total LLM tokens used |
| `total_cost_usd` | Estimated API cost |

## Setup: Making Plans Self-Contained

Before implementation, copy GDPEval data and schemas into the plan folder:

```bash
# Copy GDPEval data directory
cp -r manager_agent_gym/curation/gdpeval/data paper_code_structure_plans/

# Copy staged rubric schema
mkdir -p paper_code_structure_plans/schemas
cp manager_agent_gym/curation/gdpeval/src/staged_rubric_schema.py paper_code_structure_plans/schemas/
```

This makes the plan folder self-contained with all necessary data and schemas.

## Build Phases

### Phase 1: Foundation
- [ ] `pyproject.toml` with dependencies (inngest, sqlmodel, openai-agents-sdk)
- [ ] Docker Compose (Postgres + Inngest Dev Server)
- [ ] SQLModel table definitions
- [ ] GDPEval loader (uses local `paper_code_structure_plans/data/`)
- [ ] **Code rule converter script**: One-off script to convert GDPEval code rules (see [06_CODE_RULE_CONVERSION.md](./06_CODE_RULE_CONVERSION.md))
- [ ] **Input files as DB records**: Store GDPEval input files as Resource records (not JSON) - create during experiment loading

### Phase 2: Agents
- [ ] RubricStakeholder with rubric-based response generation
- [ ] ReActWorker with `ask_stakeholder` + GDPEval tools
- [ ] WorkerToolkit for message/action logging
- [ ] SandboxManager for E2B sandbox lifecycle (see [SANDBOX_ARCHITECTURE.md](./SANDBOX_ARCHITECTURE.md))
- [ ] Tool modules in `h_arcane/tools/` (uploaded to sandbox)
- [ ] `execute_in_sandbox()` function for sandbox tool execution

### Phase 3: Inngest Orchestration
- [ ] `run/start` event handler
- [ ] `worker_execute` function (with sandbox creation/termination)
- [ ] `run_evaluate` function (orchestrates evaluation)
- [ ] `evaluate_task_run` function (flattens rubric, evaluates criteria)
- [ ] `evaluate_criterion` function (single criterion evaluator)

### Phase 4: Experiment Runner
- [ ] Simple CLI: `python scripts/run_experiments.py --num-examples 10 --baseline react`
- [ ] Batch experiment launcher with configurable baselines
- [ ] Results aggregation and export

## Directory Structure

```
arcane_extension/
├── paper_code_structure_plans/     # This folder (self-contained)
│   ├── data/                       # GDPEval data (copied from manager_agent_gym)
│   │   ├── raw/
│   │   │   ├── gdpeval.parquet
│   │   │   ├── metadata.json
│   │   │   └── reference_files/    # 262 input files
│   │   └── generated/
│   │       └── staged_v2/
│   │           ├── staged_rubrics.jsonl
│   │           ├── train_rubrics.jsonl
│   │           └── eval_rubrics.jsonl
│   └── schemas/                    # Local schema copies
│       └── staged_rubric_schema.py # Copied from manager_agent_gym
├── h_arcane/                       # Implementation
│   ├── __init__.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py               # SQLModel tables (runs, messages, actions, etc.)
│   │   ├── connection.py
│   │   └── queries.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── worker.py               # ReActWorker
│   │   ├── stakeholder.py          # RubricStakeholder
│   │   ├── toolkit.py              # WorkerToolkit (ask_stakeholder + gdpeval tools)
│   │   ├── sandbox_executor.py     # execute_in_sandbox() function
│   │   └── tools.py                # @function_tool wrappers (call execute_in_sandbox)
│   ├── tools/                      # Tool modules (uploaded to sandbox)
│   │   ├── __init__.py
│   │   ├── read_pdf.py
│   │   ├── create_docx.py
│   │   └── ...                     # Other tool modules
│   ├── inngest/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── functions.py
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── criteria_evaluator.py   # evaluate_criteria function
│   │   └── rubric_flattener.py     # flatten_rubric function
│   └── experiments/
│       ├── __init__.py
│       ├── loader.py               # GDPEval data loading (uses local data/)
│       ├── runner.py               # Batch experiment runner
│       └── analysis.py             # Results analysis
├── scripts/
│   ├── run_experiments.py
│   └── analyze_results.py
└── theory.tex

# GDPEval tools reused from:
manager_agent_gym/core/agents/workflow_agents/tools/
├── documents.py        # create_documents_tools()
├── spreadsheets.py     # create_spreadsheets_tools()
├── rag.py              # create_rag_tools()
├── ocr.py              # create_ocr_tools()
└── code.py             # create_code_tools()
```

## Key Design Decisions

1. **Single Worker**: No manager agent; worker executes with clarification tool
2. **Continuous Execution**: Worker can ask at any point during task
3. **Messages table**: Unified Q&A logging (sender, content, sequence)
4. **Actions table**: Flattened trace (action_type, input, output) — queryable
5. **Sandbox execution**: All GDPEval tools execute inside E2B sandbox (see [SANDBOX_ARCHITECTURE.md](./SANDBOX_ARCHITECTURE.md)) - agent outside, tools inside for isolation and scalability
6. **Reuse GDPEval tool logic**: Extract tool functions from `manager_agent_gym` into `h_arcane/tools/` modules
7. **Strongly typed rubrics**: `StagedRubric` not `dict` in application code
8. **Event-Driven Orchestration**: Inngest handles async run management
9. **State in Postgres**: All messages, actions, and results persisted
10. **ReAct Only (for now)**: No VoI calculations; measure natural behavior first

## Open Questions

- [ ] How to handle very long GDPEval tasks that exceed context?
- [ ] Should stakeholder reveal partial rubric info or just answer questions?
- [ ] How to measure "question quality" for analysis?
- [ ] What prompt engineering gets best clarification behavior from ReAct?

