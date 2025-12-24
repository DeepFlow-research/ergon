# Plan 11: Generic Orchestration Layer

## Problem Statement

The core orchestration layer (`core/orchestration/`) is tightly coupled to benchmark-specific implementations. Every new benchmark requires modifying core files.

### Current Coupling Issues

| File | Issue |
|------|-------|
| `worker_execute.py` | 30-line if/else block creating benchmark-specific stakeholders/toolkits |
| `worker_execute.py` | Direct imports from `benchmarks/gdpeval/*` and `benchmarks/minif2f/*` |
| `task_evaluator.py` | Hardcoded to GDPEval's `StagedRubric` structure |
| `task_evaluator.py` | Uses GDPEval's `flatten_rubric()`, `EvaluationStage`, staged scoring logic |
| `run_evaluate.py` | Imports and uses `StagedRubric` directly |
| `events.py` | Uses GDPEval's `EvaluationStage` type |
| `events.py` | Explicit rule union: `CodeRule | LLMJudgeRule | ProofVerificationRule` |

### Consequence

Adding a new benchmark requires:
1. Modifying `worker_execute.py` to add if/else branch
2. Ensuring new benchmark uses GDPEval's `StagedRubric` model (or modifying `task_evaluator.py`)
3. Adding new rule types to `events.py` union

This violates Open/Closed Principle - core should be open for extension but closed for modification.

---

## Goal

Transform core orchestration from "knows about every benchmark" to "calls benchmark-provided components through registry".

**Success Criteria:**
- Core orchestration has **ZERO benchmark-specific imports**
- Adding a new benchmark = create files in `benchmarks/{name}/` + register in `registry.py`
- **No changes to core** when adding benchmarks
- Each benchmark owns its evaluation model (staged rubrics, binary pass/fail, etc.)
- Registry getters raise `NotImplementedError` with clear message for unimplemented benchmarks

**Design Pattern:**
- Inngest functions act as **composition roots**: one registry lookup at the start, then use only base interfaces
- Cannot pass Python objects through Inngest events (serialization boundary) - registry lookup is the standard pattern

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                           core/                                  │
│  ┌────────────────────────────┐  ┌────────────────────────────┐ │
│  │ agents/base.py             │  │ evaluation/base.py         │ │
│  │  - BaseStakeholder (ABC)   │  │  - BaseRubric (Protocol)   │ │
│  │  - BaseToolkit (ABC)       │  │      .compute_scores()     │ │
│  │  - BaseWorker (Protocol)   │  │                            │ │
│  │  - WorkerExecutionOutput   │  │                            │ │
│  └────────────────────────────┘  └────────────────────────────┘ │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ orchestration/   │  │                  │  │              │  │
│  │ worker_execute   │  │  task_evaluator  │  │ run_evaluate │  │
│  │                  │  │                  │  │              │  │
│  │ Uses registry to │  │ Delegates to     │  │ Passes data  │  │
│  │ get factories    │  │ benchmark eval   │  │ to evaluator │  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────────┘  │
└───────────┼─────────────────────┼───────────────────────────────┘
            │                     │
            ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│              benchmarks/registry.py (thin lookup)                │
│                                                                  │
│  BENCHMARK_CONFIGS: dict[BenchmarkName, BenchmarkConfig]        │
│  get_stakeholder_factory(benchmark) → Callable                  │
│  get_toolkit_factory(benchmark) → Callable                      │
│  get_rubric_evaluator(benchmark) → Callable                     │
│  deserialize_rubric(dict) → AnyRubric                           │
│  deserialize_rule(dict, type) → Rule                            │
│                                                                  │
└──────────────┬───────────────┬────────────────┬─────────────────┘
               │               │                │
       ┌───────▼───────┐ ┌─────▼─────┐  ┌───────▼───────┐
       │benchmarks/    │ │benchmarks/│  │benchmarks/    │
       │gdpeval/       │ │common/    │  │minif2f/       │
       │               │ │workers/   │  │               │
       │ factories.py  │ │           │  │ factories.py  │
       │ evaluator.py  │ │ config.py │  │ evaluator.py  │
       │ stakeholder.py│ │ react_    │  │ stakeholder.py│
       │ toolkit.py    │ │ worker.py │  │ toolkit.py    │
       │ rubric.py     │ │           │  │ schemas.py    │
       └───────────────┘ └───────────┘  └───────────────┘
