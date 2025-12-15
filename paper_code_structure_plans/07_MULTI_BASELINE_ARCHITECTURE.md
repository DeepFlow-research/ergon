# Multi-Baseline Architecture Plan

## Overview

This document outlines the plan to abstract the H-ARCANE codebase to support three different baselines:
1. **GDPEval** (existing) - Document/spreadsheet/code tasks with rubric-based evaluation
2. **MiniF2F** - Formal mathematics problems requiring proof verification (244 problems in Lean)
3. **ResearchRubrics** - Deep research tasks with ablated prompts to study adaptive stakeholder querying (101 tasks with weighted rubrics)

## Quick Summary

### Key Decisions Made ✅
- **MiniF2F**: Start with Lean only (244 problems, 100% coverage)
- **ResearchRubrics**: Use ScaleAI ResearchRubrics dataset with weighted criteria by axis type
- **Database**: Polymorphic approach with `benchmark_type` enum + JSON fields
- **Worker**: Unified `BaseWorker` with benchmark-specific configs
- **Evaluation**: End-of-generation for all benchmarks (async via Inngest)
- **Sandbox**: Single sandbox type with Lean installation
- **Exa API**: Three tools (search, QA, get_content) using `exa_py` library

### Data Splits
- **GDPEval**: Variable (loads from `staged_rubrics.jsonl`)
- **MiniF2F**: 244 problems total (valid + test splits, all in Lean)
- **ResearchRubrics**: 101 tasks with ~25 weighted criteria each (ablated prompts created separately)

## Key Design Decisions (RESOLVED)

### 1. MiniF2F Formal System Support ✅
**Decision**: Start with **Lean only**
- **Rationale**: MiniF2F has 244 problems in Lean (both test and valid splits), covering the entire dataset
- **Coverage**: 100% of MiniF2F problems available in Lean
- **Future**: Design interface to be extensible for Metamath/Isabelle/HOL Light later

### 2. ResearchRubrics Evaluation & Research Design ✅
**Decision**: Use **ScaleAI ResearchRubrics** dataset with ablated prompts to study adaptive querying

**Dataset**: `ScaleAI/researchrubrics` from HuggingFace
- 101 tasks across 10 domains (AI & ML, Business Planning, Historical Analysis, etc.)
- ~25 weighted criteria per task (total 2,593 criteria)
- Criteria organized by axis type:
  - **Implicit Criteria** (39.4%) - Not explicitly in prompt, agent must infer/ask
  - **Explicit Criteria** (27.7%) - Directly requested in prompt
  - **Synthesis of Information** (15.8%) - Quality of analysis
  - **Communication Quality** (7.8%) - Writing style/structure
  - **Instruction Following** (5.8%) - Format constraints
  - **References & Citation Quality** (3.5%) - Source quality

**Research Focus**: When should agents ask stakeholder questions?
- Primary: Do agents know WHEN to ask?
- Secondary: Does asking improve outcomes?
- Tertiary: Do agents ask the RIGHT questions?

**Ablation Strategy** (done separately, manual with QA):
- Remove context from prompts that specifies preferences
- Create uncertainty that requires stakeholder querying
- Preserve enough structure for rubric evaluation

**Stakeholder Design**:
- Stakeholder knows: rubric criteria + original (unablated) question
- Answers based on rubric criteria when relevant
- Responds "I don't have a preference on that" for out-of-scope questions

### 3. Database Schema Extension ✅
**Decision**: **Polymorphic approach** with `benchmark_type` enum
- Add `benchmark_type: BenchmarkType` field to Experiment/Run
- Use `benchmark_specific_data` JSON field for flexible storage
- Single unified schema for all benchmarks

### 4. Worker Abstraction ✅
**Decision**: **Unified BaseWorker** with benchmark-specific configurations
- Single `BaseWorker` class that accepts `BenchmarkConfig`
- Benchmark-specific toolkits and system prompts
- Cleaner architecture, easier to maintain

### 5. Stakeholder Abstraction ✅
**Decision**: Abstract to **BaseStakeholder** with benchmark-specific implementations
- **GDPEval**: RubricStakeholder (answers questions based on rubric)
- **MiniF2F**: ProofVerifier (verifies proofs, provides feedback)
- **ResearchRubrics**: RubricAwareStakeholder (answers based on rubric criteria + original question)

### 6. Sandbox Requirements ✅
**Decision**: **Single sandbox type** with Lean installation
- Since we're starting with Lean only, single sandbox setup is sufficient
- Install Lean in E2B sandbox
- Future: Can extend to support multiple sandbox types if needed

### 7. Evaluation Timing ✅
**Decision**: **End-of-generation evaluation** for all benchmarks
- GDPEval: After execution completes
- MiniF2F: After proof generation completes
- ResearchRubrics: After report generation completes
- All evaluations happen asynchronously via Inngest

## Architecture Design

### Directory Structure

```
arcane_extension/
├── h_arcane/
│   ├── schemas/                       # Shared types only
│   │   ├── __init__.py
│   │   ├── staged_rubric_schema.py    # Existing: StagedRubric, CodeRule, LLMJudgeRule, etc.
│   │   └── base.py                    # NEW: BenchmarkType enum, BenchmarkConfig
│   ├── benchmarks/                    # Benchmark-specific modules (schemas live here)
│   │   ├── __init__.py
│   │   ├── base.py                    # Base classes/interfaces (BenchmarkLoader, etc.)
│   │   ├── gdpeval/
│   │   │   ├── __init__.py
│   │   │   ├── schemas.py             # GDPEvalTask, GDPEvalBenchmarkData
│   │   │   ├── loader.py              # Data loading (moved from experiments/loader.py)
│   │   │   ├── criteria.py            # Convert StagedRubric to criteria list
│   │   │   ├── stakeholder.py         # GDPEval stakeholder (moved from agents/)
│   │   │   └── tools.py               # GDPEval tool definitions
│   │   ├── minif2f/
│   │   │   ├── __init__.py
│   │   │   ├── schemas.py             # MiniF2FProblem, MiniF2FBenchmarkData
│   │   │   ├── loader.py              # Load MiniF2F problems
│   │   │   ├── criteria.py            # Convert problem to criteria list (proof_correctness)
│   │   │   ├── stakeholder.py         # Proof verifier stakeholder
│   │   │   └── tools.py               # Lean proof verification tools
│   │   └── researchrubrics/
│   │       ├── __init__.py
│   │       ├── schemas.py             # ResearchRubricsTask, AblatedPromptsFile, etc.
│   │       ├── loader.py              # Load from ScaleAI/researchrubrics + ablated prompts
│   │       ├── criteria.py            # Convert rubrics to criteria list (weighted by axis)
│   │       ├── stakeholder.py         # RubricAwareStakeholder (knows criteria + original question)
│   │       ├── metrics.py             # Question analysis metrics
│   │       └── tools.py               # Web search/QA tools (Exa)
│   ├── agents/
│   │   ├── worker.py                  # REFACTORED: Unified BaseWorker
│   │   ├── toolkit.py                 # REFACTORED: BaseToolkit interface
│   │   └── ...                        # Other agent files
│   ├── tools/                         # REFACTORED: Organized by category
│   │   ├── __init__.py
│   │   ├── responses.py               # Base ToolResponse + GDPEval responses (existing)
│   │   ├── gdpeval/                   # GDPEval tools (existing)
│   │   │   ├── documents.py
│   │   │   ├── spreadsheets.py
│   │   │   ├── code.py
│   │   │   └── ocr.py
│   │   ├── formal_math/               # NEW: Formal math tools
│   │   │   ├── __init__.py
│   │   │   ├── responses.py           # Strongly typed responses for Lean tools
│   │   │   ├── lean_write.py          # Write/update Lean proof files
│   │   │   ├── lean_check.py          # Check file for errors and remaining goals
│   │   │   └── lean_verify.py         # Quick final verification
│   │   └── web_research/              # NEW: Web research tools
│   │       ├── __init__.py
│   │       ├── responses.py           # Strongly typed responses for Exa tools
│   │       ├── exa_search.py         # Exa web search
│   │       ├── exa_qa.py             # Exa question answering
│   │       └── exa_get_content.py    # Exa link content extraction
│   ├── db/
│   │   ├── models.py                  # EXTENDED: Add benchmark_type enum
│   │   └── ...
│   └── evaluation/
│       ├── task_evaluator.py        # UNIFIED: Orchestrates all evaluations
│       ├── criteria_evaluator.py     # SIMPLIFIED: Uses polymorphic rule.evaluate(context)
│       ├── context.py                # NEW: EvaluationContext Pydantic model
│       ├── rubric_flattener.py       # EXTENDED: Support non-StagedRubric formats
│       └── models.py                 # EXTENDED: Type aliases for benchmark-specific rules
```

### Benchmark Schemas (Strongly Typed)

**Organization principle**: Shared types live in `h_arcane/schemas/`, benchmark-specific types live in `h_arcane/benchmarks/{name}/schemas.py`.

**Shared Types (`schemas/base.py`):**
```python
# h_arcane/schemas/base.py

from enum import Enum
from pydantic import BaseModel, Field


class BenchmarkType(str, Enum):
    """Supported benchmark types."""
    GDPEVAL = "gdpeval"
    MINIF2F = "minif2f"
    RESEARCHRUBRICS = "researchrubrics"


class BenchmarkConfig(BaseModel):
    """Configuration for running a benchmark."""
    benchmark_type: BenchmarkType
    system_prompt: str
    tools: list[str]
    max_questions: int = 10
```

**GDPEval Types (`benchmarks/gdpeval/schemas.py`):**
```python
# h_arcane/benchmarks/gdpeval/schemas.py

from pathlib import Path
from pydantic import BaseModel, Field
from h_arcane.schemas.staged_rubric_schema import StagedRubric


class GDPEvalTask(BaseModel):
    """A GDPEval task with its rubric."""
    task_id: str
    task_description: str
    reference_files: list[Path]
    rubric: StagedRubric
    category: str


class GDPEvalBenchmarkData(BaseModel):
    """Stored in Experiment.benchmark_specific_data for GDPEval."""
    # GDPEval doesn't need extra data beyond ground_truth_rubric
    pass
```

