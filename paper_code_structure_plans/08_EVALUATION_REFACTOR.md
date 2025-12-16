# Evaluation System Refactor Plan

## Status: ✅ IMPLEMENTED

This document reflects the actual implementation (not the original plan).

---

## Problem Statement

The evaluation system was a "bundle of functions" spread across multiple files with:
- Duplicate/dead code
- Mixed concerns (building, parsing, executing, Inngest orchestration)
- Unclear separation of responsibilities

### Original File Structure (Before)

```
h_arcane/evaluation/
├── context.py              # 24 lines - Simple data container
├── rule_evaluators.py      # 440 lines - Evaluation functions
├── criteria_evaluator.py   # 776 lines - Inngest handlers + dead code
├── task_evaluator.py       # 219 lines - Orchestration
├── schemas.py              # 20 lines - LLMJudgeResponse
├── models.py               # FlattenedCriterion
└── rubric_flattener.py     # 38 lines

h_arcane/schemas/
└── staged_rubric_schema.py # 203 lines - Rules + Rubric definitions
```

---

## Implemented Architecture

### Design Principles

1. **Rules own their evaluation logic** - Each rule class contains all logic for evaluating itself
2. **Runner provides infrastructure with Inngest steps** - `EvaluationRunner` handles sandbox/LLM API with granular step tracing
3. **Data separated from infrastructure** - `EvaluationData` (pure data) vs `EvaluationRunner` (infrastructure)
4. **Inngest context required** - All evaluation goes through Inngest for observability

### Final File Structure

```
h_arcane/evaluation/
├── __init__.py             # Public exports
├── context.py              # ~180 lines - EvaluationData + EvaluationRunner
├── schemas.py              # ~30 lines - SandboxResult, LLMJudgeResponse
├── rubric.py               # ~125 lines - StagedRubric, EvaluationStage, GDPEvalStagedRubric
├── criteria_evaluator.py   # ~73 lines - Inngest function evaluate_criterion_fn
├── task_evaluator.py       # ~215 lines - Inngest orchestration
├── models.py               # ~16 lines - FlattenedCriterion
├── rubric_flattener.py     # ~34 lines - Flatten rubric for parallel eval
└── rules/
    ├── __init__.py         # ~16 lines - Exports BaseRule, CodeRule, LLMJudgeRule, AnyRule
    ├── base.py             # ~35 lines - BaseRule ABC
    ├── code_rule.py        # ~195 lines - CodeRule with granular Inngest steps
    └── llm_judge.py        # ~195 lines - LLMJudgeRule with granular Inngest steps

DELETED:
├── rule_evaluators.py      # Logic moved to rules/
└── h_arcane/schemas/staged_rubric_schema.py  # Moved to evaluation/, no backward compat
```

### Evaluation Flow

```
task_evaluator.py
    └── evaluate_task_run() [Inngest]
        └── invokes evaluate_criterion_fn() for each rule [Inngest parallel]
            └── criteria_evaluator.py:evaluate_criterion_fn()
                └── creates EvaluationRunner(data, sandbox_manager, inngest_ctx)
                └── calls rule.evaluate(runner)
                    └── rules/code_rule.py:CodeRule.evaluate()
                        └── runner.step("ensure-sandbox", ...)
                        └── runner.step("upload-files", ...)
                        └── runner.step("execute-code", ...)
                        └── runner.step("parse-result", ...)
                    └── rules/llm_judge.py:LLMJudgeRule.evaluate()
                        └── runner.step("call-llm-api", ...)
                        └── runner.step("compute-score", ...)
```

---

## Key Implementation Details

### EvaluationData (Pure Data)

```python
class EvaluationData(BaseModel):
    """Pure data for evaluation - no infrastructure methods."""
    run_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[Resource]
    stage_idx: int
    stage_name: str
    rule_idx: int
    max_score: float
```

### EvaluationRunner (Infrastructure with Inngest Steps)

```python
class EvaluationRunner:
    """Infrastructure runner with Inngest step tracing."""
    
    def __init__(
        self,
        data: EvaluationData,
        sandbox_manager: SandboxManager,
        inngest_ctx: inngest.Context,  # REQUIRED - no optional/None
    ):
        ...
    
    async def step(self, step_id: str, fn: Callable, output_type=None) -> R:
        """Wrap function in Inngest step for observability."""
        return await self.inngest_ctx.step.run(step_id, fn, output_type=output_type)
    
    async def ensure_sandbox(self) -> dict: ...
    async def upload_files(self, files: list[Resource]) -> dict: ...
    async def execute_code(self, code: str) -> SandboxResult: ...
    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T: ...
    async def cleanup(self) -> None: ...
```