```

---

## Target Folder Structure

After this refactor, the codebase structure will be:

```
h_arcane/
├── core/                              # Generic infrastructure (NO benchmark imports)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseStakeholder, BaseToolkit, BaseWorker (protocols)
│   │   │                              # WorkerExecutionOutput (return type)
│   │   └── tracing.py                 # (ReActWorker moved to benchmarks/common/workers/)
│   │
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseRubric, RubricEvaluator (protocols)
│   │   ├── context.py                 # EvaluationData, EvaluationRunner,
│   │   │                              # TaskEvaluationContext (NEW)
│   │   ├── schemas.py                 # SandboxResult, LLMJudgeResponse
│   │   └── rules/
│   │       ├── __init__.py
│   │       ├── base.py                # BaseRule
│   │       ├── code_rule.py           # CodeRule
│   │       └── llm_judge.py           # LLMJudgeRule
│   │
│   ├── orchestration/                 # Inngest functions (generic, uses registry)
│   │   ├── __init__.py
│   │   ├── worker_execute.py          # Uses get_stakeholder_factory(), get_toolkit_factory()
│   │   ├── task_evaluator.py          # Uses get_rubric_evaluator(), deserialize_rubric()
│   │   ├── run_evaluate.py            # Passes context to task_evaluator
│   │   ├── criteria_evaluator.py      # KEPT - generic via rule.evaluate(runner), uses deserialize_rule()
│   │   ├── experiment_runner.py
│   │   ├── run_cleanup.py
│   │   └── events.py                  # Generic events (CriterionEvaluationEvent uses primitives)
│   │
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── sandbox.py                 # SandboxManager
│   │   └── inngest_client.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── models.py
│   │   └── queries.py
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── evaluation_config.py
│   │   └── experiment_config.py
│   │
│   └── models/
│       ├── __init__.py
│       └── enums.py                   # BenchmarkName only
│
├── benchmarks/                        # Benchmark-specific code
│   ├── __init__.py
│   ├── registry.py                    # BENCHMARK_CONFIGS dict, getters,
│   │                                  # AnyRubric union, deserialize_rubric()
│   │
│   ├── common/                        # DONE: Shared benchmark components
│   │   ├── __init__.py
│   │   └── workers/
│   │       ├── __init__.py            # Exports BaselineType, WorkerConfig, ReActWorker
│   │       ├── config.py              # BaselineType, WorkerConfig
│   │       └── react_worker.py        # ReActWorker implementation
│   │
│   ├── gdpeval/
│   │   ├── __init__.py
│   │   ├── config.py                  # GDPEVAL_CONFIG (WorkerConfig)
│   │   ├── loader.py                  # load_gdpeval_to_database()
│   │   ├── rubric.py                  # StagedRubric with:
│   │   │                              #   - benchmark: Literal["gdpeval"] discriminator
│   │   │                              #   - compute_scores() method
│   │   ├── stakeholder.py             # RubricStakeholder (extends BaseStakeholder)
│   │   ├── toolkit.py                 # GDPEvalToolkit (extends BaseToolkit)
│   │   ├── factories.py               # NEW: create_stakeholder(), create_toolkit()
│   │   ├── rules/
│   │   │   └── __init__.py            # GDPEvalRule = CodeRule | LLMJudgeRule
│   │   └── skills/
│   │       ├── __init__.py
│   │       ├── responses.py
│   │       ├── create_csv.py
│   │       ├── read_pdf.py
│   │       └── ...
│   │
│   └── minif2f/
│       ├── __init__.py
│       ├── config.py                  # MINIF2F_CONFIG (WorkerConfig)
│       ├── loader.py                  # load_minif2f_to_database()
│       ├── schemas.py                 # MiniF2FRubric with:
│       │                              #   - benchmark: Literal["minif2f"] discriminator
│       │                              #   - compute_scores() method
│       │                              # MiniF2FProblem
│       ├── stakeholder.py             # MiniF2FStakeholder (extends BaseStakeholder)
│       ├── toolkit.py                 # MiniF2FToolkit (extends BaseToolkit)
│       ├── factories.py               # NEW: create_stakeholder(), create_toolkit()
│       ├── rules/
│       │   ├── __init__.py            # MiniF2FRule, ProofVerificationRule
│       │   └── proof_verification.py
│       └── skills/
│           ├── __init__.py
│           ├── responses.py
│           ├── write_lean_file.py
│           ├── check_lean_file.py
│           └── verify_lean_proof.py
│
├── api/
│   ├── __init__.py
│   └── main.py
│
└── settings.py
```

### Key Points

| Directory | Responsibility | Imports From |
|-----------|----------------|--------------|
| `core/` | Generic infrastructure, protocols | Nothing from `benchmarks/` |
| `core/orchestration/` | Inngest functions | `benchmarks/registry.py` only |
| `benchmarks/registry.py` | Lookup table + discriminated union | All `benchmarks/{name}/` |
| `benchmarks/{name}/` | Benchmark-specific implementation | `core/` protocols |

---

## Phase 1: Extend Base Interfaces

### 1.1 Add `model` and `system_prompt` to `BaseStakeholder`

**File:** `core/agents/base.py` - ADD two abstract properties to existing `BaseStakeholder` class:

```python
# ADD these two properties (answer() already exists):
@property
@abstractmethod
def model(self) -> str:
    """LLM model used by this stakeholder."""
    ...

@property
@abstractmethod
def system_prompt(self) -> str:
    """System prompt describing stakeholder behavior (for logging)."""
    ...
```

### 1.2 Implement New Properties in Stakeholders

**File:** `benchmarks/gdpeval/stakeholder.py` - ADD two property implementations:

```python
# ADD to RubricStakeholder class:
@property
def model(self) -> str:
    return self._model  # Already stored as self.model in __init__

@property
def system_prompt(self) -> str:
    return self.ANSWER_PROMPT
```

**File:** `benchmarks/minif2f/stakeholder.py` - ADD two property implementations:

```python
# ADD to MiniF2FStakeholder class:
@property
def model(self) -> str:
    return self._model

@property
def system_prompt(self) -> str:
    return self.HINT_PROMPT
```

---

## Phase 2: Add Discriminators and Context Types

> **Note:** We skip factory protocols. Factories are simple functions in `benchmarks/{name}/factories.py`
> and the registry just stores function references. No need for protocol overhead.

### 2.1 Add Discriminator to Benchmark Rubrics

Each benchmark rubric gets a `benchmark` field as a discriminator:

**File:** `benchmarks/gdpeval/rubric.py` (update existing)

```python
from typing import Literal

class StagedRubric(BaseModel):
    """GDPEval staged rubric with discriminator."""
    
    benchmark: Literal["gdpeval"] = "gdpeval"  # Discriminator
    
    category_name: str = Field(description="High-level category name")
    # ... rest of existing fields unchanged
```

**File:** `benchmarks/minif2f/schemas.py` (add new class)

```python
from typing import Literal

class MiniF2FRubric(BaseModel):
    """MiniF2F rubric for proof verification."""
    
    benchmark: Literal["minif2f"] = "minif2f"  # Discriminator
    
    max_score: float = Field(default=1.0, description="Maximum score for proof verification")
    partial_credit_for_syntax: float = Field(
        default=0.2, 
        description="Partial credit multiplier for valid Lean syntax that doesn't prove theorem"
    )
```

### 2.2 Create AnyRubric Union in Registrydefr

The union lives in the registry (which already imports all benchmarks), not in core:

**File:** `benchmarks/registry.py` (add)

```python
from typing import Annotated, Union
from pydantic import Field

from h_arcane.benchmarks.gdpeval.rubric import StagedRubric
from h_arcane.benchmarks.minif2f.schemas import MiniF2FRubric