**MiniF2F Types (`benchmarks/minif2f/schemas.py`):**
```python
# h_arcane/benchmarks/minif2f/schemas.py

from typing import Literal
from pydantic import BaseModel, Field


class MiniF2FProblem(BaseModel):
    """Parsed MiniF2F problem from Lean file."""
    theorem_name: str = Field(description="Name of the theorem (e.g., 'aime_1983_p1')")
    full_statement: str = Field(description="Complete Lean theorem with 'sorry' placeholder")
    split: Literal["valid", "test"] = Field(description="Dataset split")
    source_file: str = Field(description="Source Lean file name")


class MiniF2FProblemMetadata(BaseModel):
    """Extracted metadata from theorem name."""
    competition: str | None = Field(default=None, description="Competition name (aime, imo, etc.)")
    year: int | None = Field(default=None, description="Competition year")
    problem_number: int | None = Field(default=None, description="Problem number")


class MiniF2FBenchmarkData(BaseModel):
    """Stored in Experiment.benchmark_specific_data for MiniF2F."""
    formal_system: Literal["lean"] = "lean"
    split: Literal["valid", "test"]
    source_file: str
    theorem_name: str
    full_statement: str
    competition: str | None = None
    year: int | None = None
    problem_number: int | None = None
```

**ResearchRubrics Types (`benchmarks/researchrubrics/schemas.py`):**
```python
# h_arcane/benchmarks/researchrubrics/schemas.py

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class RubricAxisType(str, Enum):
    """Axis types from ResearchRubrics dataset."""
    IMPLICIT_CRITERIA = "Implicit Criteria"
    EXPLICIT_CRITERIA = "Explicit Criteria"
    SYNTHESIS = "Synthesis of Information"
    COMMUNICATION = "Communication Quality"
    INSTRUCTION_FOLLOWING = "Instruction Following"
    REFERENCES = "References & Citation Quality"


class RubricCriterion(BaseModel):
    """A single criterion from ResearchRubrics."""
    criterion: str = Field(description="The criterion text")
    axis: str = Field(description="Axis type (Implicit/Explicit/etc.)")
    weight: float = Field(description="Criterion weight (can be negative for penalties)")


class ResearchRubricsTask(BaseModel):
    """Parsed ResearchRubrics task from HuggingFace."""
    sample_id: str = Field(description="Unique task identifier")
    domain: str = Field(description="Task domain (AI & ML, Business Planning, etc.)")
    original_prompt: str = Field(description="Original unablated prompt")
    rubrics: list[RubricCriterion] = Field(description="List of evaluation criteria")


class AblatedPrompt(BaseModel):
    """An ablated prompt for a ResearchRubrics task."""
    sample_id: str = Field(description="Task identifier this ablation belongs to")
    ablated_prompt: str = Field(description="Prompt with context removed")
    ablation_type: Literal["preference_removal", "scope_removal", "full"] = Field(
        default="preference_removal",
        description="Type of ablation applied"
    )
    removed_elements: list[str] | None = Field(
        default=None,
        description="What was removed from the original prompt"
    )


class AblatedPromptsFile(BaseModel):
    """Schema for the ablated_prompts.json file."""
    version: str = Field(default="1.0", description="Schema version")
    created_at: str = Field(description="ISO 8601 timestamp")
    prompts: list[AblatedPrompt] = Field(description="List of ablated prompts")


class RubricAxisSummary(BaseModel):
    """Summary stats for one axis type."""
    count: int = Field(description="Number of criteria in this axis")
    weight: float = Field(description="Sum of weights for this axis")


class RubricSummary(BaseModel):
    """Summary statistics for a task's rubrics."""
    total_criteria: int
    total_weight: float
    by_axis: dict[str, RubricAxisSummary]


class ResearchRubricsBenchmarkData(BaseModel):
    """Stored in Experiment.benchmark_specific_data for ResearchRubrics."""
    domain: str = Field(description="Task domain")
    original_prompt: str = Field(description="Unablated prompt for stakeholder")
    ablation_type: str | None = Field(default=None, description="Type of ablation applied")
    removed_elements: list[str] | None = Field(default=None, description="What was ablated")
    rubric_summary: RubricSummary = Field(description="Aggregated rubric statistics")
```

**Import Pattern:**
```python
# From within benchmarks/researchrubrics/loader.py:
from h_arcane.benchmarks.researchrubrics.schemas import (
    ResearchRubricsTask,
    AblatedPromptsFile,
    ResearchRubricsBenchmarkData,
)

# From shared schemas:
from h_arcane.schemas.base import BenchmarkType, BenchmarkConfig
```

### Unified Evaluation Architecture

All benchmarks use the same evaluation pattern:
1. **Flatten** criteria from benchmark-specific format → list of criteria
2. **Evaluate** each criterion in parallel (via Inngest)
3. **Aggregate** results back into structure
4. **Calculate** final scores

**Criterion types by benchmark:**
- **GDPEval**: Uses `StagedRubric` schema with `CodeRule` and `LLMJudgeRule`
- **MiniF2F**: Uses `ProofVerificationRule` for Lean verification
- **ResearchRubrics**: Uses `LLMJudgeRule` with weighted criteria from dataset

**Self-Evaluating Rules Architecture:**
```python
# schemas/staged_rubric_schema.py
from abc import ABC, abstractmethod
from typing import Annotated, Literal, Union, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from h_arcane.evaluation.context import EvaluationContext
    from h_arcane.db.models import CriterionResult

# Base rule class with common fields
class BaseRule(BaseModel, ABC):
    """Base class for all evaluation rules."""
    name: str
    description: str
    weight: float = 1.0
    
    @abstractmethod
    async def evaluate(self, context: "EvaluationContext") -> "CriterionResult":
        """Each rule knows how to evaluate itself."""
        ...

class CodeRule(BaseRule):
    """Evaluates via Python code execution in sandbox."""
    type: Literal["code"] = "code"
    code: str
    
    async def evaluate(self, context: "EvaluationContext") -> "CriterionResult":
        # Execute Python code in sandbox
        return await execute_code_in_sandbox(self.code, context)

class LLMJudgeRule(BaseRule):
    """Evaluates via LLM judge call."""
    type: Literal["llm_judge"] = "llm_judge"
    judge_prompt: str
    expectation: str | None = None
    # Extended fields for structured output (ResearchRubrics)
    response_format: Literal["score", "checklist", "pointwise"] = "score"
    response_schema: dict | None = None
    
    async def evaluate(self, context: "EvaluationContext") -> "CriterionResult":
        # Call LLM judge with appropriate parsing
        return await call_llm_judge(self, context)

class ProofVerificationRule(BaseRule):
    """Evaluates via formal proof verification (Lean)."""
    type: Literal["proof_verification"] = "proof_verification"
    problem_statement: str
    formal_system: Literal["lean"] = "lean"
    
    async def evaluate(self, context: "EvaluationContext") -> "CriterionResult":
        # Verify proof in Lean
        return await verify_lean_proof(self, context)

# Discriminated union - Pydantic routes based on "type" field
AnyRule = Annotated[
    Union[CodeRule, LLMJudgeRule, ProofVerificationRule],
    Field(discriminator="type")
]

# Benchmark-specific types (subsets of AnyRule)
GDPEvalRule = Annotated[Union[CodeRule, LLMJudgeRule], Field(discriminator="type")]
MiniF2FRule = ProofVerificationRule
ResearchRubricsRule = LLMJudgeRule
```

**Evaluation Context:**
```python
# evaluation/context.py
from uuid import UUID
from pydantic import BaseModel, Field
from h_arcane.db.models import Resource
from h_arcane.agents.sandbox import SandboxManager

class EvaluationContext(BaseModel):
    """All context needed by any rule to evaluate."""
    run_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[Resource]
    sandbox_manager: SandboxManager | None = None
    stage_idx: int
    rule_idx: int
    max_score: float
    
    class Config:
        arbitrary_types_allowed = True  # For SandboxManager
```

**Criteria Evaluator:**
```python
# evaluation/criteria_evaluator.py
async def evaluate_criterion(
    rule: AnyRule,
    context: EvaluationContext,
) -> CriterionResult:
    """Evaluate any rule - each rule implements its own evaluation logic."""
    return await rule.evaluate(context)
```

### Evaluation Flow (Unified)

```
Benchmark-specific format
    ↓
criteria.py (benchmark-specific converter)
    ↓
List[Criterion] (unified format)
    ↓
evaluate_task_run() (unified orchestrator)
    ↓
Parallel evaluation via Inngest
    ↓
Aggregate results
    ↓
Calculate final scores
```

### Example: How Each Benchmark Provides Criteria

**GDPEval** (already works):
```python
# benchmarks/gdpeval/criteria.py
def to_criteria(staged_rubric: StagedRubric) -> list[Criterion]:
    return flatten_rubric(staged_rubric)  # Uses existing flatten_rubric()
```

**MiniF2F** (uses `ProofVerificationRule`):
```python
# benchmarks/minif2f/criteria.py
from h_arcane.schemas.staged_rubric_schema import ProofVerificationRule

def to_criteria(problem: MiniF2FProblem) -> list[ProofVerificationRule]:
    return [
        ProofVerificationRule(
            name="proof_correctness",
            description="Verify that the proof compiles and verifies in Lean",
            weight=1.0,
            problem_statement=problem.statement,
            formal_system="lean",
        )
    ]
```


## MiniF2F Deep Dive: What It Is and How Verification Works

### What is MiniF2F?

MiniF2F is a **formal mathematics benchmark** consisting of:
- **488 problems** from olympiad competitions (AMC, AIME, IMO) and math courses
- **Formalized** in proof assistants: Lean, Metamath, Isabelle, HOL Light
- **Split**: 244 validation + 244 test problems
- **Coverage**: All 244 problems available in Lean (100% coverage)

**Example Problem** (informal → formal):
```
Informal: "Prove that for any positive integer n, 1 + 2 + ... + n = n(n+1)/2"

Lean formalization:
theorem sum_formula (n : ℕ) : (Finset.range n.succ).sum id = n * (n + 1) / 2 := by
  -- Agent must provide proof here
```

### How Do We Know If the Answer Is Correct?

**Key Insight**: In formal mathematics, correctness is **deterministic** - the proof either verifies or it doesn't.

**Verification Process**:
1. Agent produces Lean code (theorem statement + proof)
2. We compile/verify it with Lean compiler
3. **Result**: 
   - ✅ **Success** (exit code 0) → Proof is mathematically correct → Score: 1.0
   - ❌ **Failure** (exit code ≠ 0) → Proof is incorrect/incomplete → Score: 0.0