### Rule Evaluate Signature

```python
class BaseRule(BaseModel, ABC):
    @abstractmethod
    async def evaluate(self, runner: "EvaluationRunner") -> "CriterionResult":
        """Evaluate this rule using the provided runner."""
        ...
```

### Inngest Step Granularity

**CodeRule steps:**
1. `ensure-sandbox` - Create sandbox for run
2. `upload-files` - Upload agent outputs to `/evaluation/`
3. `execute-code` - Run evaluation code in sandbox
4. `parse-result` - Parse JSON output from execution

**LLMJudgeRule steps:**
1. `call-llm-api` - Call OpenAI with structured output
2. `compute-score` - Convert verdict to score

---

## Design Decision: Inngest Context Required

We pass `inngest.Context` directly to `EvaluationRunner` for step-level observability.
This couples the runner to Inngest, but:
- Inngest is our primary orchestration framework and we want granular step tracing
- If we need to swap orchestration frameworks later, we can introduce a `StepRunner`
  protocol that abstracts `ctx.step.run()` - `EvaluationRunner` would then accept
  `StepRunner` instead of `inngest.Context`.

**Note:** There is no "direct call" mode without Inngest. All evaluation goes through Inngest.

---

## Line Count Summary (Actual)

| File | Lines |
|------|-------|
| context.py | ~180 |
| schemas.py | ~30 |
| rubric.py | ~125 |
| criteria_evaluator.py | ~73 |
| task_evaluator.py | ~215 |
| models.py | ~16 |
| rubric_flattener.py | ~34 |
| rules/__init__.py | ~16 |
| rules/base.py | ~35 |
| rules/code_rule.py | ~195 |
| rules/llm_judge.py | ~195 |
| **Total** | **~1114** |

Original total was ~1682 lines. Net reduction of ~570 lines with much cleaner separation.

---

## Import Locations

```python
# Rules
from h_arcane.evaluation.rules import CodeRule, LLMJudgeRule, BaseRule, AnyRule

# Rubric
from h_arcane.evaluation.rubric import StagedRubric, EvaluationStage, GDPEvalStagedRubric

# Context
from h_arcane.evaluation.context import EvaluationData, EvaluationRunner

# Inngest function
from h_arcane.evaluation.criteria_evaluator import evaluate_criterion_fn

# Or via main __init__.py
from h_arcane.evaluation import (
    CodeRule, LLMJudgeRule, StagedRubric, EvaluationStage,
    EvaluationData, EvaluationRunner, evaluate_criterion_fn,
)
```

---

## Execution Checklist

- [x] Phase 0: Delete dead code (lines 583-776 in criteria_evaluator.py)
- [x] Phase 1: Create EvaluationData + EvaluationRunner with Inngest step support
- [x] Phase 2: Create evaluation/rules/ structure with CodeRule
- [x] Phase 3: Create LLMJudgeRule in evaluation/rules/
- [x] Phase 4: Simplify criteria_evaluator.py to thin Inngest wrapper
- [x] Phase 5: Move StagedRubric & EvaluationStage to evaluation/rubric.py
- [x] Phase 6: Delete old files (rule_evaluators.py, staged_rubric_schema.py), update imports
- [ ] Test: Run evaluation on sample task

---

## Changes from Original Plan

| Aspect | Original Plan | Actual Implementation |
|--------|---------------|----------------------|
| Context | Single `EvaluationContext` | Split: `EvaluationData` + `EvaluationRunner` |
| Inngest integration | Not detailed | Runner takes required `inngest_ctx` for granular steps |
| Rule signature | `evaluate(context)` | `evaluate(runner)` |
| `evaluate_criterion()` | Keep as wrapper | Deleted - only Inngest function |
| `criteria_evaluator.py` | Merge into task_evaluator | Kept separate (~73 lines) |
| Backward compat | Optional re-exports | No backward compat - deleted old file |
| Step granularity | One step per rule | Multiple steps per rule (4-5 for code, 2-3 for LLM) |