# Discriminated union - Pydantic auto-selects based on "benchmark" field
AnyRubric = Annotated[
    Union[StagedRubric, MiniF2FRubric], 
    Field(discriminator="benchmark")
]

def deserialize_rubric(rubric_data: dict) -> AnyRubric:
    """Deserialize rubric dict to correct benchmark type using discriminator."""
    from pydantic import TypeAdapter
    adapter = TypeAdapter(AnyRubric)
    return adapter.validate_python(rubric_data)
```

### 2.3 Add TaskEvaluationContext to `core/evaluation/context.py`

**File:** `core/evaluation/context.py` (add to existing file)

```python
class TaskEvaluationContext(BaseModel):
    """Context for evaluating an entire task (all criteria).
    
    This bundles all the data needed to evaluate a task's outputs
    against a benchmark's rubric. The rubric is typed as BaseRubric
    (the protocol), with actual type determined at runtime via
    discriminator.
    """
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    run_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[Resource]
    rubric: "BaseRubric"  # Actual type is StagedRubric or MiniF2FRubric
```

### 2.4 Add `compute_scores` Method to `BaseRubric` Protocol

**File:** `core/evaluation/base.py` - UPDATE `BaseRubric` to include the evaluation method:

```python
# ADD imports:
import inngest
from h_arcane.core.db.models import TaskEvaluationResult
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from h_arcane.core.evaluation.context import TaskEvaluationContext

# UPDATE BaseRubric protocol (add compute_scores method):
class BaseRubric(Protocol):
    """Protocol for benchmark rubrics.
    
    Each benchmark implements its own rubric as a Pydantic model
    with a discriminator field and scoring logic.
    """
    
    benchmark: str  # Discriminator field
    
    async def compute_scores(
        self,
        context: "TaskEvaluationContext",
        inngest_ctx: inngest.Context,
    ) -> TaskEvaluationResult:
        """Compute scores for agent outputs against this rubric.
        
        Each benchmark implements its own scoring logic:
        - GDPEval: staged evaluation with gates
        - MiniF2F: binary proof verification
        """
        ...
```

This approach:
- Keeps rubrics as Pydantic models (for serialization)
- Adds evaluation method directly on the rubric
- Provides type safety via the protocol

### 2.5 Update Registry

**File:** `benchmarks/registry.py` - ADD to existing file:

```python
# ADD imports:
from typing import Annotated, Callable, Union
from pydantic import Field, TypeAdapter
from h_arcane.benchmarks.common.workers.config import WorkerConfig  # UPDATED IMPORT
from h_arcane.benchmarks.gdpeval.rubric import StagedRubric
from h_arcane.benchmarks.minif2f.schemas import MiniF2FRubric

# ADD discriminated union:
AnyRubric = Annotated[
    Union[StagedRubric, MiniF2FRubric], 
    Field(discriminator="benchmark")
]
_rubric_adapter = TypeAdapter(AnyRubric)

# ADD deserialize function:
def deserialize_rubric(rubric_data: dict) -> StagedRubric | MiniF2FRubric:
    """Deserialize rubric using discriminator."""
    return _rubric_adapter.validate_python(rubric_data)

# UPDATE BenchmarkConfig to add new fields (factories are just Callable):
class BenchmarkConfig(TypedDict):
    config: WorkerConfig
    skills_dir: Path
    loader: Callable
    stakeholder_factory: Callable  # Function: (Experiment) -> BaseStakeholder
    toolkit_factory: Callable      # Function: (run_id, stakeholder, sandbox, max_q) -> BaseToolkit
    # NOTE: No rubric_evaluator - rubrics have compute_scores() method

# UPDATE BENCHMARK_CONFIGS entries to include factory fields (see Phase 5)
# ADD new getter functions (see Phase 5)
```

---

## Phase 3: Create Factory Modules

### 3.1 GDPEval Factories

**File:** `benchmarks/gdpeval/factories.py`

```python
"""GDPEval factory functions for stakeholder and toolkit creation."""

from uuid import UUID

from h_arcane.core.db.models import Experiment
from h_arcane.core.infrastructure.sandbox import SandboxManager
from h_arcane.benchmarks.gdpeval.stakeholder import RubricStakeholder
from h_arcane.benchmarks.gdpeval.toolkit import GDPEvalToolkit
from h_arcane.benchmarks.gdpeval.rubric import StagedRubric


def create_stakeholder(experiment: Experiment) -> RubricStakeholder:
    """
    Create GDPEval stakeholder from experiment.
    
    Args:
        experiment: Experiment containing ground_truth_rubric
        
    Returns:
        RubricStakeholder configured with the rubric
    """
    rubric = StagedRubric(**experiment.ground_truth_rubric)
    return RubricStakeholder(
        ground_truth_rubric=rubric,
        task_description=experiment.task_description,
    )


def create_toolkit(
    run_id: UUID,
    stakeholder: RubricStakeholder,
    sandbox_manager: SandboxManager,
    max_questions: int,
) -> GDPEvalToolkit:
    """
    Create GDPEval toolkit.
    
    Args:
        run_id: Run ID for logging
        stakeholder: RubricStakeholder instance
        sandbox_manager: Sandbox manager
        max_questions: Maximum questions allowed
        
    Returns:
        GDPEvalToolkit with document processing tools
    """
    return GDPEvalToolkit(
        run_id=run_id,
        stakeholder=stakeholder,
        sandbox_manager=sandbox_manager,
        max_questions=max_questions,
    )
```

### 3.2 MiniF2F Factories

**File:** `benchmarks/minif2f/factories.py`

```python
"""MiniF2F factory functions for stakeholder and toolkit creation."""

from uuid import UUID

from h_arcane.core.db.models import Experiment
from h_arcane.core.infrastructure.sandbox import SandboxManager
from h_arcane.benchmarks.minif2f.stakeholder import MiniF2FStakeholder
from h_arcane.benchmarks.minif2f.toolkit import MiniF2FToolkit