**Why This Works**:
- Lean is a **proof assistant** - it checks logical soundness, not just syntax
- If Lean accepts the proof, it's **mathematically correct** (by construction)
- **No partial credit**: Binary outcome (verified or not)
- **No LLM judging needed**: Deterministic verification

**Example**:
```lean
-- ✅ Correct proof:
theorem example (n : ℕ) : n + 0 = n := by simp

-- ❌ Broken proof:
theorem example (n : ℕ) : n + 0 = n := by sorry  -- "sorry" is cheating, won't verify
```

### Lean Tool Responses

```python
# h_arcane/tools/formal_math/responses.py

from pydantic import BaseModel, Field
from h_arcane.tools.responses import ToolResponse

class WriteLeanResponse(ToolResponse):
    """Response from write_lean_file tool."""
    filename: str | None = Field(default=None, description="Path to the written file")
    bytes_written: int | None = Field(default=None, description="Number of bytes written")

class LeanCheckResponse(ToolResponse):
    """Response from check_lean_file - includes goal information for iterative development."""
    compiled: bool = Field(default=False, description="Whether the file compiled (sorry allowed)")
    errors: list[str] | None = Field(default=None, description="Compilation errors if any")
    goals_remaining: list[str] | None = Field(default=None, description="Goals from sorry placeholders")
    warnings: list[str] | None = Field(default=None, description="Compiler warnings")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "compiled": True,
                "errors": None,
                "goals_remaining": ["⊢ 1 + 1 = 2"],
                "warnings": None,
            }
        }

class LeanVerificationResponse(ToolResponse):
    """Response from verify_lean_proof - final pass/fail (no sorry allowed)."""
    verified: bool = Field(default=False, description="Whether the proof compiled and verified")
    errors: str | None = Field(default=None, description="Compilation/verification errors if failed")
    output: str | None = Field(default=None, description="Lean compiler output")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "verified": True,
                "errors": None,
                "output": "theorem example verified",
            }
        }
```

### Lean Agent Workflow

Agents can use two approaches:

**Approach 1: Quick verification (simple proofs)**
```
Agent generates complete proof → verify_lean_proof → pass/fail
```

**Approach 2: Iterative development (complex proofs)**
```
1. write_lean_file with theorem + sorry placeholder
2. check_lean_file → see remaining goals
3. Update proof with tactics, more sorrys if needed
4. check_lean_file → see new goals
5. Repeat until no goals remain
6. verify_lean_proof → final confirmation
```

The key is **`sorry`** - a placeholder that lets Lean type-check partial proofs and show what's left to prove.

### How We'll Run Lean Verification

#### Step 1: Lean Installation in Sandbox

**Install on-demand in sandbox**
```python
# In sandbox setup (lazy initialization)
async def ensure_lean_installed(sandbox: Sandbox) -> bool:
    """Check if Lean is installed, install if not."""
    # Check if elan exists
    check_result = await sandbox.execute("which elan", timeout=5)
    if check_result.exit_code == 0:
        return True  # Already installed
    
    # Install elan (Lean version manager)
    install_result = await sandbox.execute(
        "curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh",
        timeout=60,
    )
    if install_result.exit_code != 0:
        return False
    
    # Install stable Lean toolchain
    toolchain_result = await sandbox.execute(
        "export PATH=$HOME/.elan/bin:$PATH && elan toolchain install stable",
        timeout=120,  # Can take a while
    )
    
    return toolchain_result.exit_code == 0
```

**Usage**: Call `ensure_lean_installed()` before first proof verification, cache result per sandbox.

#### Step 2: Create Lean Project Structure

For each MiniF2F problem, we need:
```
/workspace/
├── LeanProject.lean  # Main file with problem statement + agent's proof
└── leanpkg.toml      # Project dependencies (if needed)
```

**Problem Setup**:
```python
# benchmarks/minif2f/loader.py
def setup_lean_problem(problem: MiniF2FProblem) -> str:
    """Create Lean file with problem statement."""
    return f"""
import Mathlib.Tactic

-- Problem statement from MiniF2F
{problem.statement}

-- Agent must prove this theorem
theorem solution : {problem.goal} := by
  -- Agent's proof goes here
"""
```

#### Step 3: Agent Develops Proof

Agents have three tools for proof development:

**Tool 1: Write Lean file (for iterative development)**
```python
# tools/formal_math/lean_write.py
from h_arcane.tools.formal_math.responses import WriteLeanResponse

@function_tool
async def write_lean_file(filename: str, content: str) -> WriteLeanResponse:
    """
    Write or update a Lean proof file. Use this to build proofs incrementally.
    
    Use `sorry` as a placeholder to mark incomplete parts:
    
    theorem example : 1 + 1 = 2 := by
      sorry  -- Placeholder, check_lean_file will show the goal
    
    Args:
        filename: Name of the Lean file (e.g., "proof.lean")
        content: Complete Lean file content
    
    Returns:
        WriteLeanResponse with filename and bytes written
    """
    sandbox = get_sandbox_from_context()
    filepath = f"/workspace/{filename}"
    await sandbox.write_file(filepath, content)
    
    return WriteLeanResponse(
        success=True,
        filename=filepath,
        bytes_written=len(content.encode()),
    )
```

**Tool 2: Check Lean file (see errors and remaining goals)**
```python
# tools/formal_math/lean_check.py
from h_arcane.tools.formal_math.responses import LeanCheckResponse

@function_tool
async def check_lean_file(filename: str) -> LeanCheckResponse:
    """
    Check a Lean file for errors and remaining goals.
    
    This is useful for iterative proof development:
    - Shows compilation errors if syntax/type errors exist
    - Shows remaining goals from `sorry` placeholders
    - Allows partial proofs to type-check
    
    Args:
        filename: Name of the Lean file to check
    
    Returns:
        LeanCheckResponse with compiled status, errors, and goals_remaining
    """
    sandbox = get_sandbox_from_context()
    await ensure_lean_installed(sandbox)
    
    filepath = f"/workspace/{filename}"
    result = await sandbox.execute(
        f"export PATH=$HOME/.elan/bin:$PATH && lean {filepath} 2>&1",
        timeout=60,
    )
    
    # Parse output for goals and errors
    errors, goals = parse_lean_output(result.stdout + result.stderr)
    
    return LeanCheckResponse(
        success=True,
        compiled=result.exit_code == 0 or "sorry" in result.stdout,
        errors=errors if errors else None,
        goals_remaining=goals if goals else None,
    )
```

**Tool 3: Verify final proof (no sorry allowed)**
```python
# tools/formal_math/lean_verify.py
from h_arcane.tools.formal_math.responses import LeanVerificationResponse

@function_tool
async def verify_lean_proof(proof_code: str) -> LeanVerificationResponse:
    """
    Verify a complete Lean proof (no `sorry` allowed).
    
    Use this for final verification after developing the proof.
    For iterative development, use write_lean_file + check_lean_file instead.
    
    Args:
        proof_code: Complete Lean code including theorem statement and proof
    
    Returns:
        LeanVerificationResponse with verified status and any errors
    """
    sandbox = get_sandbox_from_context()
    await ensure_lean_installed(sandbox)
    
    # Check for sorry - not allowed in final verification
    if "sorry" in proof_code:
        return LeanVerificationResponse(
            success=True,
            verified=False,
            errors="Proof contains 'sorry' - incomplete proof not allowed for verification",
        )
    
    await sandbox.write_file("/workspace/verify.lean", proof_code)
    
    result = await sandbox.execute(
        "export PATH=$HOME/.elan/bin:$PATH && lean --check /workspace/verify.lean",
        timeout=60,
    )
    
    return LeanVerificationResponse(
        success=True,
        verified=result.exit_code == 0,
        errors=result.stderr if result.exit_code != 0 else None,
        output=result.stdout,
    )
```

**Example Agent Workflow:**
```
Agent: I'll start with the theorem and sorry to see what I need to prove.

[write_lean_file("proof.lean", """
import Mathlib.Tactic

theorem sum_formula (n : ℕ) : (Finset.range n.succ).sum id = n * (n + 1) / 2 := by
  sorry
""")]

[check_lean_file("proof.lean")]
→ goals_remaining: ["⊢ (Finset.range n.succ).sum id = n * (n + 1) / 2"]

Agent: I'll try induction on n.

[write_lean_file("proof.lean", """
...
theorem sum_formula (n : ℕ) : ... := by
  induction n with
  | zero => sorry
  | succ n ih => sorry
""")]

[check_lean_file("proof.lean")]
→ goals_remaining: ["⊢ 0 = 0", "⊢ ... = (n+1)*(n+2)/2"]

Agent: Base case is trivial, inductive case needs arithmetic...
[continues iterating until no goals remain]

[verify_lean_proof(final_proof)]
→ verified: true
```

#### Step 4: Evaluation (Proof Verification)

**In `ProofVerificationRule.evaluate()`:**
```python
class ProofVerificationRule(BaseRule):
    """Rule for verifying formal proofs in Lean."""
    type: Literal["proof_verification"] = "proof_verification"
    problem_statement: str
    formal_system: Literal["lean"] = "lean"
    
    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        """Verify Lean proof."""
        problem_statement = self.problem_statement
        
        # Extract Lean code from agent output (via context)
        # Option 1: Agent writes proof to a .lean file
        lean_file = next((r for r in context.agent_outputs if r.name.endswith('.lean')), None)
        if lean_file:
            proof_code = lean_file.load_text()
        else:
            # Option 2: Extract from agent_reasoning (if agent outputs code directly)
            proof_code = _extract_lean_code(context.agent_reasoning)
    
    # Combine with problem statement
    full_code = f"""
{problem_statement}

-- Agent's proof:
{proof_code}
"""
    
        # Verify in sandbox (access via context)
        sandbox = context.sandbox_manager.get_sandbox(context.run_id)
        
        # Ensure Lean is installed (on-demand)
    from h_arcane.tools.formal_math.lean import ensure_lean_installed
    if not await ensure_lean_installed(sandbox):
        return CriterionResult(
            # ... error: Lean installation failed
            score=0.0,
            feedback="Failed to install Lean compiler in sandbox.",
        )
    
    # Write to sandbox
    await sandbox.write_file("/workspace/LeanProject.lean", full_code)
    
    # Run Lean compiler (with PATH set)
    result = await sandbox.execute(
        "export PATH=$HOME/.elan/bin:$PATH && cd /workspace && lean --check LeanProject.lean",
        timeout=30,
    )
    
    # Parse result
    if result.exit_code == 0:
        score = max_score  # Proof verified!
        feedback = "Proof successfully verified by Lean compiler."
    else:
        score = 0.0
        feedback = f"Proof verification failed:\n{result.stderr}"
    
    return CriterionResult(
        run_id=run_id,
        stage_num=0,  # Single stage for MiniF2F
        stage_name="proof_verification",
        criterion_num=0,
        criterion_type="proof_verification",
        criterion_description=self.description,
        score=score,
        max_score=context.max_score,
        feedback=feedback,
        evaluation_input=full_code,
        evaluated_resource_ids=[str(r.id) for r in context.agent_outputs if r.name.endswith('.lean')],
    )
```

