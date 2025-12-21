# Benchmark-First Architecture Plan

## Overview

Reorganize `h_arcane/` around the principle that **benchmarks are the primary axis of variation**. Core infrastructure is generic and stable; benchmark-specific code lives together in self-contained packages.

## Current Status (Post Plan 9)

**✅ COMPLETED - Skills Architecture:**
- Skills created with Pydantic responses
- `SandboxManager.run_skill()` with typed Pydantic return values
- Toolkits use closures (capturing `self.run_id`)
- Old `tools/`, `agents/tools.py`, `agents/sandbox_executor.py` deleted

**⚠️ NEEDS MOVE - Skills currently at wrong location:**
- Currently: `h_arcane/skills/gdpeval/` and `h_arcane/skills/minif2f/`
- Should be: `h_arcane/benchmarks/gdpeval/skills/` and `h_arcane/benchmarks/minif2f/skills/`
- Reason: Everything benchmark-specific should be in one place

**🔲 REMAINING - Core Restructure:**
- Move skills under their benchmarks
- Create `h_arcane/core/` folder structure
- Move generic infrastructure to core
- Move `StagedRubric` to GDPEval (it's benchmark-specific)
- Remove `AnyRule` from core (benchmark-specific rule unions)
- Move `proof_verification.py` to `benchmarks/minif2f/rules/`
- Create `BaseRubric` protocol in core

## Guiding Principles

1. **Core never imports benchmarks** - dependency arrow is strictly one-way
2. **Benchmarks are self-contained** - everything MiniF2F needs is in `benchmarks/minif2f/`
3. **Core defines protocols, benchmarks implement them** - clear interface boundaries
4. **Skills live under their benchmark** - `benchmarks/{name}/skills/` (🔲 TODO: move)
5. **Adding a benchmark = adding one folder** - no touching 10 directories

---

## Complete Directory Structure

```
h_arcane/
│
├── __init__.py
├── settings.py                              # Global settings (env vars)
│
├── core/                                    # ═══════════════════════════════
│   │                                        # 🔲 TODO - GENERIC INFRASTRUCTURE
│   │                                        # Zero benchmark imports allowed
│   │                                        # ═══════════════════════════════
│   │
│   ├── __init__.py
│   │
│   ├── db/                                  # Database layer
│   │   ├── __init__.py
│   │   ├── connection.py                    # Engine, session factory
│   │   ├── models.py                        # SQLAlchemy models (or split into files)
│   │   └── queries.py                       # Query helpers
│   │
│   ├── infrastructure/                      # External service clients
│   │   ├── __init__.py
│   │   ├── sandbox.py                       # SandboxManager (already has run_skill!)
│   │   ├── llm.py                           # OpenAI/LiteLLM client
│   │   └── inngest_client.py                # Inngest client singleton
│   │
│   ├── models/                              # Domain models (Pydantic schemas)
│   │   ├── __init__.py
│   │   ├── experiment.py                    # Experiment, ExperimentRun, WorkerConfig
│   │   ├── resource.py                      # Resource
│   │   ├── action.py                        # Action  
│   │   ├── evaluation.py                    # CriterionResult, Evaluation
│   │   └── enums.py                         # BenchmarkName, Status enums
│   │
│   ├── evaluation/                          # Base evaluation infrastructure
│   │   ├── __init__.py
│   │   ├── base.py                          # BaseRubric interface
│   │   ├── data.py                          # EvaluationData (pure data container)
│   │   ├── runner.py                        # EvaluationRunner (infra + Inngest steps)
│   │   └── rules/                           # GENERIC rules only (no ProofVerification!)
│   │       ├── __init__.py
│   │       ├── base.py                      # BaseRule ABC
│   │       ├── code_rule.py                 # Execute Python code in sandbox
│   │       └── llm_judge.py                 # LLM-based evaluation
│   │
│   ├── agents/                              # Base agent infrastructure
│   │   ├── __init__.py
│   │   ├── base.py                          # BaseToolkit, BaseStakeholder interfaces
│   │   ├── worker.py                        # ReActWorker
│   │   └── tracing.py                       # Action logging utilities
│   │
│   ├── orchestration/                       # Inngest function handlers
│   │   ├── __init__.py
│   │   ├── events.py                        # Inngest event schemas
│   │   ├── handlers.py                      # register_inngest_handlers()
│   │   ├── worker_execute.py                # Worker execution handler
│   │   ├── criterion_evaluate.py            # Criterion evaluation handler
│   │   ├── task_evaluator.py                # Task evaluation orchestration
│   │   ├── run_evaluate.py                  # Run evaluation handler
│   │   ├── run_cleanup.py                   # Cleanup handler
│   │   └── experiment_runner.py             # ExperimentRunner class
│   │
│   ├── config/                              # Configuration
│   │   ├── __init__.py
│   │   └── evaluation_config.py             # LLM eval settings, etc.
│   │
│   └── schemas/                             # Base Pydantic models
│       ├── __init__.py
│       └── base.py                          # ToolResponse, SkillResponse base classes
│
├── benchmarks/                              # ═══════════════════════════════
│   │                                        # BENCHMARK IMPLEMENTATIONS
│   │                                        # Config, loaders, toolkits, rules
│   │                                        # ═══════════════════════════════
│   │
│   ├── __init__.py
│   ├── registry.py                          # Benchmark lookup (✅ exists)
│   │                                        # NOTE: base.py moves to core/agents/base.py
│   │
│   ├── gdpeval/                             # ───────────────────────────────
│   │   │                                    # GDP-Eval Benchmark
│   │   │                                    # EVERYTHING GDPEval in ONE place
│   │   │                                    # ───────────────────────────────
│   │   │
│   │   ├── __init__.py
│   │   ├── config.py                        # GDPEVAL_WORKER_CONFIG (✅ exists)
│   │   ├── loader.py                        # load_gdpeval_to_database() (✅ exists)
│   │   ├── stakeholder.py                   # RubricStakeholder (✅ exists)
│   │   ├── toolkit.py                       # GDPEvalToolkit (✅ refactored)
│   │   ├── schemas.py                       # GDPEvalTask (✅ exists)
│   │   ├── rubric.py                        # 🔲 TODO: Move StagedRubric here
│   │   │
│   │   ├── skills/                          # ⚠️ TODO: Move from h_arcane/skills/gdpeval/
│   │   │   ├── __init__.py
│   │   │   ├── responses.py                 # Pydantic response models
│   │   │   ├── read_pdf.py                  # async def main(**kwargs) -> Response
│   │   │   ├── read_csv.py
│   │   │   ├── read_excel.py
│   │   │   ├── create_docx.py
│   │   │   ├── create_excel.py
│   │   │   ├── create_csv.py
│   │   │   ├── ocr_image.py
│   │   │   └── run_python.py
│   │   │
│   │   └── rules/                           # 🔲 TODO: GDPEval rule union
│   │       └── __init__.py                  # GDPEvalRule = CodeRule | LLMJudgeRule
│   │
│   ├── minif2f/                             # ───────────────────────────────
│   │   │                                    # MiniF2F Benchmark
│   │   │                                    # EVERYTHING MiniF2F in ONE place
│   │   │                                    # ───────────────────────────────
│   │   │
│   │   ├── __init__.py
│   │   ├── config.py                        # MINIF2F_WORKER_CONFIG (✅ exists)
│   │   ├── loader.py                        # load_minif2f_to_database() (✅ exists)
│   │   ├── schemas.py                       # MiniF2FProblem (✅ exists)
│   │   ├── stakeholder.py                   # MiniF2FStakeholder (✅ exists)
│   │   ├── toolkit.py                       # MiniF2FToolkit (✅ refactored)
│   │   │
│   │   ├── skills/                          # ⚠️ TODO: Move from h_arcane/skills/minif2f/
│   │   │   ├── __init__.py
│   │   │   ├── responses.py                 # Pydantic response models
│   │   │   ├── _utils.py                    # Lean helpers
│   │   │   ├── write_lean_file.py
│   │   │   ├── check_lean_file.py
│   │   │   └── verify_lean_proof.py
│   │   │
│   │   └── rules/                           # 🔲 TODO: Move ProofVerificationRule here
│   │       ├── __init__.py
│   │       └── proof_verification.py        # Move from evaluation/rules/
│   │
│   └── research_rubrics/                    # (Future)
│       ├── skills/
│       ├── rules/
│       └── ...
│
├── api/                                     # ═══════════════════════════════
│   │                                        # HTTP API (FastAPI)
│   │                                        # ═══════════════════════════════
│   │
│   ├── __init__.py
│   └── main.py                              # FastAPI app, Inngest serve endpoint
│
└── notebooks/                               # ═══════════════════════════════
    │                                        # EXPLORATORY NOTEBOOKS
    │                                        # (Not part of core, can delete)
    │                                        # ═══════════════════════════════
    │
    └── explore_researchrubrics.ipynb

# NOTE: CLI scripts stay in arcane_extension/scripts/ (outside h_arcane/)
# NOT moved into h_arcane/cli/ as previously planned
```

---

## What Lives Where

### `core/` - Generic Infrastructure

**Rule: ZERO imports from `benchmarks/`**

| Directory | Contains | Examples |
|-----------|----------|----------|
| `infrastructure/` | External service wrappers | SandboxManager, Postgres client, OpenAI client |
| `models/` | Domain models (Pydantic + SQLAlchemy) | Experiment, Resource, Action, CriterionResult |
| `evaluation/` | Base evaluation logic | EvaluationRunner, BaseRule, CodeRule, LLMJudgeRule, **BaseRubric** |
| `agents/` | Base agent classes | ReActWorker, **BaseToolkit**, **BaseStakeholder** |
| `orchestration/` | Inngest handlers + experiment runner | worker_execute, criterion_evaluate, ExperimentRunner |
| `skills/` | Shared base types for VM skills | ToolResponse base class |

**Important: No `AnyRule` union in core!** Each benchmark defines its own rule union if needed.

**Key files in `core/`:**

```python
# core/agents/base.py
"""Base interfaces for agent-related components."""
from typing import Protocol
from agents import Tool


class BaseToolkit(Protocol):
    """Protocol all benchmark toolkits must implement."""
    
    def get_tools(self) -> list[Tool]: ...
    
    @property
    def questions_asked(self) -> int: ...


class BaseStakeholder(Protocol):
    """Protocol all benchmark stakeholders must implement."""
    
    async def answer(self, question: str) -> str: ...
```

```python
# core/evaluation/rules/base.py
from abc import ABC, abstractmethod
from pydantic import BaseModel

class BaseRule(BaseModel, ABC):
    """Base class for all evaluation rules."""
    name: str
    description: str
    weight: float = 1.0
    
    @abstractmethod
    async def evaluate(self, runner: "EvaluationRunner") -> "CriterionResult":
        """Each rule evaluates itself using the provided runner."""
        ...
```

```python
# core/infrastructure/sandbox.py
from pathlib import Path
from uuid import UUID

class SandboxManager:
    """Manages E2B sandboxes with benchmark-specific skills."""
    
    async def create(
        self,
        run_id: UUID,
        skills_dir: Path,  # Benchmark passes its skills directory
    ) -> Sandbox:
        """Create sandbox and copy skills to VM."""
        ...
    
    async def run_skill(
        self,
        run_id: UUID,
        skill_name: str,
        **kwargs,
    ) -> dict:
        """Execute a skill in the sandbox."""
        ...
```

```python
# core/evaluation/base.py
"""Base interfaces for evaluation components."""
from typing import Protocol

from h_arcane.core.evaluation.data import EvaluationData
from h_arcane.core.models.evaluation import CriterionResult, Evaluation


class BaseRubric(Protocol):
    """
    Protocol that benchmark rubrics must implement.
    
    Core defines WHAT goes in and WHAT comes out.
    Benchmarks define their own internal structure.
    
    GDPEval: Complex staged rubric with gates, thresholds
    MiniF2F: Simple binary (proof verified or not)
    """
    
    def get_rules(self) -> list["BaseRule"]:
        """Return list of rules to evaluate."""
        ...
    
    def compute_final_score(
        self,
        criterion_results: list[CriterionResult],
    ) -> Evaluation:
        """
        Given criterion results, compute the final evaluation.
        
        Each benchmark implements its own scoring logic:
        - GDPEval: Stage-based scoring with gates
        - MiniF2F: Binary pass/fail based on proof verification
        """
        ...
```

Note: `EvaluationData` is the strongly-typed context passed to rules during evaluation.

---

### `benchmarks/` - Benchmark Implementations

**Rule: Each benchmark is a self-contained package**

| Component | Purpose | Location |
|-----------|---------|----------|
| `config.py` | Worker system prompt, model params | `benchmarks/{name}/config.py` |
| `loader.py` | Load data into database | `benchmarks/{name}/loader.py` |
| `stakeholder.py` | Benchmark-specific stakeholder | `benchmarks/{name}/stakeholder.py` |
| `toolkit.py` | Tool wrapper that calls skills | `benchmarks/{name}/toolkit.py` |
| `skills/` | Code that runs IN the VM | `benchmarks/{name}/skills/` |
| `rules/` | Benchmark-specific evaluation rules | `benchmarks/{name}/rules/` |

**Key file - `benchmarks/registry.py`:**

```python
"""Benchmark registry - single source of truth for benchmark lookup."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import UUID

from h_arcane.core.models.enums import BenchmarkName
from h_arcane.core.models.experiment import WorkerConfig
from h_arcane.core.agents.protocols import BaseToolkit, BaseStakeholder


@dataclass
class BenchmarkSpec:
    """Complete specification for a benchmark."""
    name: BenchmarkName
    worker_config: WorkerConfig
    toolkit_class: type[BaseToolkit]
    stakeholder_class: type[BaseStakeholder]
    loader: Callable[[int | None], list[UUID]]
    skills_dir: Path  # Path to skills/ folder for VM copying


# Import benchmark implementations
from h_arcane.benchmarks.gdpeval import (
    GDPEVAL_WORKER_CONFIG,
    GDPEvalToolkit,
    RubricStakeholder,
    load_gdpeval_to_database,
)
from h_arcane.benchmarks.minif2f import (
    MINIF2F_WORKER_CONFIG,
    MiniF2FToolkit,
    MiniF2FStakeholder,
    load_minif2f_to_database,
)


BENCHMARKS: dict[BenchmarkName, BenchmarkSpec] = {
    BenchmarkName.GDPEVAL: BenchmarkSpec(
        name=BenchmarkName.GDPEVAL,
        worker_config=GDPEVAL_WORKER_CONFIG,
        toolkit_class=GDPEvalToolkit,
        stakeholder_class=RubricStakeholder,
        loader=load_gdpeval_to_database,
        skills_dir=Path(__file__).parent / "gdpeval" / "skills",
    ),
    BenchmarkName.MINIF2F: BenchmarkSpec(
        name=BenchmarkName.MINIF2F,
        worker_config=MINIF2F_WORKER_CONFIG,
        toolkit_class=MiniF2FToolkit,
        stakeholder_class=MiniF2FStakeholder,
        loader=load_minif2f_to_database,
        skills_dir=Path(__file__).parent / "minif2f" / "skills",
    ),
}


def get_benchmark(name: BenchmarkName) -> BenchmarkSpec:
    """Get benchmark specification by name."""
    if name not in BENCHMARKS:
        raise ValueError(f"Unknown benchmark: {name}. Available: {list(BENCHMARKS.keys())}")
    return BENCHMARKS[name]
```

---

### Skills Structure (VM Code)

Each benchmark's `skills/` folder is copied to the VM at sandbox creation.

**VM filesystem after setup:**
```
/skills/
├── _core/                    # Always copied (from core/skills/)
│   ├── __init__.py
│   └── base.py               # ToolResponse
│
└── {benchmark}/              # e.g., "gdpeval" or "minif2f"
    ├── __init__.py
    ├── responses.py
    └── *.py                  # Individual skill files
```

**Skill file convention:**

```python
# benchmarks/minif2f/skills/write_lean_file.py
"""Write Lean file skill - runs IN the VM."""
from pathlib import Path
from .responses import WriteLeanResponse


async def main(filename: str, content: str) -> dict:
    """
    Write or update a Lean proof file.
    
    Args:
        filename: Name of file (e.g., "proof.lean")
        content: Lean code content
    
    Returns:
        {"success": True, "filename": "...", "bytes_written": N}
    """
    try:
        filepath = Path("/workspace") / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        content_bytes = content.encode("utf-8")
        filepath.write_bytes(content_bytes)
        
        return WriteLeanResponse(
            success=True,
            filename=str(filepath),
            bytes_written=len(content_bytes),
        ).to_dict()
        
    except Exception as e:
        return WriteLeanResponse(success=False, error=str(e)).to_dict()
```

**Response types:**

```python
# benchmarks/minif2f/skills/responses.py
"""Response types for MiniF2F skills."""
from dataclasses import dataclass, asdict
from typing import Any

# Import base from _core (works in VM because we copy it)
from _core.base import ToolResponse


@dataclass
class WriteLeanResponse(ToolResponse):
    filename: str | None = None
    bytes_written: int | None = None


@dataclass
class LeanCheckResponse(ToolResponse):
    has_errors: bool | None = None
    errors: list[str] | None = None
    goals: list[str] | None = None
    warnings: list[str] | None = None


@dataclass
class LeanVerificationResponse(ToolResponse):
    verified: bool = False
    message: str | None = None
    proof_complete: bool = False
```

---

## Toolkit Implementation Pattern (✅ Implemented)

Toolkits use **closures** to capture `run_id` and `sandbox_manager`. Each tool wrapper calls `run_skill()` with typed Pydantic responses.

```python
# benchmarks/minif2f/toolkit.py (ACTUAL IMPLEMENTATION)
"""MiniF2F toolkit - explicit tool wrappers for Lean proof development."""
from uuid import UUID
from agents import function_tool, Tool

from h_arcane.agents.sandbox import SandboxManager
from h_arcane.benchmarks.base import BaseToolkit, BaseStakeholder

# Import response types from the skills package (same types used in VM!)
from h_arcane.skills.minif2f.responses import (
    WriteLeanResponse,
    LeanCheckResponse,
    LeanVerificationResponse,
)


class MiniF2FToolkit(BaseToolkit):
    """MiniF2F benchmark toolkit with Lean tools."""

    def __init__(
        self,
        run_id: UUID,
        stakeholder: BaseStakeholder,
        sandbox_manager: SandboxManager,
        max_questions: int = 10,
    ):
        self.run_id = run_id
        self.stakeholder = stakeholder
        self.sandbox_manager = sandbox_manager
        self.max_questions = max_questions
        self._questions_asked = 0

    def get_tools(self) -> list[Tool]:
        """Return all MiniF2F tools."""
        return [
            self._write_lean_file(),
            self._check_lean_file(),
            self._verify_lean_proof(),
            self._ask_stakeholder(),
        ]

    # ─────────────────────────────────────────────────────────────────
    # Tool wrappers - closures capture self.run_id and self.sandbox_manager
    # ─────────────────────────────────────────────────────────────────

    def _write_lean_file(self) -> Tool:
        @function_tool
        async def write_lean_file(filename: str, content: str) -> WriteLeanResponse:
            """Write or update a Lean proof file."""
            # Closure captures self.run_id - no global state!
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "write_lean_file",
                WriteLeanResponse,  # Pydantic type for validation
                filename=filename,
                content=content,
            )
            return result
        return write_lean_file

    def _check_lean_file(self) -> Tool:
        @function_tool
        async def check_lean_file(filename: str) -> LeanCheckResponse:
            """Check a Lean file for errors and get proof goals."""
            result = await self.sandbox_manager.run_skill(
                self.run_id,
                "check_lean_file",
                LeanCheckResponse,
                filename=filename,
            )
            return result
        return check_lean_file
    
    # ... similar for verify_lean_proof and ask_stakeholder
```

**Key points:**
1. **Closures capture `self.run_id`** - no global state needed
2. **`run_skill()` takes Pydantic type** - validates VM response into typed model
3. **Response types shared** - `h_arcane.skills.minif2f.responses` used in both VM and toolkit
4. **Tools return Pydantic models** - agent sees structured responses

---

## How Closures Eliminate Global State (✅ Implemented)

The old approach used **global state** which was problematic:

```python
# OLD APPROACH (BAD) - agents/sandbox_executor.py (DELETED)
_current_run_id: UUID | None = None  # 🚨 GLOBAL STATE

def set_sandbox_manager(sandbox_manager: SandboxManager, run_id: UUID) -> None:
    global _current_run_id
    _current_run_id = run_id  # Set before tools are called
```

**Problems:** Not parallelizable, hidden coupling, hard to test.

### Current Solution: Closures

Each toolkit creates tool wrappers that **close over** `self.run_id` and `self.sandbox_manager`:

```python
class MiniF2FToolkit:
    def __init__(self, run_id: UUID, sandbox_manager: SandboxManager, ...):
        self.run_id = run_id  # Stored on instance
        self.sandbox_manager = sandbox_manager
    
    def _write_lean_file(self) -> Tool:
        @function_tool
        async def write_lean_file(filename: str, content: str) -> WriteLeanResponse:
            # ✅ Closure captures self.run_id - no global state!
            result = await self.sandbox_manager.run_skill(
                self.run_id,  # ← From enclosing scope
                "write_lean_file",
                WriteLeanResponse,
                filename=filename,
                content=content,
            )
            return result
        return write_lean_file
```

**Benefits:**
- ✅ Each toolkit instance has its own `run_id`
- ✅ No global state - fully parallelizable  
- ✅ Explicit data flow
- ✅ Easy to test (just create toolkit with mock sandbox)

### Future: `RunContextWrapper` (Optional Enhancement)

The OpenAI Agents SDK provides `RunContextWrapper` for dependency injection.
This could be adopted later to define tools once at module level instead of per-instance.
See SDK docs: https://openai.github.io/openai-agents-python/context/

---

## Orchestration Layer

The orchestration layer in `core/` is benchmark-agnostic. It uses the registry to get benchmark-specific components.

```python
# core/orchestration/worker_execute.py
"""Worker execution Inngest handler."""
import inngest
from uuid import UUID

from h_arcane.core.infrastructure.sandbox import SandboxManager
from h_arcane.core.agents.worker import ReActWorker
from h_arcane.core.models.enums import BenchmarkName
from h_arcane.benchmarks.registry import get_benchmark


async def worker_execute_handler(
    ctx: inngest.Context,
    run_id: UUID,
    benchmark_name: BenchmarkName,
    task_input: str,
    # ... other params
):
    """Execute worker for any benchmark."""
    
    # Get benchmark specification
    benchmark = get_benchmark(benchmark_name)
    
    # Create sandbox with benchmark's skills
    sandbox_manager = SandboxManager()
    await sandbox_manager.create(run_id, benchmark.skills_dir)
    
    # Create benchmark-specific stakeholder
    stakeholder = benchmark.stakeholder_class(...)
    
    # Create benchmark-specific toolkit
    toolkit = benchmark.toolkit_class(
        run_id=run_id,
        sandbox_manager=sandbox_manager,
        stakeholder=stakeholder,
    )
    
    # Create worker with benchmark config
    worker = ReActWorker(
        config=benchmark.worker_config,
        toolkit=toolkit,
    )
    
    # Execute
    result = await worker.execute(task_input)
    
    return result
```

---

## Benchmark-Specific Rules

Rules that are only relevant to one benchmark live with that benchmark.

```python
# benchmarks/minif2f/rules/proof_verification.py
"""Proof verification rule - MiniF2F specific."""
from pydantic import Field

from h_arcane.core.evaluation.rules.base import BaseRule
from h_arcane.core.evaluation.runner import EvaluationRunner
from h_arcane.core.models.evaluation import CriterionResult


class ProofVerificationRule(BaseRule):
    """Verifies a Lean proof compiles without errors or sorry."""
    
    rule_type: str = Field(default="proof_verification", frozen=True)
    problem_statement: str = Field(description="The Lean theorem statement to prove")
    
    async def evaluate(self, runner: EvaluationRunner) -> CriterionResult:
        """Verify Lean proof with granular Inngest steps."""
        data = runner.data
        
        # Step 1: Ensure sandbox exists
        await runner.step("ensure-sandbox", runner.ensure_sandbox)
        
        # Step 2: Ensure Lean is installed
        async def ensure_lean():
            # ... Lean installation logic ...
            pass
        
        await runner.step("ensure-lean", ensure_lean)
        
        # Step 3: Extract proof from agent output
        async def extract_proof():
            lean_files = [r for r in data.agent_outputs if r.name.endswith(".lean")]
            if not lean_files:
                raise ValueError("No Lean proof found in agent outputs")
            return {"proof_code": lean_files[0].load_text()}
        
        proof_data = await runner.step("extract-proof", extract_proof)
        
        # Step 4: Verify proof
        async def verify_proof():
            # ... verification logic ...
            pass
        
        verify_result = await runner.step("verify-proof", verify_proof)
        
        # Return result
        return CriterionResult(...)
```

**Benchmark-specific rule unions (NOT in core):**

```python
# benchmarks/minif2f/rules/__init__.py
"""MiniF2F-specific evaluation rules."""
from .proof_verification import ProofVerificationRule

# MiniF2F defines its OWN rule union - not exported to core
# This is only used within MiniF2F benchmark code
from typing import Annotated, Union
from pydantic import Field

from h_arcane.core.evaluation.rules import CodeRule, LLMJudgeRule

MiniF2FRule = Annotated[
    Union[CodeRule, LLMJudgeRule, ProofVerificationRule],
    Field(discriminator="rule_type"),
]

__all__ = ["ProofVerificationRule", "MiniF2FRule"]
```

```python
# benchmarks/gdpeval/rules/__init__.py
"""GDPEval rule union."""
from typing import Annotated, Union
from pydantic import Field

from h_arcane.core.evaluation.rules import CodeRule, LLMJudgeRule

# GDPEval only uses core rules, but defines its own union for type safety
GDPEvalRule = Annotated[
    Union[CodeRule, LLMJudgeRule],
    Field(discriminator="rule_type"),
]

__all__ = ["GDPEvalRule"]
```

**Key insight:** There is NO `AnyRule` in core. Each benchmark defines what rules it uses.
This prevents core from importing benchmark-specific code.

---

## Import Rules

### From `core/` (allowed anywhere in core):
```python
from h_arcane.core.infrastructure.sandbox import SandboxManager
from h_arcane.core.models.experiment import Experiment
from h_arcane.core.evaluation.rules.base import BaseRule
from h_arcane.core.agents.protocols import BaseToolkit
```

### From `benchmarks/` (only in benchmarks or entry points):
```python
# In benchmarks/minif2f/toolkit.py - OK
from h_arcane.core.infrastructure.sandbox import SandboxManager

# In core/orchestration/worker_execute.py - OK (uses registry)
from h_arcane.benchmarks.registry import get_benchmark

# In core/evaluation/rules/base.py - FORBIDDEN
from h_arcane.benchmarks.minif2f.rules import ProofVerificationRule  # NO!
```

### Cross-benchmark imports (FORBIDDEN):
```python
# In benchmarks/minif2f/toolkit.py - FORBIDDEN
from h_arcane.benchmarks.gdpeval.toolkit import GDPEvalToolkit  # NO!
```

---

## Migration Plan (Updated Post-Plan 9)

### ✅ COMPLETED - Skills Architecture (Plan 9)
- Created skills with Pydantic responses
- Refactored `SandboxManager.run_skill()` with typed returns
- Refactored toolkits to use closures + `run_skill()`
- Deleted old `tools/`, `agents/tools.py`, `agents/sandbox_executor.py`

### Phase 1: Move skills under benchmarks (🔲 TODO - Quick win)
1. Move `h_arcane/skills/gdpeval/` → `h_arcane/benchmarks/gdpeval/skills/`
2. Move `h_arcane/skills/minif2f/` → `h_arcane/benchmarks/minif2f/skills/`
3. Delete empty `h_arcane/skills/` directory
4. Update `benchmarks/registry.py` skills_dir paths
5. Update toolkit imports (if any reference skills directly)

### Phase 2: Create `core/` structure (🔲 TODO)
1. Create `h_arcane/core/` directory structure
2. Move database: `db/*` → `core/db/*`
3. Move infrastructure:
   - `agents/sandbox.py` → `core/infrastructure/sandbox.py`
   - `inngest/client.py` → `core/infrastructure/inngest_client.py`
4. Move config:
   - `config/evaluation_config.py` → `core/config/evaluation_config.py`
   - `experiments/config.py` → `core/config/experiment_config.py`
5. Move models: `schemas/base.py` → `core/models/enums.py`
6. Move evaluation base: 
   - `evaluation/context.py` → `core/evaluation/data.py` + `runner.py`
   - `evaluation/rules/base.py`, `code_rule.py`, `llm_judge.py` → `core/evaluation/rules/`
   - **NOT** `proof_verification.py` (benchmark-specific)
7. Move agent base:
   - `agents/worker.py` → `core/agents/worker.py`
   - `agents/tracing.py` → `core/agents/tracing.py`
   - `benchmarks/base.py` → `core/agents/base.py` (protocols/ABCs)
8. Move orchestration:
   - `inngest/functions/*.py` → `core/orchestration/*.py`
   - `inngest/events.py` → `core/orchestration/events.py`
   - `experiments/runner.py` → `core/orchestration/experiment_runner.py`

### Phase 3: Move benchmark-specific code (🔲 TODO)
1. **Remove `AnyRule` from core** - delete from `evaluation/rules/__init__.py`
2. **Move `proof_verification.py`**: `evaluation/rules/` → `benchmarks/minif2f/rules/`
3. **Move `StagedRubric` + `rubric_flattener.py`**: → `benchmarks/gdpeval/rubric.py`
   - Merge `flatten_rubric()` function into the same file
   - `EvaluationStage` also moves here (GDPEval-specific)
4. **Create `BaseRubric`** in `core/evaluation/base.py`
5. **Create benchmark rule unions**:
   - `benchmarks/gdpeval/rules/__init__.py`: `GDPEvalRule = CodeRule | LLMJudgeRule`
   - `benchmarks/minif2f/rules/__init__.py`: `MiniF2FRule = CodeRule | LLMJudgeRule | ProofVerificationRule`

### Phase 4: Update imports + cleanup (🔲 TODO)
1. Update all imports to use `h_arcane.core.*` paths
2. Update `benchmarks/registry.py` to use new paths
3. Update orchestration to use registry for benchmark-specific code
4. Delete old `h_arcane/evaluation/schemas.py` (after moving StagedRubric)
5. Delete old `h_arcane/schemas/` directory (after migrating to core/models)
6. Delete `h_arcane/agents/stakeholder.py` (duplicate of gdpeval stakeholder)

### Phase 5: Verification (🔲 TODO)
1. Run GDPEval end-to-end
2. Run MiniF2F end-to-end
3. Verify skills are correctly copied to VMs
4. Verify evaluation rules work for both benchmarks
5. Run pyright - ensure no type errors

---

## File-by-File Migration Map (Updated)

### ⚠️ Phase 1: Move skills under benchmarks
| Current Location | Target Location |
|------------------|-----------------|
| `h_arcane/skills/gdpeval/*` | `h_arcane/benchmarks/gdpeval/skills/*` |
| `h_arcane/skills/minif2f/*` | `h_arcane/benchmarks/minif2f/skills/*` |
| `h_arcane/skills/` | DELETE (empty after move) |

### 🔲 Remaining Moves (Phase 2-4)
| Current Location | New Location |
|------------------|--------------|
| `h_arcane/schemas/base.py` | `h_arcane/core/models/enums.py` |
| `h_arcane/db/*` | `h_arcane/core/db/*` |
| `h_arcane/experiments/config.py` | `h_arcane/core/config/experiment_config.py` |
| `h_arcane/experiments/runner.py` | `h_arcane/core/orchestration/experiment_runner.py` |
| `h_arcane/experiments/loader.py` | DELETE (legacy duplicate of `benchmarks/gdpeval/loader.py`) |
| `h_arcane/evaluation/context.py` | `h_arcane/core/evaluation/data.py` + `runner.py` |
| `h_arcane/evaluation/rules/base.py` | `h_arcane/core/evaluation/rules/base.py` |
| `h_arcane/evaluation/rules/code_rule.py` | `h_arcane/core/evaluation/rules/code_rule.py` |
| `h_arcane/evaluation/rules/llm_judge.py` | `h_arcane/core/evaluation/rules/llm_judge.py` |
| `h_arcane/evaluation/rules/proof_verification.py` | `h_arcane/benchmarks/minif2f/rules/proof_verification.py` |
| `h_arcane/evaluation/schemas.py` (StagedRubric part) | `h_arcane/benchmarks/gdpeval/rubric.py` |
| `h_arcane/agents/worker.py` | `h_arcane/core/agents/worker.py` |
| `h_arcane/agents/sandbox.py` | `h_arcane/core/infrastructure/sandbox.py` |
| `h_arcane/agents/stakeholder.py` | DELETE (duplicate of gdpeval stakeholder) |
| `h_arcane/inngest/functions/*.py` | `h_arcane/core/orchestration/*.py` |
| `h_arcane/inngest/client.py` | `h_arcane/core/infrastructure/inngest_client.py` |
| `h_arcane/inngest/events.py` | `h_arcane/core/orchestration/events.py` |
| `h_arcane/agents/tracing.py` | `h_arcane/core/agents/tracing.py` |
| `h_arcane/config/evaluation_config.py` | `h_arcane/core/config/evaluation_config.py` |
| `h_arcane/evaluation/rubric_flattener.py` | `h_arcane/benchmarks/gdpeval/rubric.py` (merge with StagedRubric) |
| `h_arcane/benchmarks/base.py` | `h_arcane/core/agents/base.py` (protocols move to core) |

### Files to DELETE after migration
- `h_arcane/evaluation/rules/__init__.py` → Remove AnyRule, recreate minimal
- `h_arcane/evaluation/schemas.py` → After moving StagedRubric to gdpeval
- `h_arcane/evaluation/rubric_flattener.py` → Merged into `benchmarks/gdpeval/rubric.py`
- `h_arcane/agents/stakeholder.py` → Duplicate of `benchmarks/gdpeval/stakeholder.py`
- `h_arcane/schemas/` directory → After moving to `core/models/`
- `h_arcane/experiments/loader.py` → Legacy duplicate of `benchmarks/gdpeval/loader.py`
- `h_arcane/experiments/` directory → After moving config/runner to core
- `h_arcane/config/` directory → After moving to `core/config/`
- `h_arcane/inngest/` directory → After moving to `core/orchestration/` and `core/infrastructure/`
- `h_arcane/benchmarks/base.py` → After moving protocols to `core/agents/base.py`

---

## Adding a New Benchmark Checklist

1. **Create benchmark directory**: `h_arcane/benchmarks/{name}/`
2. **Create `__init__.py`** with exports
3. **Create `config.py`** with `{NAME}_WORKER_CONFIG`
4. **Create `loader.py`** with `load_{name}_to_database()`
5. **Create `stakeholder.py`** with `{Name}Stakeholder`
6. **Create `toolkit.py`** with `{Name}Toolkit` (closures over `run_id`)
7. **Create `skills/` subdirectory** with:
   - `__init__.py`
   - `responses.py` (Pydantic models)
   - Individual skill files with `async def main(**kwargs) -> ResponseModel`
8. **Create `rules/` subdirectory** (if benchmark needs custom evaluation rules)
   - `__init__.py` with rule union type
   - Custom rule classes
9. **Register in `benchmarks/registry.py`**:
   - Add to `BENCHMARKS` dict
   - Set `skills_dir = Path(__file__).parent / "{name}" / "skills"`
10. **Add to `BenchmarkName` enum** in `core/models/enums.py`

**Result**: Everything for `{name}` is in `h_arcane/benchmarks/{name}/`

---

## Benefits of This Structure

1. **"What is MiniF2F?"** → Look in `benchmarks/minif2f/`, EVERYTHING is there:
   - `config.py` - worker config
   - `toolkit.py` - tools
   - `skills/` - VM code
   - `rules/` - evaluation rules
   - `stakeholder.py`, `loader.py`, etc.
2. **"How do I add a benchmark?"** → Copy a benchmark folder, modify, register
3. **"What's shared infrastructure?"** → Everything in `core/`
4. **"Will this change break GDPEval?"** → Changes to `benchmarks/minif2f/` won't affect it
5. **Clear ownership** → MiniF2F team owns `benchmarks/minif2f/`, core team owns `core/`
6. **Testable in isolation** → Can test benchmark skills without full infrastructure
7. **No scattered files** → All MiniF2F code in ONE directory, not 6+