def create_stakeholder(experiment: Experiment) -> MiniF2FStakeholder:
    """
    Create MiniF2F stakeholder from experiment.
    
    Args:
        experiment: Experiment containing ground truth proof
        
    Returns:
        MiniF2FStakeholder configured with the proof
    """
    ground_truth_proof = experiment.benchmark_specific_data.get("ground_truth_proof", "")
    return MiniF2FStakeholder(
        ground_truth_proof=ground_truth_proof,
        problem_statement=experiment.task_description,
    )


def create_toolkit(
    run_id: UUID,
    stakeholder: MiniF2FStakeholder,
    sandbox_manager: SandboxManager,
    max_questions: int,
) -> MiniF2FToolkit:
    """
    Create MiniF2F toolkit.
    
    Args:
        run_id: Run ID for logging
        stakeholder: MiniF2FStakeholder instance
        sandbox_manager: Sandbox manager
        max_questions: Maximum questions allowed
        
    Returns:
        MiniF2FToolkit with Lean proof tools
    """
    return MiniF2FToolkit(
        run_id=run_id,
        stakeholder=stakeholder,
        sandbox_manager=sandbox_manager,
        max_questions=max_questions,
    )
```

---

## Phase 4: Implement `compute_scores` on Rubric Classes

Instead of separate evaluator files, the scoring logic lives on the rubric classes themselves.

### 4.1 GDPEval: Add `compute_scores` to `StagedRubric`

**File:** `benchmarks/gdpeval/rubric.py` - ADD method to existing `StagedRubric` class:

```python
# ADD imports at top:
import inngest
from h_arcane.core.db.models import CriterionResult, Evaluation, TaskEvaluationResult
from h_arcane.core.evaluation.context import TaskEvaluationContext
from h_arcane.core.evaluation.rules import CodeRule, LLMJudgeRule


class StagedRubric(BaseModel):
    """GDPEval staged rubric."""
    
    benchmark: Literal["gdpeval"] = "gdpeval"  # Discriminator
    category_name: str
    stages: list[EvaluationStage]
    max_total_score: float
    # ... existing fields ...
    
    async def compute_scores(
        self,
        context: TaskEvaluationContext,
        inngest_ctx: inngest.Context,
    ) -> TaskEvaluationResult:
    """
    Evaluate GDPEval's StagedRubric.
    
    This contains all the staged evaluation logic:
    - Flatten rubric into parallel criteria
    - Evaluate each criterion (code rules, LLM judge)
    - Rebuild stage results
    - Calculate aggregate scores with gate logic
    
    Args:
        context: Task evaluation context with run_id, task_input,
                 agent_reasoning, agent_outputs, and rubric
        inngest_ctx: Inngest context for step tracing
        
    Returns:
        TaskEvaluationResult with criterion-level and aggregate scores
    """
    # Cast rubric to StagedRubric (we know it's this type for GDPEval)
    rubric = context.rubric
    if not isinstance(rubric, StagedRubric):
        raise TypeError(f"Expected StagedRubric, got {type(rubric)}")
    
    # Flatten rubric into criteria list
    async def flatten_rubric_step():
        criteria_tuples = flatten_rubric(rubric)
        return [
            FlattenedCriterion(
                stage=stage,
                rule=rule,
                stage_idx=stage_idx,
                rule_idx=rule_idx,
            )
            for stage, rule, stage_idx, rule_idx in criteria_tuples
        ]
    
    criteria_models = await inngest_ctx.step.run(
        "flatten-rubric", 
        flatten_rubric_step, 
        output_type=list[FlattenedCriterion]
    )
    criteria = [(c.stage, c.rule, c.stage_idx, c.rule_idx) for c in criteria_models]
    
    # Import the generic criterion evaluator
    from h_arcane.core.orchestration.criteria_evaluator import evaluate_criterion_fn
    from h_arcane.core.orchestration.events import CriterionEvaluationEvent
    
    # Create step invokers that call the generic criteria_evaluator
    # Each criterion invokes a separate Inngest function for full telemetry
    def make_criterion_invoker(stage: EvaluationStage, rule: GDPEvalRule, stage_idx: int, rule_idx: int):
        """Create an invoker for the generic criterion evaluator."""
        rule_type = "code" if isinstance(rule, CodeRule) else "llm_judge"
        step_id = f"criterion-{stage_idx}-{rule_idx}-{rule_type}"
        max_score = rule.weight * stage.max_points
        
        # Build generic event data
        event_data = CriterionEvaluationEvent(
            run_id=str(context.run_id),
            task_input=context.task_input,
            agent_reasoning=context.agent_reasoning,
            agent_outputs=[r.model_dump(mode="json") for r in context.agent_outputs],
            stage_name=stage.name,
            stage_idx=stage_idx,
            rule_idx=rule_idx,
            max_score=max_score,
            rule=rule.model_dump(mode="json"),
            rule_type=rule_type,
        )
        
        # Return lambda that invokes the generic criterion evaluator
        return lambda: inngest_ctx.step.invoke(
            step_id=step_id,
            function=evaluate_criterion_fn,
            data=event_data.model_dump(mode="json"),
        )
    
    # Build list of parallel invokers
    parallel_invokers = tuple(
        make_criterion_invoker(stage, rule, stage_idx, rule_idx)
        for stage, rule, stage_idx, rule_idx in criteria
    )
    
    # Execute ALL criteria in parallel - each as a separate Inngest function
    # This gives us: parallel execution + separate function per criterion in dashboard
    criterion_results_tuple = await inngest_ctx.group.parallel(parallel_invokers)
    criterion_results = list(criterion_results_tuple)
    
    # Rebuild stage results
    stage_results = _rebuild_stage_results(criterion_results, rubric)
    
    # Calculate aggregate scores
    aggregate = _calculate_aggregate_scores(context.run_id, stage_results, rubric)
    
    return TaskEvaluationResult(
        run_id=context.run_id,
        criterion_results=[cr.model_dump() for cr in criterion_results],
        total_score=aggregate.total_score,
        max_score=aggregate.max_score,
        normalized_score=aggregate.normalized_score,
        stages_evaluated=aggregate.stages_evaluated,
        stages_passed=aggregate.stages_passed,
        failed_gate=aggregate.failed_gate,
    )