#### Step 5: Lean Compiler Command Details

**Basic verification**:
```bash
lean --check LeanProject.lean
```

**With dependencies** (if using Mathlib):
```bash
# First build dependencies
leanpkg build

# Then check
lean --check LeanProject.lean
```

**Error handling**:
- Exit code 0: Success (proof verified)
- Exit code 1: Compilation error (syntax, type errors, proof gaps)
- Timeout: Proof too complex or infinite loop

**Output parsing**:
```python
# Lean outputs errors to stderr
if result.exit_code != 0:
    errors = result.stderr
    # Parse errors like:
    # "LeanProject.lean:5:8: error: unknown identifier 'x'"
    # "LeanProject.lean:10:15: error: type mismatch"
```

### Comparison with Other Benchmarks

| Aspect | GDPEval | MiniF2F | ResearchRubrics |
|--------|---------|---------|-----------------|
| **Verification** | Rubric-based (stages, criteria) | Binary (verifies or not) | Weighted criteria by axis |
| **Scoring** | Partial credit (0.0 - max_score) | Binary (0.0 or 1.0) | Weighted sum across ~25 criteria |
| **Evaluation** | Code rules + LLM judges | Lean compiler | LLM judges per criterion |
| **Feedback** | Detailed rubric feedback | Compilation errors | Per-criterion scores + axis breakdown |
| **Deterministic** | No (LLM judges) | Yes (compiler) | No (LLM judges) |
| **Research Focus** | Task completion | Proof correctness | Adaptive stakeholder querying |

**ResearchRubrics** (uses `LLMJudgeRule` with dataset criteria):
```python
# benchmarks/researchrubrics/criteria.py
from h_arcane.schemas.staged_rubric_schema import LLMJudgeRule

def to_criteria(task: ResearchRubricsTask) -> list[LLMJudgeRule]:
    """Convert ResearchRubrics task to list of LLMJudgeRule criteria."""
    return [
        LLMJudgeRule(
            type="llm_judge",
            name=f"criterion_{i}",
            description=rubric['criterion'],
            weight=rubric['weight'],
            judge_prompt=build_criterion_judge_prompt(rubric['criterion']),
            axis=rubric['axis'],  # For analysis: Implicit/Explicit/Synthesis/etc.
        )
        for i, rubric in enumerate(task.rubrics)
    ]

def build_criterion_judge_prompt(criterion: str) -> str:
    """Build a judge prompt for a single criterion."""
    return f"""You are evaluating a research report against a specific criterion.

CRITERION: {criterion}

Evaluate whether the report meets this criterion. Consider:
- Is the criterion fully addressed?
- Is the information accurate and well-supported?
- Is it presented clearly?

Respond with a JSON object:
{{
    "met": true/false,
    "score": 0.0-1.0,
    "reasoning": "explanation"
}}
"""
```

**Extended `LLMJudgeRule` fields for ResearchRubrics:**
- `axis: str | None` - Criterion axis type (Implicit/Explicit/Synthesis/etc.) for analysis
- `weight: float` - From dataset (can be negative for penalty criteria)

## Core Abstractions

#### 1. Benchmark Interface

```python
# h_arcane/benchmarks/base.py

from abc import ABC, abstractmethod
from uuid import UUID
from typing import Protocol
from h_arcane.db.models import Experiment, Run, Resource

class BenchmarkLoader(Protocol):
    """Protocol for loading benchmark data."""
    def load_tasks(self, limit: int | None = None) -> list[dict]:
        """Load tasks from benchmark dataset."""
        ...
    
    def load_to_database(self, tasks: list[dict]) -> list[UUID]:
        """Load tasks into database as Experiment records."""
        ...

class BenchmarkStakeholder(ABC):
    """Base class for benchmark-specific stakeholders."""
    @abstractmethod
    async def answer(self, question: str) -> str:
        """Answer a question based on benchmark context."""
        ...

# All benchmarks use the same evaluation orchestrator:
# 1. Flatten criteria (from StagedRubric or benchmark-specific format)
# 2. Evaluate each criterion in parallel
# 3. Aggregate results
# 4. Calculate final scores
#
# Criteria are defined differently per benchmark:
# - GDPEval: Uses StagedRubric schema (stages → rules)
# - MiniF2F: Single criterion (proof_correctness)
# - ResearchRubrics: ~25 weighted criteria per task, organized by axis type
#
# All produce CriterionResult objects that get aggregated the same way.

class BenchmarkConfig(BaseModel):
    """Configuration for a benchmark."""
    benchmark_type: BenchmarkType
    system_prompt: str
    tools: list[str]  # Tool names
    max_questions: int
    evaluation_criteria: list[str]  # Names of criteria (for reference)

# Benchmark-specific criteria converters
class BenchmarkCriteriaConverter(Protocol):
    """Protocol for converting benchmark data to criteria list."""
    def to_criteria(
        self,
        benchmark_data: dict,  # Benchmark-specific data (StagedRubric, problem, query)
    ) -> list[Criterion]:  # Unified criteria format
        """Convert benchmark-specific format to unified criteria list."""
        ...
```

#### 2. Unified Worker

```python
# h_arcane/agents/worker.py

class BaseWorker:
    """Unified worker that works with any benchmark."""
    
    def __init__(
        self,
        model: str,
        benchmark_config: BenchmarkConfig,
        toolkit: BaseToolkit,
    ):
        self.model = model
        self.config = benchmark_config
        self.toolkit = toolkit
    
    async def execute(
        self,
        run_id: UUID,
        task_description: str,
        input_resources: list[Resource],
    ) -> WorkerExecutionOutput:
        """Execute task with benchmark-specific tools and prompt."""
        # Create agent with benchmark-specific system prompt and tools
        agent = Agent[WorkerContext](
            name="TaskWorker",
            model=self.model,
            instructions=self.config.system_prompt,
            tools=self.toolkit.get_tools(),
            output_type=WorkerExecutionOutput,
        )
        # ... rest of execution logic
```

#### 3. Database Schema Extensions

```python
# h_arcane/db/models.py

class BenchmarkType(str, Enum):
    """Supported benchmark types."""
    GDPEVAL = "gdpeval"
    MINIF2F = "minif2f"
    RESEARCHRUBRICS = "researchrubrics"

class Experiment(SQLModel, table=True):
    # ... existing fields ...
    benchmark_type: BenchmarkType = Field(index=True)
    benchmark_specific_data: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON)
    )  # Flexible storage for benchmark-specific fields

class Run(SQLModel, table=True):
    # ... existing fields ...
    benchmark_type: BenchmarkType = Field(index=True)
    benchmark_specific_results: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON)
    )  # Flexible storage for benchmark-specific results
```

## Implementation Plan

### Phase 1: Foundation & Schema Extensions (Week 1)

1. **Schema extensions** (`staged_rubric_schema.py`)
   - [ ] Refactor rules to inherit from `BaseRule` (ABC with abstract `evaluate()` method)
   - [ ] Each rule class implements its own `evaluate(context: EvaluationContext) -> CriterionResult`
   - [ ] Create discriminated union `AnyRule = Annotated[Union[CodeRule, LLMJudgeRule, ProofVerificationRule], Field(discriminator="type")]`
   - [ ] Create benchmark-specific type aliases (`GDPEvalRule`, `MiniF2FRule`, `ResearchRubricsRule`)

2. **Evaluation context** (`evaluation/context.py`)
   - [ ] Create `EvaluationContext` Pydantic BaseModel
   - [ ] Includes: run_id, task_input, agent_reasoning, agent_outputs, sandbox_manager, stage_idx, rule_idx, max_score
   - [ ] Set `arbitrary_types_allowed = True` in Config for SandboxManager

3. **Evaluator simplification** (`criteria_evaluator.py`)
   - [ ] Replace if-else routing with polymorphic `rule.evaluate(context)`
   - [ ] Move `_evaluate_code_rule()` logic into `CodeRule.evaluate()`
   - [ ] Move `_evaluate_llm_judge()` logic into `LLMJudgeRule.evaluate()`

4. **Create benchmark abstraction layer**
   - [ ] Create `h_arcane/benchmarks/base.py` with base classes
   - [ ] Move GDPEval-specific code to `h_arcane/benchmarks/gdpeval/`
   - [ ] Create `BenchmarkConfig` Pydantic model
   - [ ] Update database models with `benchmark_type` enum

5. **Refactor worker and toolkit**
   - [ ] Create `BaseWorker` class
   - [ ] Refactor `ReActWorker` to extend `BaseWorker`
   - [ ] Create `BaseToolkit` interface
   - [ ] Refactor `WorkerToolkit` to implement `BaseToolkit`

6. **Update experiment loading**
   - [ ] Move GDPEval loader to `benchmarks/gdpeval/loader.py`
   - [ ] Create benchmark registry/factory pattern
   - [ ] Update `run_experiments.py` to support benchmark selection

### Phase 2: MiniF2F Integration (Week 2)

1. **MiniF2F data loading**
   - [ ] Create `benchmarks/minif2f/loader.py`
   - [ ] Implement loading from MiniF2F repository (Lean files)
   - [ ] Parse problem statements and ground truth proofs
   - [ ] Store in database with `benchmark_type=BenchmarkType.MINIF2F`

2. **Formal math tools**
   - [ ] Create `tools/formal_math/responses.py`:
     - `WriteLeanResponse` - for write_lean_file
     - `LeanCheckResponse` - for check_lean_file (includes goals_remaining)
     - `LeanVerificationResponse` - for verify_lean_proof
   - [ ] Create `tools/formal_math/lean_write.py`:
     - `write_lean_file(filename, content)` - write/update proof files
   - [ ] Create `tools/formal_math/lean_check.py`:
     - `check_lean_file(filename)` - check for errors AND remaining goals
     - `parse_lean_output()` - parse Lean output to extract goals
   - [ ] Create `tools/formal_math/lean_verify.py`:
     - `verify_lean_proof(proof_code)` - final verification (no sorry)
   - [ ] Create `tools/formal_math/utils.py`:
     - `ensure_lean_installed()` - on-demand installation
     - `get_sandbox_from_context()` - helper to get current sandbox
   - [ ] Cache Lean installation status per sandbox

3. **MiniF2F criteria definition**
   - [ ] Create `benchmarks/minif2f/criteria.py`
   - [ ] Define function to convert MiniF2F problem → criteria list
   - [ ] Single criterion: "proof_correctness" (binary: 0 or 1)
   - [ ] Add `ProofVerificationRule` to `staged_rubric_schema.py` (extends `BaseRule` from Phase 1)
   - [ ] Implement `ProofVerificationRule.evaluate()`:
     - Returns score 1.0 if proof verifies, 0.0 if it fails
     - Provides compilation/verification errors as feedback

4. **MiniF2F stakeholder**
   - [ ] Create `benchmarks/minif2f/stakeholder.py`
   - [ ] Implement proof verifier that provides feedback
   - [ ] Answer questions about proof requirements

### Phase 3: ResearchRubrics Integration (Week 3)

1. **ResearchRubrics data loading**
   - [ ] Create `benchmarks/researchrubrics/loader.py`
   - [ ] Load from HuggingFace: `ScaleAI/researchrubrics`
   - [ ] Load ablated prompts (created separately, manual with QA)
   - [ ] Parse rubrics: extract criterion, weight, axis for each task
   - [ ] Store in database with `benchmark_type=BenchmarkType.RESEARCHRUBRICS`
   - [ ] Store original (unablated) prompts for stakeholder reference

2. **Web research tools**
   - [ ] Create `tools/web_research/responses.py` with `ExaSearchResponse`, `ExaQAResponse`, `ExaGetContentResponse`
   - [ ] Create `tools/web_research/exa_search.py` returning `ExaSearchResponse`
   - [ ] Create `tools/web_research/exa_qa.py` returning `ExaQAResponse`
   - [ ] Create `tools/web_research/exa_get_content.py` returning `ExaGetContentResponse`
   - [ ] Configure Exa API key in settings
   - [ ] Tools execute in sandbox (web access needed)

3. **ResearchRubrics criteria definition**
   - [ ] Create `benchmarks/researchrubrics/criteria.py`
   - [ ] Convert dataset rubrics to `LLMJudgeRule` list:
     ```python
     def to_criteria(task: ResearchRubricsTask) -> list[LLMJudgeRule]:
         return [
             LLMJudgeRule(
                 name=f"criterion_{i}",
                 description=rubric['criterion'],
                 weight=rubric['weight'],
                 judge_prompt=build_criterion_judge_prompt(rubric),
                 axis=rubric['axis'],  # Track for analysis
             )
             for i, rubric in enumerate(task.rubrics)
         ]
     ```
   - [ ] Extend `LLMJudgeRule` with `axis: str | None` field for analysis
   - [ ] Build judge prompts that evaluate if criterion is met in output

4. **ResearchRubrics stakeholder**
   - [ ] Create `benchmarks/researchrubrics/stakeholder.py`
   - [ ] Implement `RubricAwareStakeholder`:
     - Has access to: rubric criteria + original (unablated) question
     - Answers based on what rubric criteria expect
     - Responds "I don't have a preference on that" for out-of-scope questions
   - [ ] LLM-based with guardrails to prevent leaking full rubric

5. **Question analysis metrics**
   - [ ] Create `benchmarks/researchrubrics/metrics.py`
   - [ ] Implement per-run metrics (automatic):
     - `question_count`: Total questions asked
     - `question_timing`: Early (first 25% of actions) / Mid / Late
     - `question_criterion_match`: Embed questions → match to criteria → sum weights
     - `implicit_criteria_addressed`: Questions that relate to Implicit Criteria axis
   - [ ] Implement aggregate analysis:
     - Score breakdown by axis type (Implicit vs Explicit vs Synthesis, etc.)
     - Correlation: question timing × final score on Implicit Criteria
   - [ ] Optional expensive metrics (for sampled runs):
     - `counterfactual_delta`: Re-run without questions, compare scores
     - `llm_question_quality`: Judge relevance/timing of each question

### Phase 4: Integration & Testing (Week 4)

1. **Unified CLI**
   - [ ] Update `run_experiments.py` to support `--benchmark` flag
   - [ ] Add benchmark-specific CLI options
   - [ ] Update progress tracking for all benchmarks

2. **Testing**
   - [ ] Unit tests for each benchmark loader
   - [ ] Unit tests for each rule type's `evaluate()` method
   - [ ] Integration tests for each benchmark
   - [ ] End-to-end tests for multi-baseline runs
   - [ ] Verify type safety per benchmark

## Configuration Examples

### GDPEval Configuration

```python
GDPEVAL_CONFIG = BenchmarkConfig(
    benchmark_type=BenchmarkType.GDPEVAL,
    system_prompt=REACT_WORKER_PROMPT,  # Existing prompt
    tools=[
        "ask_stakeholder",
        "read_pdf",
        "create_docx",
        "read_excel",
        "create_excel",
        "read_csv",
        "create_csv",
        "execute_python_code",
        "ocr_image",
    ],
    max_questions=10,
    evaluation_criteria=["staged_rubric"],
)
```

### MiniF2F Configuration

```python
MINIF2F_CONFIG = BenchmarkConfig(
    benchmark_type=BenchmarkType.MINIF2F,
    system_prompt="""
You are a formal mathematics assistant solving olympiad-level problems in Lean.

You have access to:
- `ask_stakeholder`: Ask questions about proof requirements
- `write_lean_file`: Write/update a Lean proof file
- `check_lean_file`: Check file for errors and see remaining goals (use with `sorry`)
- `verify_lean_proof`: Final verification of complete proof

**Recommended workflow for complex proofs:**
1. Start with theorem statement + `sorry` placeholder
2. Use `check_lean_file` to see what goals need proving
3. Replace `sorry` with tactics, add more `sorry` for sub-goals
4. Iterate until all goals are resolved
5. Use `verify_lean_proof` for final confirmation

**For simple proofs:** Use `verify_lean_proof` directly.

Think step by step. Build proofs incrementally to see intermediate goals.
""",
    tools=[
        "ask_stakeholder",
        "write_lean_file",
        "check_lean_file",
        "verify_lean_proof",
    ],
    max_questions=5,
    evaluation_criteria=["proof_correctness"],
)
```

### ResearchRubrics Configuration

```python
RESEARCHRUBRICS_CONFIG = BenchmarkConfig(
    benchmark_type=BenchmarkType.RESEARCHRUBRICS,
    system_prompt="""
You are a deep research assistant producing comprehensive research reports.

You have access to:
- `ask_stakeholder`: Ask clarification questions about requirements and preferences
- `exa_search`: Search the web for information
- `exa_qa`: Get answers to specific questions
- `exa_get_content`: Extract content from URLs

The task description may be incomplete or ambiguous. When you encounter uncertainty 
about what the stakeholder wants, ask clarifying questions. Consider asking about:
- Scope and depth of coverage
- Preferred evidence standards (academic, practical, etc.)
- Format and presentation preferences
- Any specific requirements not clear from the task

Produce well-cited, comprehensive reports that address the stakeholder's needs.
""",
    tools=[
        "ask_stakeholder",
        "exa_search",
        "exa_qa",
        "exa_get_content",
    ],
    max_questions=10,
    evaluation_criteria=[
        # Loaded dynamically from dataset rubrics
        # ~25 weighted criteria per task, organized by axis
    ],
)
```

## ResearchRubrics Research Design

### Research Questions (Ordered by Priority)
1. **Do agents know WHEN to ask?** - Timing analysis of stakeholder questions
2. **Does asking improve outcomes?** - Score comparison: asked vs didn't ask
3. **Do agents ask the RIGHT questions?** - Question-criterion relevance

### Metrics Collected

**Per-Run Metrics (Automatic):**
| Metric | Description |
|--------|-------------|
| `question_count` | Total stakeholder questions asked |
| `question_timing` | Distribution: early/mid/late in task |
| `question_criterion_match` | Similarity of questions to rubric criteria (weighted) |
| `implicit_criteria_addressed` | % of questions targeting Implicit Criteria axis |
| `score_by_axis` | Final scores broken down by axis type |

**Aggregate Analysis:**
| Analysis | Description |
|----------|-------------|
| Timing × Score | Correlation between mid-task questions and Implicit Criteria scores |
| Question Impact | Runs with questions vs without on same task |
| Axis Coverage | Which axis types benefit most from asking |

**Key Hypothesis:**
> "Agents that ask questions mid-task about Implicit Criteria score higher 
> on those criteria than agents that ask early or not at all"

### Axis Types (for Analysis)
| Axis | % of Criteria | Notes |
|------|---------------|-------|
| Implicit Criteria | 39.4% | Key target - agent can't know without asking |
| Explicit Criteria | 27.7% | In prompt, should survive ablation |
| Synthesis of Information | 15.8% | Quality of reasoning |
| Communication Quality | 7.8% | Style/format preferences |
| Instruction Following | 5.8% | Format constraints |
| References & Citation Quality | 3.5% | Source quality |

## Migration Strategy

1. **Backward compatibility**: Keep existing GDPEval code working during refactoring
2. **Gradual migration**: Move GDPEval code to new structure incrementally
3. **Feature flags**: Use feature flags to enable new benchmarks
4. **Database migration**: Add `benchmark_type` column with default "gdpeval"

## Exa API Integration Proposal

Based on the existing `manager_agent_gym` implementation, here's the proposed Exa integration:

### Exa Tool Responses