def _rebuild_stage_results(
    criterion_results: list[CriterionResult],
    rubric: StagedRubric,
) -> list[dict]:
    """Rebuild criterion results into stage structure."""
    stage_results = []
    
    for stage_idx, stage in enumerate(rubric.stages):
        stage_criteria = [cr for cr in criterion_results if cr.stage_num == stage_idx]
        stage_score = sum(cr.score for cr in stage_criteria)
        stage_score = min(stage_score, stage.max_points)
        
        stage_result = {
            "stage_num": stage_idx,
            "stage_name": stage.name,
            "score": stage_score,
            "max_points": stage.max_points,
            "passed": stage_score >= stage.min_score_to_pass,
            "criteria": [
                {
                    "criterion_num": cr.criterion_num,
                    "criterion_type": cr.criterion_type,
                    "score": cr.score,
                    "max_score": cr.max_score,
                    "feedback": cr.feedback,
                }
                for cr in stage_criteria
            ],
        }
        stage_results.append(stage_result)
    
    return stage_results


def _calculate_aggregate_scores(
    run_id: UUID,
    stage_results: list[dict],
    rubric: StagedRubric,
) -> Evaluation:
    """Calculate aggregate scores from stage results."""
    total_score = 0.0
    max_score = rubric.max_total_score
    stages_evaluated = 0
    stages_passed = 0
    failed_gate = None
    
    for stage_result in stage_results:
        stages_evaluated += 1
        total_score += stage_result["score"]
        
        if stage_result["passed"]:
            stages_passed += 1
        else:
            stage_idx = stage_result["stage_num"]
            stage = rubric.stages[stage_idx]
            if stage.is_required and failed_gate is None:
                failed_gate = stage.name
            
            if stage.on_failure_action == "skip_remaining":
                break
            elif stage.on_failure_action == "zero_category":
                total_score -= stage_result["score"]
                total_score += stage.on_failure_score
    
    normalized_score = total_score / max_score if max_score > 0 else 0.0
    normalized_score = min(max(normalized_score, 0.0), 1.0)
    
    return Evaluation(
        run_id=run_id,
        total_score=total_score,
        max_score=max_score,
        normalized_score=normalized_score,
        stages_evaluated=stages_evaluated,
        stages_passed=stages_passed,
        failed_gate=failed_gate,
    )
```

### 4.2 MiniF2F: Add `compute_scores` to `MiniF2FRubric`

**File:** `benchmarks/minif2f/schemas.py` - ADD method to `MiniF2FRubric` class:

```python
# ADD imports at top:
import inngest
from h_arcane.core.db.models import CriterionResult, TaskEvaluationResult
from h_arcane.core.evaluation.context import EvaluationData, EvaluationRunner, TaskEvaluationContext
from h_arcane.core.infrastructure.sandbox import SandboxManager
from h_arcane.benchmarks.minif2f.rules import ProofVerificationRule


class MiniF2FRubric(BaseModel):
    """MiniF2F rubric for proof verification."""
    
    benchmark: Literal["minif2f"] = "minif2f"  # Discriminator
    max_score: float = 1.0
    partial_credit_for_syntax: float = 0.2
    
    async def compute_scores(
        self,
        context: TaskEvaluationContext,
        inngest_ctx: inngest.Context,
    ) -> TaskEvaluationResult:
        """
        Evaluate MiniF2F proof verification.
        
        MiniF2F evaluation is simpler than GDPEval:
        - Single criterion: does the proof verify?
        - Binary pass/fail (1.0 or 0.0)
        - Optional partial credit for valid Lean syntax
        """
        # Create proof verification rule
        rule = ProofVerificationRule(
            name="proof_verification",
            description="Verify Lean proof compiles and proves the theorem",
            weight=1.0,
        )
        
        # Build evaluation data
        data = EvaluationData(
            run_id=context.run_id,
            task_input=context.task_input,
            agent_reasoning=context.agent_reasoning,
            agent_outputs=context.agent_outputs,
            stage_idx=0,
            stage_name="Proof Verification",
            rule_idx=0,
            max_score=self.max_score,
        )
        
        # Evaluate proof
        async def verify_proof():
            sandbox_manager = SandboxManager()
            runner = EvaluationRunner(data, sandbox_manager, inngest_ctx=inngest_ctx)
            result = await rule.evaluate(runner)
            await runner.cleanup()
            return result
        
        criterion_result = await inngest_ctx.step.run(
            "verify-proof",
            verify_proof,
            output_type=CriterionResult,
        )
        
        # Calculate final score
        if criterion_result.score >= self.max_score:
            total_score = self.max_score
            passed = True
        elif criterion_result.score > 0:
            total_score = self.partial_credit_for_syntax * self.max_score
            passed = False
        else:
            total_score = 0.0
            passed = False
        
        normalized_score = total_score / self.max_score if self.max_score > 0 else 0.0
        
        return TaskEvaluationResult(
            run_id=context.run_id,
            criterion_results=[criterion_result.model_dump()],
            total_score=total_score,
            max_score=self.max_score,
            normalized_score=normalized_score,
            stages_evaluated=1,
            stages_passed=1 if passed else 0,
            failed_gate="Proof Verification" if not passed else None,
        )
```

---

## Phase 5: Update Registry with All Components

**File:** `benchmarks/registry.py` (complete)

The registry is now a thin lookup table - no factory protocols needed, just function references.

```python
"""Benchmark registry for config, loader, factories, and evaluator lookup."""

from pathlib import Path
from typing import Annotated, Callable, TypedDict, Union

from pydantic import Field, TypeAdapter

from h_arcane.core.models.enums import BenchmarkName
from h_arcane.benchmarks.common.workers.config import WorkerConfig  # MOVED from core

# Import benchmark implementations
from h_arcane.benchmarks.gdpeval.config import GDPEVAL_CONFIG
from h_arcane.benchmarks.gdpeval.loader import load_gdpeval_to_database
from h_arcane.benchmarks.gdpeval.factories import (
    create_stakeholder as gdpeval_create_stakeholder,
    create_toolkit as gdpeval_create_toolkit,
)
from h_arcane.benchmarks.gdpeval.rubric import StagedRubric  # Has compute_scores()