```python
# h_arcane/tools/web_research/responses.py

from pydantic import BaseModel, Field
from h_arcane.tools.responses import ToolResponse

class ExaSearchResult(BaseModel):
    """A single search result from Exa."""
    title: str
    url: str
    summary: str | None = None
    content: str | None = None
    published_date: str | None = None

class ExaSearchResponse(ToolResponse):
    """Response from exa_search tool."""
    query: str | None = Field(default=None, description="Original search query")
    results: list[ExaSearchResult] | None = Field(default=None, description="Search results")

class ExaQAResponse(ToolResponse):
    """Response from exa_qa tool."""
    question: str | None = Field(default=None, description="Original question")
    answer: str | None = Field(default=None, description="Answer synthesized from sources")
    sources: list[dict] | None = Field(default=None, description="Source citations")

class ExaGetContentResponse(ToolResponse):
    """Response from exa_get_content tool."""
    url: str | None = Field(default=None, description="URL that was fetched")
    title: str | None = Field(default=None, description="Page title")
    content: str | None = Field(default=None, description="Extracted content")
    published_date: str | None = Field(default=None, description="Publication date if available")
```

### Exa Tools Structure

```python
# h_arcane/tools/web_research/exa_search.py

from exa_py import Exa
from h_arcane.settings import settings
from h_arcane.tools.web_research.responses import ExaSearchResponse, ExaSearchResult

EXA_CLIENT = Exa(api_key=settings.exa_api_key)

@function_tool
async def exa_search(
    query: str,
    num_results: int = 5,
    start_published_date: str | None = None,
    category: str | None = None,
) -> ExaSearchResponse:
    """
    Search the web using Exa to get ranked search results with content.
    
    Args:
        query: Search query
        num_results: Number of results to return (default: 5)
        start_published_date: ISO 8601 date string for filtering results
        category: Content category (e.g., "news", "academic", "company")
    
    Returns:
        ExaSearchResponse with search results including titles, URLs, summaries, and content
    """
    results = EXA_CLIENT.search_and_contents(
        query,
        type="auto",
        text=True,
        start_published_date=start_published_date,
        category=category,
        num_results=num_results,
        summary=True,
    ).results
    
    return ExaSearchResponse(
        success=True,
        query=query,
        results=[
            ExaSearchResult(
                title=r.title,
                url=r.url,
                summary=r.summary,
                content=r.text[:5000] if r.text else None,
                published_date=r.published_date,
            )
            for r in results
        ]
    )

@function_tool
async def exa_qa(
    question: str,
    num_results: int = 3,
) -> ExaQAResponse:
    """
    Get direct answers to questions using Exa's QA capabilities.
    
    Args:
        question: Question to answer
        num_results: Number of sources to use
    
    Returns:
        ExaQAResponse with answer and source citations
    """
    from h_arcane.tools.web_research.responses import ExaQAResponse
    
    results = EXA_CLIENT.search_and_contents(
        question,
        type="neural",
        text=True,
        num_results=num_results,
        summary=True,
    ).results
    
    return ExaQAResponse(
        success=True,
        question=question,
        answer=results[0].summary if results else "No answer found",
        sources=[{"url": r.url, "title": r.title} for r in results]
    )

@function_tool
async def exa_get_content(
    url: str,
) -> ExaGetContentResponse:
    """
    Extract full content from a URL using Exa.
    
    Args:
        url: URL to extract content from
    
    Returns:
        ExaGetContentResponse with extracted content, title, and metadata
    """
    from h_arcane.tools.web_research.responses import ExaGetContentResponse
    
    result = EXA_CLIENT.get_contents(
        [url],
        text=True,
    ).results[0]
    
    return ExaGetContentResponse(
        success=True,
        url=url,
        title=result.title,
        content=result.text,
        published_date=result.published_date,
    )
```

### Settings Configuration

```python
# h_arcane/settings.py

class Settings(BaseSettings):
    # ... existing settings ...
    
    # Exa API
    exa_api_key: str = ""
```

### Cost Tracking

- **Exa API costs**: Track separately in `Action` table with `action_type="exa_search"` or `"exa_qa"`
- Add `api_cost_usd` field to Action model for external API costs
- Aggregate in Run's `total_cost_usd` field

## Remaining Implementation Details

1. **Lean Installation in Sandbox**: 
   - On-demand installation via `ensure_lean_installed()` (decision made)
   - Install elan → stable toolchain when first proof verification is requested
   - Cache installation status per sandbox
   - Test Lean compilation in sandbox environment

2. **Reference Report Storage**:
   - Store reference reports as Resources with `experiment_id` (not `run_id`)
   - Load on-demand during evaluation
   - Cache in memory for performance

3. **MiniF2F Problem Loading**:
   - Clone MiniF2F repo or use as submodule
   - Parse Lean files from `lean/valid.lean` and `lean/test.lean`
   - Extract problem statements and ground truth proofs

## Data Seeding: Detailed Implementation

This section describes exactly how each benchmark's data gets loaded into PostgreSQL, including schema requirements, loader implementations, and CLI commands.

### Database Schema (New)

Drop existing tables and use these SQLModel definitions as source of truth:

```python
# h_arcane/db/models.py

from enum import Enum
from uuid import UUID, uuid4
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, Index
from sqlalchemy import JSON


class BenchmarkType(str, Enum):
    """Supported benchmark types."""
    GDPEVAL = "gdpeval"
    MINIF2F = "minif2f"
    RESEARCHRUBRICS = "researchrubrics"


class Experiment(SQLModel, table=True):
    """A task from any supported benchmark."""

    __tablename__ = "experiments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # Benchmark identification
    benchmark_type: BenchmarkType = Field(index=True)
    task_id: str = Field(index=True)  # Unique per benchmark_type
    
    # Task definition
    task_description: str
    
    # Ground truth evaluation data (rubrics, problem statements, etc.)
    # Structure varies by benchmark_type
    ground_truth_rubric: dict = Field(sa_column=Column(JSON))
    
    # Benchmark-specific metadata (flexible JSON)
    benchmark_specific_data: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON)
    )
    
    # Generic metadata
    category: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_experiments_benchmark_task", "benchmark_type", "task_id", unique=True),
    )


class Run(SQLModel, table=True):
    """A single run of an experiment."""

    __tablename__ = "runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_id: UUID = Field(foreign_key="experiments.id", index=True)

    # Worker configuration
    worker_model: str = Field(default="gpt-4o")
    max_questions: int = Field(default=10)

    # Status
    status: RunStatus = Field(default=RunStatus.PENDING)
    error_message: str | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Execution output
    output_text: str | None = None
    output_resource_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Results
    final_score: float | None = None
    normalized_score: float | None = None
    questions_asked: int | None = None
    total_cost_usd: float | None = None

    # Benchmark-specific results (flexible JSON)
    benchmark_specific_results: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON)
    )
```

**Reset database:**
```bash
# Drop and recreate (dev only)
python -c "from h_arcane.db.connection import get_engine; from h_arcane.db.models import *; SQLModel.metadata.drop_all(get_engine()); SQLModel.metadata.create_all(get_engine())"
```

---

### GDPEval Seeding

**Data Sources:**
- `data/generated/staged_v2/staged_rubrics.jsonl` - Task rubrics
- `data/raw/gdpeval.parquet` - Task descriptions
- `data/raw/reference_files/{task_id}/` - Input files

**Schema Mapping:**

| Source Field | DB Field | Notes |
|-------------|----------|-------|
| `task_id` | `task_id` | From JSONL |
| `"gdpeval"` | `benchmark_type` | Hardcoded |
| `parquet.prompt` | `task_description` | Joined from parquet |
| `rubric` | `ground_truth_rubric` | Full StagedRubric JSON |
| `rubric.category_name` | `category` | First part before " – " |
| - | `benchmark_specific_data` | `{}` (not needed for GDPEval) |

**Loader Implementation:**

```python
# h_arcane/benchmarks/gdpeval/loader.py

from pathlib import Path
from uuid import UUID
from sqlmodel import Session, select
from h_arcane.db.connection import get_engine
from h_arcane.db.models import Experiment, Resource
from h_arcane.schemas.base import BenchmarkType
from h_arcane.benchmarks.gdpeval.schemas import GDPEvalTask

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"

def load_gdpeval_to_database(
    rubric_file: Path | None = None,
    reference_dir: Path | None = None,
    limit: int | None = None,
) -> list[UUID]:
    """Load GDPEval tasks into database."""
    
    if rubric_file is None:
        rubric_file = DATA_DIR / "generated" / "staged_v2" / "staged_rubrics.jsonl"
    if reference_dir is None:
        reference_dir = DATA_DIR / "raw" / "reference_files"
    
    experiment_ids = []
    engine = get_engine()
    
    with Session(engine) as session:
        for task in _parse_gdpeval_tasks(rubric_file, reference_dir, limit):
            # Check if exists
            existing = session.exec(
                select(Experiment).where(
                    Experiment.benchmark_type == BenchmarkType.GDPEVAL,
                    Experiment.task_id == task.task_id,
                )
            ).first()
            
            if existing:
                experiment_ids.append(existing.id)
                continue
            
            # Create experiment
            experiment = Experiment(
                benchmark_type=BenchmarkType.GDPEVAL,
                task_id=task.task_id,
                task_description=task.task_description,
                ground_truth_rubric=task.rubric.model_dump(),
                benchmark_specific_data={},  # GDPEval doesn't need extra data
                category=task.category,
            )
            session.add(experiment)
            session.flush()
            experiment_ids.append(experiment.id)
            
            # Create resource records for input files
            for ref_file in task.reference_files:
                resource = Resource(
                    experiment_id=experiment.id,
                    name=ref_file.name,
                    mime_type=_get_mime_type(ref_file),
                    file_path=str(ref_file.relative_to(DATA_DIR)),
                    size_bytes=ref_file.stat().st_size,
                )
                session.add(resource)
        
        session.commit()
    
    return experiment_ids
```

**CLI Command:**
```bash
python -m h_arcane.cli seed --benchmark gdpeval --limit 10
```

---

### MiniF2F Seeding

**Data Sources:**
- GitHub: `openai/miniF2F` repository
- Files: `lean/valid.lean`, `lean/test.lean`
- No authentication required (public repo)

**Problem Structure in Lean Files:**
```lean
-- Example from miniF2F
theorem aime_1983_p1
  (x y z w : ℕ)
  (ht : 1 < x ∧ 1 < y ∧ 1 < z)
  (hw : 0 ≤ w)
  (h0 : Nat.log x (w) = 24)
  (h1 : Nat.log y (w) = 40)
  (h2 : Nat.log (x * y * z) (w) = 12) :
  Nat.log z (w) = 60 := by
  sorry
```

**Schema Mapping:**