from h_arcane.benchmarks.minif2f.config import MINIF2F_CONFIG
from h_arcane.benchmarks.minif2f.loader import load_minif2f_to_database
from h_arcane.benchmarks.minif2f.factories import (
    create_stakeholder as minif2f_create_stakeholder,
    create_toolkit as minif2f_create_toolkit,
)
from h_arcane.benchmarks.minif2f.schemas import MiniF2FRubric  # Has compute_scores()


# Discriminated union - Pydantic auto-selects based on "benchmark" field
AnyRubric = Annotated[
    Union[StagedRubric, MiniF2FRubric], 
    Field(discriminator="benchmark")
]

_rubric_adapter = TypeAdapter(AnyRubric)


def deserialize_rubric(rubric_data: dict) -> BaseRubric:
    """Deserialize rubric dict to correct benchmark type using discriminator.
    
    Uses Pydantic's discriminated union to automatically select the
    correct rubric class based on the 'benchmark' field in the data.
    """
    return _rubric_adapter.validate_python(rubric_data)


# Rule deserialization for criteria_evaluator
from h_arcane.core.evaluation.rules import CodeRule, LLMJudgeRule
from h_arcane.benchmarks.minif2f.rules import ProofVerificationRule

_RULE_TYPES = {
    "code": CodeRule,
    "llm_judge": LLMJudgeRule,
    "proof_verification": ProofVerificationRule,
}

def deserialize_rule(rule_data: dict, rule_type: str) -> CodeRule | LLMJudgeRule | ProofVerificationRule:
    """Deserialize rule dict to correct rule type."""
    rule_class = _RULE_TYPES.get(rule_type)
    if not rule_class:
        raise ValueError(f"Unknown rule type: {rule_type}")
    return rule_class(**rule_data)


class BenchmarkConfig(TypedDict):
    """Full configuration for a benchmark."""
    config: WorkerConfig
    skills_dir: Path
    loader: Callable
    stakeholder_factory: Callable  # (Experiment) -> BaseStakeholder
    toolkit_factory: Callable      # (run_id, stakeholder, sandbox, max_q) -> BaseToolkit
    # NOTE: No rubric_evaluator - evaluation logic is on BaseRubric.compute_scores()


# Compute paths relative to this file
_BENCHMARKS_DIR = Path(__file__).parent


BENCHMARK_CONFIGS: dict[BenchmarkName, BenchmarkConfig] = {
    BenchmarkName.GDPEVAL: {
        "config": GDPEVAL_CONFIG,
        "skills_dir": _BENCHMARKS_DIR / "gdpeval" / "skills",
        "loader": load_gdpeval_to_database,
        "stakeholder_factory": gdpeval_create_stakeholder,
        "toolkit_factory": gdpeval_create_toolkit,
    },
    BenchmarkName.MINIF2F: {
        "config": MINIF2F_CONFIG,
        "skills_dir": _BENCHMARKS_DIR / "minif2f" / "skills",
        "loader": load_minif2f_to_database,
        "stakeholder_factory": minif2f_create_stakeholder,
        "toolkit_factory": minif2f_create_toolkit,
    },
}


# Helper to check benchmark exists
def _get_config(benchmark_name: BenchmarkName) -> BenchmarkConfig:
    """Get config for benchmark, raising clear error if not implemented."""
    if benchmark_name not in BENCHMARK_CONFIGS:
        implemented = [b.value for b in BENCHMARK_CONFIGS.keys()]
        raise NotImplementedError(
            f"Benchmark '{benchmark_name.value}' is not implemented. "
            f"Implemented benchmarks: {implemented}"
        )
    return BENCHMARK_CONFIGS[benchmark_name]


# Getters - all raise NotImplementedError for unknown benchmarks
def get_worker_config(benchmark_name: BenchmarkName) -> WorkerConfig:
    return _get_config(benchmark_name)["config"]


def get_skills_dir(benchmark_name: BenchmarkName) -> Path:
    return _get_config(benchmark_name)["skills_dir"]


def get_benchmark_loader(benchmark_name: BenchmarkName) -> Callable:
    return _get_config(benchmark_name)["loader"]


def get_stakeholder_factory(benchmark_name: BenchmarkName) -> Callable:
    """Get factory function: (Experiment) -> BaseStakeholder."""
    return _get_config(benchmark_name)["stakeholder_factory"]


def get_toolkit_factory(benchmark_name: BenchmarkName) -> Callable:
    """Get factory function: (run_id, stakeholder, sandbox, max_q) -> BaseToolkit."""
    return _get_config(benchmark_name)["toolkit_factory"]

# NOTE: No get_rubric_evaluator() - call rubric.compute_scores() directly
```

---

## Phase 6: Simplify Core Orchestration (Composition Root Pattern)

Inngest functions act as **composition roots**: they do ONE lookup from the registry at the start,
then use ONLY base interfaces (`BaseStakeholder`, `BaseToolkit`) for all operations.

> **Why not pass objects via events?** Inngest events are serialized to JSON - you cannot pass 
> Python class instances or functions. The registry lookup is the standard pattern for
> distributed/serialization-boundary systems.

### 6.1 Simplify `worker_execute.py`

**Before (lines 179-208):** if/elif chain with concrete types

**After:** Single lookup, then interfaces only

```python
from h_arcane.core.agents.base import BaseStakeholder, BaseToolkit  # Base interfaces
from h_arcane.benchmarks.registry import (
    get_stakeholder_factory,
    get_toolkit_factory,
    get_worker_config,
    get_skills_dir,
)

async def worker_execute_fn(ctx: inngest.Context, ...):
    ...
    benchmark_name = BenchmarkName(experiment.benchmark)
    
    # === COMPOSITION ROOT: one lookup per dependency ===
    stakeholder_factory = get_stakeholder_factory(benchmark_name)  # Raises NotImplementedError if unknown
    toolkit_factory = get_toolkit_factory(benchmark_name)
    
    # Create instances via factories - return types are base interfaces
    stakeholder: BaseStakeholder = stakeholder_factory(experiment)
    toolkit: BaseToolkit = toolkit_factory(run_id, stakeholder, SandboxManager(), run.max_questions)
    
    # === From here: ONLY use interface methods ===
    tools = toolkit.get_tools()                    # BaseToolkit.get_tools()
    answer = await toolkit.ask_stakeholder(q)      # BaseToolkit.ask_stakeholder()
    model = stakeholder.model                       # BaseStakeholder.model
    prompt = stakeholder.system_prompt             # BaseStakeholder.system_prompt
```

**DELETE these imports** (no longer needed):
```python
from h_arcane.benchmarks.gdpeval.stakeholder import RubricStakeholder
from h_arcane.benchmarks.gdpeval.toolkit import GDPEvalToolkit
from h_arcane.benchmarks.minif2f.stakeholder import MiniF2FStakeholder
from h_arcane.benchmarks.minif2f.toolkit import MiniF2FToolkit
from h_arcane.benchmarks.gdpeval.rubric import StagedRubric
```

### 6.2 Simplify `task_evaluator.py`

Rubric now has `compute_scores()` method - just call it directly.

**Before:** 223 lines of GDPEval-specific evaluation logic

**After:** ~40 lines - deserialize rubric and call its method

```python
"""Task run evaluator - delegates to rubric's compute_scores method."""

from uuid import UUID

import inngest

from h_arcane.core.db.models import Resource, TaskEvaluationResult
from h_arcane.core.infrastructure.inngest_client import inngest_client
from h_arcane.core.evaluation.context import TaskEvaluationContext
from h_arcane.core.orchestration.events import TaskEvaluationEvent
from h_arcane.benchmarks.registry import deserialize_rubric


@inngest_client.create_function(
    fn_id="evaluate-task-run",
    trigger=inngest.TriggerEvent(event="task/evaluate"),
    retries=2,
    concurrency=[inngest.Concurrency(limit=10, scope="fn")],
    output_type=TaskEvaluationResult,
)
async def evaluate_task_run(ctx: inngest.Context) -> TaskEvaluationResult:
    """
    Evaluate a task run by delegating to rubric.compute_scores().
    
    This function is now a thin wrapper that:
    1. Deserializes rubric to benchmark-specific type (via discriminator)
    2. Creates TaskEvaluationContext
    3. Calls rubric.compute_scores() - polymorphic dispatch
    """
    event_data = TaskEvaluationEvent.model_validate(ctx.event.data)
    run_id = UUID(event_data.run_id)
    
    # Deserialize rubric using discriminated union (auto-selects StagedRubric or MiniF2FRubric)
    rubric = deserialize_rubric(event_data.rubric)
    
    # Deserialize agent outputs
    agent_outputs = [Resource(**r_dict) for r_dict in event_data.agent_outputs]
    
    # Build context
    context = TaskEvaluationContext(
        run_id=run_id,
        task_input=event_data.task_input,
        agent_reasoning=event_data.agent_reasoning,
        agent_outputs=agent_outputs,
        rubric=rubric,
    )
    
    # Polymorphic dispatch - each rubric type implements its own scoring
    return await rubric.compute_scores(context, ctx)
```

### 6.3 Update `run_evaluate.py`

**Change:** Add `experiment_id` to `TaskEvaluationEvent`

```python
# Before:
data=TaskEvaluationEvent(
    run_id=str(run_id),
    task_input=experiment.task_description,
    ...
)

# After:
data=TaskEvaluationEvent(
    run_id=str(run_id),
    experiment_id=str(experiment.id),  # NEW
    task_input=experiment.task_description,
    ...
)
```

**Remove imports:**
```python
# DELETE:
from h_arcane.benchmarks.gdpeval.rubric import StagedRubric
```

### 6.4 Genericize `events.py`

**Before:**
```python
from h_arcane.benchmarks.gdpeval.rubric import EvaluationStage
from h_arcane.core.evaluation.rules import CodeRule, LLMJudgeRule
from h_arcane.benchmarks.minif2f.rules import ProofVerificationRule

class CriterionEvaluationEvent(BaseModel):
    stage: EvaluationStage  # GDPEval-specific!
    rule: CodeRule | LLMJudgeRule | ProofVerificationRule  # Explicit union!
```

**After:**
```python
# No benchmark imports needed!

class TaskEvaluationEvent(BaseModel):
    """Generic task evaluation event."""
    run_id: str
    experiment_id: str  # NEW - needed to look up benchmark
    task_input: str
    agent_reasoning: str
    agent_outputs: list[dict]
    rubric: dict  # Benchmark-specific rubric as dict


class CriterionEvaluationEvent(BaseModel):
    """Generic criterion evaluation event.
    
    Uses primitive types instead of benchmark-specific types.
    The rule is passed as a dict and deserialized in criteria_evaluator.py
    using the registry's rule deserializer.
    """
    run_id: str
    task_input: str
    agent_reasoning: str
    agent_outputs: list[dict]  # Serialized Resources
    
    # Generic criterion info (instead of EvaluationStage)
    stage_name: str
    stage_idx: int
    rule_idx: int
    max_score: float
    
    # Rule as dict - deserialized in criteria_evaluator using registry
    rule: dict
    rule_type: str  # "code", "llm_judge", "proof_verification" - for deserialization
```

### 6.5 Update `criteria_evaluator.py` to Use Registry for Rule Deserialization

**File:** `core/orchestration/criteria_evaluator.py`

The criteria evaluator stays but uses registry to deserialize rules:

```python
from h_arcane.benchmarks.registry import deserialize_rule