| Source Field | DB Field | Notes |
|-------------|----------|-------|
| theorem name (e.g., `aime_1983_p1`) | `task_id` | Extracted from Lean |
| `"minif2f"` | `benchmark_type` | Hardcoded |
| Generated instruction | `task_description` | "Prove the following theorem in Lean: {statement}" |
| `{"problem_statement": ..., "formal_system": "lean"}` | `ground_truth_rubric` | Single ProofVerificationRule |
| Split name | `category` | "valid" or "test" |
| Full problem data | `benchmark_specific_data` | See below |

**`benchmark_specific_data` Structure:**
```json
{
  "formal_system": "lean",
  "split": "valid",  // or "test"
  "source_file": "lean/valid.lean",
  "theorem_name": "aime_1983_p1",
  "full_statement": "theorem aime_1983_p1 ... := by\n  sorry",
  "competition": "aime",
  "year": 1983,
  "problem_number": 1
}
```

**Loader Implementation:**

```python
# h_arcane/benchmarks/minif2f/loader.py

import re
import subprocess
import tempfile
from pathlib import Path
from uuid import UUID
from sqlmodel import Session, select
from h_arcane.db.connection import get_engine
from h_arcane.db.models import Experiment
from h_arcane.schemas.base import BenchmarkType
from h_arcane.benchmarks.minif2f.schemas import (
    MiniF2FProblem,
    MiniF2FProblemMetadata,
    MiniF2FBenchmarkData,
)

MINIF2F_REPO = "https://github.com/openai/miniF2F.git"


def clone_minif2f_repo(target_dir: Path) -> Path:
    """Clone MiniF2F repository if not already present."""
    repo_dir = target_dir / "miniF2F"
    if not repo_dir.exists():
        subprocess.run(
            ["git", "clone", "--depth", "1", MINIF2F_REPO, str(repo_dir)],
            check=True,
        )
    return repo_dir


def parse_lean_file(lean_file: Path, split: str) -> list[MiniF2FProblem]:
    """Parse a Lean file to extract theorems."""
    content = lean_file.read_text()
    problems = []
    
    # Regex to match theorem definitions
    # Matches: theorem <name> ... := by
    theorem_pattern = re.compile(
        r'theorem\s+(\w+)\s*([^:]*:[^:=]+):=\s*by\s*sorry',
        re.DOTALL
    )
    
    for match in theorem_pattern.finditer(content):
        theorem_name = match.group(1)
        full_statement = match.group(0)
        
        problems.append(MiniF2FProblem(
            theorem_name=theorem_name,
            full_statement=full_statement.strip(),
            split=split,
            source_file=lean_file.name,
        ))
    
    return problems


def parse_theorem_metadata(theorem_name: str) -> MiniF2FProblemMetadata:
    """Extract competition/year/problem from theorem name."""
    # Pattern: {competition}_{year}_p{number} or {competition}_p{number}
    pattern = r'^([a-z]+)_?(\d{4})?_?p(\d+)$'
    match = re.match(pattern, theorem_name, re.IGNORECASE)
    
    if match:
        return MiniF2FProblemMetadata(
            competition=match.group(1),
            year=int(match.group(2)) if match.group(2) else None,
            problem_number=int(match.group(3)),
        )
    return MiniF2FProblemMetadata(competition="unknown")


def load_minif2f_to_database(
    repo_dir: Path | None = None,
    limit: int | None = None,
) -> list[UUID]:
    """Load MiniF2F problems into database."""
    
    # Clone repo if needed
    if repo_dir is None:
        repo_dir = clone_minif2f_repo(Path(tempfile.gettempdir()))
    
    experiment_ids = []
    engine = get_engine()
    
    # Parse both splits
    all_problems: list[MiniF2FProblem] = []
    for split in ["valid", "test"]:
        lean_file = repo_dir / "lean" / f"{split}.lean"
        if lean_file.exists():
            all_problems.extend(parse_lean_file(lean_file, split))
    
    print(f"📂 Found {len(all_problems)} MiniF2F problems")
    
    if limit:
        all_problems = all_problems[:limit]
    
    with Session(engine) as session:
        for problem in all_problems:
            # Check if exists
            existing = session.exec(
                select(Experiment).where(
                    Experiment.benchmark_type == BenchmarkType.MINIF2F,
                    Experiment.task_id == problem.theorem_name,
                )
            ).first()
            
            if existing:
                experiment_ids.append(existing.id)
                continue
            
            metadata = parse_theorem_metadata(problem.theorem_name)
            
            # Create strongly typed benchmark data
            benchmark_data = MiniF2FBenchmarkData(
                formal_system="lean",
                split=problem.split,
                source_file=problem.source_file,
                theorem_name=problem.theorem_name,
                full_statement=problem.full_statement,
                competition=metadata.competition,
                year=metadata.year,
                problem_number=metadata.problem_number,
            )
            
            # Create experiment
            experiment = Experiment(
                benchmark_type=BenchmarkType.MINIF2F,
                task_id=problem.theorem_name,
                task_description=f"Prove the following theorem in Lean:\n\n```lean\n{problem.full_statement}\n```",
                ground_truth_rubric={
                    "type": "proof_verification",
                    "name": "proof_correctness",
                    "description": "Verify that the proof compiles and verifies in Lean",
                    "weight": 1.0,
                    "problem_statement": problem.full_statement,
                    "formal_system": "lean",
                },
                benchmark_specific_data=benchmark_data.model_dump(),
                category=problem.split,  # "valid" or "test"
            )
            session.add(experiment)
            session.flush()
            experiment_ids.append(experiment.id)
        
        session.commit()
    
    print(f"✅ Loaded {len(experiment_ids)} MiniF2F problems to database")
    return experiment_ids
```

**CLI Command:**
```bash
python -m h_arcane.cli seed --benchmark minif2f --limit 50
```

---

### ResearchRubrics Seeding

**Data Sources:**
- HuggingFace: `ScaleAI/researchrubrics` (gated dataset)
- Ablated prompts: Created separately, stored locally

**Authentication Required:**
```bash
# HuggingFace login (one-time)
huggingface-cli login
# OR set environment variable
export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxx
```

**Settings Configuration:**
```python
# h_arcane/settings.py

class Settings(BaseSettings):
    # ... existing settings ...
    
    # HuggingFace (for gated datasets)
    hf_token: str | None = None  # Optional, uses cached credentials if not set
```

**Dataset Structure:**
```python
# From ScaleAI/researchrubrics
{
    "sample_id": "ai_ml_001",
    "domain": "AI & ML",
    "prompt": "Write a comprehensive report on...",
    "rubrics": [
        {
            "criterion": "The report should discuss transformer architectures",
            "axis": "Explicit Criteria",
            "weight": 3.0
        },
        {
            "criterion": "Consider computational efficiency trade-offs",
            "axis": "Implicit Criteria", 
            "weight": 2.0
        },
        # ... ~25 criteria per task
    ]
}
```

**Schema Mapping:**

| Source Field | DB Field | Notes |
|-------------|----------|-------|
| `sample_id` | `task_id` | From dataset |
| `"researchrubrics"` | `benchmark_type` | Hardcoded |
| Ablated prompt | `task_description` | From local ablated file |
| `rubrics` array | `ground_truth_rubric` | Converted to LLMJudgeRule list |
| `domain` | `category` | From dataset |
| Full task data | `benchmark_specific_data` | See below |

**`benchmark_specific_data` Structure:**
```json
{
  "domain": "AI & ML",
  "original_prompt": "Write a comprehensive report on...",  // Unablated, for stakeholder
  "ablation_type": "preference_removal",
  "rubric_summary": {
    "total_criteria": 25,
    "total_weight": 45.0,
    "by_axis": {
      "Implicit Criteria": {"count": 10, "weight": 18.0},
      "Explicit Criteria": {"count": 7, "weight": 12.0},
      "Synthesis of Information": {"count": 4, "weight": 8.0},
      "Communication Quality": {"count": 2, "weight": 4.0},
      "Instruction Following": {"count": 1, "weight": 2.0},
      "References & Citation Quality": {"count": 1, "weight": 1.0}
    }
  }
}
```

**Loader Implementation:**