@inngest_client.create_function(...)
async def evaluate_criterion_fn(ctx: inngest.Context) -> CriterionResult:
    event_data = CriterionEvaluationEvent.model_validate(ctx.event.data)
    run_id = UUID(event_data.run_id)
    
    # Deserialize rule using registry (handles CodeRule, LLMJudgeRule, ProofVerificationRule)
    rule = deserialize_rule(event_data.rule, event_data.rule_type)
    
    # Build evaluation data from generic fields
    data = EvaluationData(
        run_id=run_id,
        task_input=event_data.task_input,
        agent_reasoning=event_data.agent_reasoning,
        agent_outputs=[Resource(**r) for r in event_data.agent_outputs],
        stage_idx=event_data.stage_idx,
        stage_name=event_data.stage_name,
        rule_idx=event_data.rule_idx,
        max_score=event_data.max_score,
    )
    
    # Rest stays the same - polymorphic evaluation
    sandbox_manager = SandboxManager()
    runner = EvaluationRunner(data, sandbox_manager, inngest_ctx=ctx)
    result = await rule.evaluate(runner)
    await ctx.step.run("cleanup", lambda: runner.cleanup())
    return result
```

---

## Phase 7: Cleanup and Verification

**Files to keep (now generic):**

| File | Status |
|------|--------|
| `core/orchestration/criteria_evaluator.py` | KEEP - already generic via `rule.evaluate(runner)` |
| `core/orchestration/task_evaluator.py` | KEEP - now delegates to benchmark evaluators |

**Files that may have dead code:**

| File | Action |
|------|--------|
| `core/orchestration/events.py` | Remove old `EvaluationStage` import, update `CriterionEvaluationEvent` |

**Inngest observability:**
- Each benchmark evaluator uses `inngest_ctx.group.parallel()` for parallel criterion invocation
- Each criterion calls `ctx.step.invoke(evaluate_criterion_fn, ...)` - **separate Inngest function per criterion**
- Dashboard shows: task_evaluator → N parallel evaluate_criterion_fn invocations
- Full per-criterion telemetry and retry preserved

---

## Migration Checklist

### Pre-work (DONE)
- [x] Move `ReActWorker` to `benchmarks/common/workers/react_worker.py`
- [x] Add `BaseWorker` protocol and `WorkerExecutionOutput` to `core/agents/base.py`
- [x] Move `WorkerConfig` to `benchmarks/common/workers/config.py`
- [x] Move `BaselineType` to `benchmarks/common/workers/config.py`
- [x] Update all imports for moved types

### Phase 1: Extend Base Interfaces
- [ ] Add `model` and `system_prompt` properties to `BaseStakeholder` in `core/agents/base.py`
- [ ] Update `RubricStakeholder` to implement new properties
- [ ] Update `MiniF2FStakeholder` to implement new properties

### Phase 2: Add Discriminators and Context Types
- [ ] Add `benchmark: Literal["gdpeval"]` discriminator to `StagedRubric`
- [ ] Create `MiniF2FRubric` with `benchmark: Literal["minif2f"]` discriminator
- [ ] Add `AnyRubric` discriminated union to `benchmarks/registry.py`
- [ ] Add `deserialize_rubric()` function to `benchmarks/registry.py`
- [ ] Add `TaskEvaluationContext` to `core/evaluation/context.py`
- [ ] Update `BaseRubric` protocol to include `compute_scores()` method
- [ ] Update `BenchmarkConfig` TypedDict in registry (factories only, no evaluator)

### Phase 3: Create Factory Modules
- [ ] Create `benchmarks/gdpeval/factories.py` (simple functions)
- [ ] Create `benchmarks/minif2f/factories.py`

### Phase 4: Implement `compute_scores` on Rubric Classes
- [ ] Add `compute_scores()` method to `StagedRubric` in `benchmarks/gdpeval/rubric.py`
- [ ] Add `compute_scores()` method to `MiniF2FRubric` in `benchmarks/minif2f/schemas.py`

### Phase 5: Update Registry
- [ ] Add factory imports to registry
- [ ] Add `AnyRubric` discriminated union and `deserialize_rubric()` function
- [ ] Add `deserialize_rule()` function to registry
- [ ] Add new getter functions (`get_stakeholder_factory`, `get_toolkit_factory`)
- [ ] Update `BENCHMARK_CONFIGS` dict with factory fields

### Phase 6: Simplify Core Orchestration
- [ ] Refactor `worker_execute.py` to use registry factories (delete if/elif chain)
- [ ] Refactor `task_evaluator.py` to delegate to registry evaluators
- [ ] Update `run_evaluate.py` to pass `experiment_id`
- [ ] Genericize `events.py` - update `CriterionEvaluationEvent` to use primitive types
- [ ] Update `criteria_evaluator.py` to use `deserialize_rule()` from registry
- [ ] Remove all direct benchmark imports from core orchestration

### Phase 7: Cleanup and Verification
- [ ] Verify `criteria_evaluator.py` works with generic event schema
- [ ] Run pyright to verify no type errors
- [ ] Run end-to-end tests for GDPEval
- [ ] Run end-to-end tests for MiniF2F

---

## Result

After this refactor:

| Metric | Before | After |
|--------|--------|-------|
| Benchmark imports in core | 8 | 0 |
| Lines changed to add benchmark | ~50 in core | 0 in core |
| Files changed to add benchmark | 4 core files | 0 core files |
| Benchmark owns evaluation logic | No | Yes |
| Worker implementation in core | Yes | No (in benchmarks/common/) |
| WorkerConfig in core | Yes | No (in benchmarks/common/) |

**Adding a new benchmark now requires:**
1. Create `benchmarks/{name}/stakeholder.py` (extends `BaseStakeholder`)
2. Create `benchmarks/{name}/toolkit.py` (extends `BaseToolkit`)
3. Create `benchmarks/{name}/factories.py` (2 simple functions)
4. Create rubric class with:
   - `benchmark: Literal["{name}"]` discriminator field
   - `compute_scores()` method (implements `BaseRubric` protocol)
5. Register in `benchmarks/registry.py` (add entry to dict + update AnyRubric union)

**Adding a new worker type** (if needed):
1. Create `benchmarks/common/workers/{name}_worker.py` (implements `BaseWorker` protocol)
2. Add to `BaselineType` enum in `benchmarks/common/workers/config.py`

**Zero changes to core orchestration.**