```python
# h_arcane/benchmarks/researchrubrics/loader.py

import json
from pathlib import Path
from uuid import UUID
from datasets import load_dataset
from sqlmodel import Session, select
from h_arcane.db.connection import get_engine
from h_arcane.db.models import Experiment
from h_arcane.schemas.base import BenchmarkType
from h_arcane.settings import settings
from h_arcane.benchmarks.researchrubrics.schemas import (
    ResearchRubricsTask,
    RubricCriterion,
    AblatedPromptsFile,
    AblatedPrompt,
    ResearchRubricsBenchmarkData,
    RubricSummary,
    RubricAxisSummary,
)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
ABLATED_PROMPTS_FILE = DATA_DIR / "generated" / "researchrubrics" / "ablated_prompts.json"


def load_researchrubrics_dataset() -> list[ResearchRubricsTask]:
    """Load ResearchRubrics dataset from HuggingFace."""
    # Uses HF_TOKEN env var or cached credentials from `huggingface-cli login`
    token = settings.hf_token if settings.hf_token else True  # True = use cached
    
    ds = load_dataset(
        "ScaleAI/researchrubrics",
        token=token,
    )
    
    tasks = []
    for row in ds["train"]:
        rubrics = [
            RubricCriterion(
                criterion=r["criterion"],
                axis=r["axis"],
                weight=r["weight"],
            )
            for r in row["rubrics"]
        ]
        
        tasks.append(ResearchRubricsTask(
            sample_id=row["sample_id"],
            domain=row["domain"],
            original_prompt=row["prompt"],
            rubrics=rubrics,
        ))
    
    return tasks


def load_ablated_prompts() -> AblatedPromptsFile:
    """Load and validate ablated prompts from local file.
    
    Returns:
        Validated AblatedPromptsFile with list of AblatedPrompt objects
    """
    if not ABLATED_PROMPTS_FILE.exists():
        raise FileNotFoundError(
            f"Ablated prompts file not found at {ABLATED_PROMPTS_FILE}. "
            "Please create ablated prompts first (manual process with QA)."
        )
    
    with open(ABLATED_PROMPTS_FILE) as f:
        data = json.load(f)
    return AblatedPromptsFile.model_validate(data)


def compute_rubric_summary(rubrics: list[RubricCriterion]) -> RubricSummary:
    """Compute summary statistics for rubrics."""
    by_axis: dict[str, RubricAxisSummary] = {}
    
    for r in rubrics:
        if r.axis not in by_axis:
            by_axis[r.axis] = RubricAxisSummary(count=0, weight=0.0)
        by_axis[r.axis].count += 1
        by_axis[r.axis].weight += r.weight
    
    return RubricSummary(
        total_criteria=len(rubrics),
        total_weight=sum(r.weight for r in rubrics),
        by_axis=by_axis,
    )


def build_llm_judge_rules(rubrics: list[RubricCriterion]) -> list[dict]:
    """Convert rubrics to LLMJudgeRule format."""
    rules = []
    
    for i, r in enumerate(rubrics):
        rules.append({
            "type": "llm_judge",
            "name": f"criterion_{i}",
            "description": r.criterion,
            "weight": r.weight,
            "axis": r.axis,  # For analysis
            "judge_prompt": _build_criterion_judge_prompt(r.criterion),
            "response_format": "score",
        })
    
    return rules


def _build_criterion_judge_prompt(criterion: str) -> str:
    """Build judge prompt for a single criterion."""
    return f"""You are evaluating a research report against a specific criterion.

CRITERION: {criterion}

Evaluate whether the report meets this criterion. Consider:
- Is the criterion fully addressed?
- Is the information accurate and well-supported?
- Is it presented clearly?

Respond with a JSON object:
{{
    "met": true or false,
    "score": 0.0 to 1.0,
    "reasoning": "your explanation"
}}
"""


def get_ablation_for_task(
    task_id: str,
    ablations: AblatedPromptsFile | None,
) -> AblatedPrompt | None:
    """Find ablation for a specific task."""
    if not ablations:
        return None
    for ablation in ablations.prompts:
        if ablation.sample_id == task_id:
            return ablation
    return None


def create_benchmark_data(
    task: ResearchRubricsTask,
    ablation: AblatedPrompt | None,
) -> ResearchRubricsBenchmarkData:
    """Create strongly typed benchmark data for database storage."""
    return ResearchRubricsBenchmarkData(
        domain=task.domain,
        original_prompt=task.original_prompt,
        ablation_type=ablation.ablation_type if ablation else None,
        removed_elements=ablation.removed_elements if ablation else None,
        rubric_summary=compute_rubric_summary(task.rubrics),
    )


def load_researchrubrics_to_database(
    limit: int | None = None,
    skip_if_no_ablation: bool = True,
) -> list[UUID]:
    """Load ResearchRubrics tasks into database.
    
    Args:
        limit: Maximum number of tasks to load
        skip_if_no_ablation: If True, skip tasks without ablated prompts
    
    Returns:
        List of experiment UUIDs created
    """
    print("📥 Loading ResearchRubrics from HuggingFace...")
    tasks = load_researchrubrics_dataset()
    print(f"   Found {len(tasks)} tasks")
    
    print("📥 Loading ablated prompts...")
    ablations: AblatedPromptsFile | None = None
    try:
        ablations = load_ablated_prompts()
        print(f"   Found {len(ablations.prompts)} ablated prompts")
    except FileNotFoundError as e:
        if skip_if_no_ablation:
            raise
        print(f"   ⚠️ Warning: {e}")
        print("   Proceeding with original prompts (no ablation)")
    
    if limit:
        tasks = tasks[:limit]
    
    experiment_ids = []
    engine = get_engine()
    
    with Session(engine) as session:
        for task in tasks:
            # Find ablation for this task
            ablation = get_ablation_for_task(task.sample_id, ablations)
            
            if not ablation and skip_if_no_ablation:
                print(f"   ⚠️ Skipping {task.sample_id}: no ablated prompt")
                continue
            
            # Use ablated prompt if available, otherwise original
            task_description = ablation.ablated_prompt if ablation else task.original_prompt
            
            # Check if exists
            existing = session.exec(
                select(Experiment).where(
                    Experiment.benchmark_type == BenchmarkType.RESEARCHRUBRICS,
                    Experiment.task_id == task.sample_id,
                )
            ).first()
            
            if existing:
                experiment_ids.append(existing.id)
                continue
            
            # Create strongly typed benchmark data
            benchmark_data = create_benchmark_data(task, ablation)
            
            # Create experiment
            experiment = Experiment(
                benchmark_type=BenchmarkType.RESEARCHRUBRICS,
                task_id=task.sample_id,
                task_description=task_description,
                ground_truth_rubric={
                    "rules": build_llm_judge_rules(task.rubrics),
                },
                benchmark_specific_data=benchmark_data.model_dump(),
                category=task.domain,
            )
            session.add(experiment)
            session.flush()
            experiment_ids.append(experiment.id)
        
        session.commit()
    
    print(f"✅ Loaded {len(experiment_ids)} ResearchRubrics tasks to database")
    return experiment_ids
```

**CLI Command:**
```bash
# Requires HuggingFace authentication
export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxx
# OR run: huggingface-cli login

python -m h_arcane.cli seed --benchmark researchrubrics --limit 20
```

**Ablated Prompts File Format (`data/generated/researchrubrics/ablated_prompts.json`):**
```json
{
  "version": "1.0",
  "created_at": "2025-01-15T12:00:00Z",
  "prompts": [
    {
      "sample_id": "ai_ml_001",
      "ablated_prompt": "Write a report on transformer architectures.",
      "ablation_type": "preference_removal",
      "removed_elements": [
        "Preferred citation style",
        "Depth of technical detail",
        "Target audience specification"
      ]
    },
    {
      "sample_id": "ai_ml_002",
      "ablated_prompt": "Analyze the impact of large language models.",
      "ablation_type": "preference_removal",
      "removed_elements": [
        "Time period constraints",
        "Specific domains to focus on"
      ]
    }
  ]
}
```

---

### Unified Seeding CLI

**Implementation:**

```python
# h_arcane/cli.py (or scripts/seed_experiments.py)

import click
from h_arcane.db.models import BenchmarkType


@click.group()
def cli():
    """H-ARCANE CLI."""
    pass


@cli.command()
@click.option("--benchmark", type=click.Choice(["gdpeval", "minif2f", "researchrubrics", "all"]), required=True)
@click.option("--limit", type=int, default=None, help="Max tasks to load")
@click.option("--force", is_flag=True, help="Force reload even if exists")
def seed(benchmark: str, limit: int | None, force: bool):
    """Seed experiments from benchmark datasets."""
    
    if benchmark == "gdpeval" or benchmark == "all":
        from h_arcane.benchmarks.gdpeval.loader import load_gdpeval_to_database
        print("\n🔹 Seeding GDPEval...")
        ids = load_gdpeval_to_database(limit=limit)
        print(f"   Created {len(ids)} experiments")
    
    if benchmark == "minif2f" or benchmark == "all":
        from h_arcane.benchmarks.minif2f.loader import load_minif2f_to_database
        print("\n🔹 Seeding MiniF2F...")
        ids = load_minif2f_to_database(limit=limit)
        print(f"   Created {len(ids)} experiments")
    
    if benchmark == "researchrubrics" or benchmark == "all":
        from h_arcane.benchmarks.researchrubrics.loader import load_researchrubrics_to_database
        print("\n🔹 Seeding ResearchRubrics...")
        ids = load_researchrubrics_to_database(limit=limit)
        print(f"   Created {len(ids)} experiments")
    
    print("\n✅ Seeding complete!")


if __name__ == "__main__":
    cli()
```

**Usage Examples:**
```bash
# Seed all benchmarks
python -m h_arcane.cli seed --benchmark all

# Seed specific benchmark with limit
python -m h_arcane.cli seed --benchmark minif2f --limit 50

# Seed ResearchRubrics (requires HF auth)
HF_TOKEN=hf_xxx python -m h_arcane.cli seed --benchmark researchrubrics
```

---

### Settings Configuration Summary

```python
# h_arcane/settings.py

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://..."
    
    # OpenAI
    openai_api_key: str
    
    # Exa API (for ResearchRubrics web search)
    exa_api_key: str = ""
    
    # HuggingFace (for gated datasets like ScaleAI/researchrubrics)
    hf_token: str | None = None
    
    # Data paths
    data_dir: str = "./data"
    
    class Config:
        env_file = ".env"


settings = Settings()
```

**.env Example:**
```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/h_arcane
OPENAI_API_KEY=sk-...
EXA_API_KEY=...
HF_TOKEN=hf_...  # Optional, can use huggingface-cli login instead
```

---

### Data Directory Structure

```
arcane_extension/
├── data/
│   ├── raw/
│   │   ├── gdpeval.parquet              # GDPEval task descriptions
│   │   └── reference_files/             # GDPEval input files
│   │       └── {task_id}/
│   │           └── *.pdf, *.xlsx, etc.
│   ├── generated/
│   │   ├── staged_v2/
│   │   │   └── staged_rubrics.jsonl     # GDPEval rubrics
│   │   └── researchrubrics/
│   │       └── ablated_prompts.json     # Manually created ablations
│   └── cache/
│       └── miniF2F/                     # Cloned MiniF2F repo (auto)
```

---

### Verification Queries

After seeding, verify data with these queries:

```sql
-- Count experiments by benchmark
SELECT benchmark_type, COUNT(*) as count 
FROM experiments 
GROUP BY benchmark_type;

-- Check GDPEval has resources
SELECT e.task_id, COUNT(r.id) as resource_count
FROM experiments e
LEFT JOIN resources r ON r.experiment_id = e.id
WHERE e.benchmark_type = 'gdpeval'
GROUP BY e.task_id
LIMIT 10;

-- Check ResearchRubrics rubric structure
SELECT 
    task_id,
    benchmark_specific_data->>'domain' as domain,
    benchmark_specific_data->'rubric_summary'->>'total_criteria' as criteria_count
FROM experiments
WHERE benchmark_type = 'researchrubrics'
LIMIT 10;

-- Check MiniF2F problem metadata
SELECT 
    task_id,
    benchmark_specific_data->>'split' as split,
    benchmark_specific_data->>'competition' as competition
FROM experiments
WHERE benchmark_type = 'minif2f'
LIMIT 10;
```

## Next Steps

1. **Review this plan** and answer open questions
2. **Create detailed implementation tickets** for each phase
3. **Set up development branches** for each benchmark
4. **Begin Phase 1 refactoring** with GDPEval migration

