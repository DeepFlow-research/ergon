# Evaluation Architecture

**Approach**: Functional evaluation system with Inngest orchestration.

**Key Design**: 
- `evaluate_criteria`: Single criterion evaluator (code rule or LLM judge)
- `evaluate_task_run`: Orchestrator that flattens rubric → evaluates all criteria → rebuilds results → saves to DB

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│              run_evaluate (Inngest Function)                │
│  - Loads run, experiment, resources, actions               │
│  - Invokes evaluate_task_run                                │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│         evaluate_task_run (Inngest Function)                │
│                                                              │
│  1. Iterate StagedRubric → list[(stage, rule, stage_idx, rule_idx)] │
│  2. For each criterion:                                     │
│     step.invoke(evaluate_criteria, ...)                     │
│  3. Collect all criterion results                          │
│  4. Rebuild into stage structure                            │
│  5. Calculate aggregate scores                             │
│  6. Save to Postgres (CriterionResult + Evaluation)        │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │ step.invoke (parallel)
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
┌──────────────────┐          ┌──────────────────┐
│ evaluate_criteria│          │ evaluate_criteria│
│ (Code Rule)      │          │ (LLM Judge)      │
└──────────────────┘          └──────────────────┘
```

---

## Data Structures

### CriterionEvaluationResult

```python
class CriterionEvaluationResult(BaseModel):
    """Result of evaluating a single criterion."""
    # Identity
    stage_num: int
    criterion_num: int
    
    # Scoring
    score: float
    max_score: float  # criterion_weight * stage_max_points (normalized)
    
    # Feedback
    feedback: str
    
    # What was evaluated
    evaluated_action_ids: list[str] = []  # UUIDs of actions
    evaluated_resource_ids: list[str] = []  # UUIDs of resources
    
    # Error handling
    error: str | None = None
```

---

## Core Functions

### 1. evaluate_criteria

**Purpose**: Evaluate a single criterion against task outputs.

**Input**: 
- `agent_reasoning: str` - Worker's reasoning/output text
- `agent_outputs: list[Resource]` - Output files/resources
- `stage: EvaluationStage` - The stage containing this criterion
- `rule: CodeRule | LLMJudgeRule` - The rule/criterion to evaluate
- `stage_idx: int` - Stage index (0, 1, 2, ...)
- `rule_idx: int` - Rule index within stage (0, 1, 2, ...)
- `task_input: str` - Original task description

**Process**:
- For code rules: Execute code in sandbox with access to files
- For LLM judges: Upload files to LLM (multimodal), call with prompt

**Returns**: `CriterionEvaluationResult`

```python
# h_arcane/evaluation/criteria_evaluator.py
from h_arcane.agents.sandbox import SandboxManager
from openai import AsyncOpenAI
import json
from pathlib import Path

async def evaluate_criteria(
    agent_reasoning: str,
    agent_outputs: list[Resource],
    stage: EvaluationStage,
    rule: CodeRule | LLMJudgeRule,
    stage_idx: int,
    rule_idx: int,
    task_input: str,
    sandbox_manager: SandboxManager | None = None,
) -> CriterionEvaluationResult:
    """
    Evaluate a single criterion against task outputs.
    
    Args:
        agent_reasoning: Worker's reasoning/output text
        agent_outputs: Output files/resources
        stage: The stage containing this criterion
        rule: The rule/criterion to evaluate (CodeRule or LLMJudgeRule)
        stage_idx: Stage index (0, 1, 2, ...)
        rule_idx: Rule index within stage (0, 1, 2, ...)
        task_input: Original task description
        sandbox_manager: Optional sandbox for code rule execution
    
    Returns:
        CriterionEvaluationResult with score, feedback, and evaluated references
    """
    max_score = rule.weight * stage.max_points
    
    if rule.type == "code":
        return await _evaluate_code_rule(
            agent_reasoning=agent_reasoning,
            agent_outputs=agent_outputs,
            rule=rule,
            stage=stage,
            stage_idx=stage_idx,
            rule_idx=rule_idx,
            task_input=task_input,
            sandbox_manager=sandbox_manager,
            max_score=max_score,
        )
    elif rule.type == "llm_judge":
        return await _evaluate_llm_judge(
            agent_reasoning=agent_reasoning,
            agent_outputs=agent_outputs,
            rule=rule,
            stage=stage,
            stage_idx=stage_idx,
            rule_idx=rule_idx,
            task_input=task_input,
            max_score=max_score,
        )
    else:
        raise ValueError(f"Unknown rule type: {rule.type}")

async def _evaluate_code_rule(
    agent_reasoning: str,
    agent_outputs: list[Resource],
    rule: CodeRule,
    stage: EvaluationStage,
    stage_idx: int,
    rule_idx: int,
    task_input: str,
    sandbox_manager: SandboxManager | None,
    max_score: float,
) -> CriterionEvaluationResult:
    """Execute code rule in sandbox."""
    if sandbox_manager is None:
        # Create temporary sandbox for evaluation
        sandbox_manager = SandboxManager(run_id=uuid4())
        await sandbox_manager.create()
        should_terminate = True
    else:
        should_terminate = False
    
    try:
        # Upload output files to sandbox
        for resource in agent_outputs:
            sandbox_path = f"/evaluation/{resource.name}"
            content = resource.load_content()
            await sandbox_manager.sandbox.files.write(sandbox_path, content)
        
        # Prepare evaluation context
        # Code rules expect: evaluate(task_input: str, agent_reasoning: str, output_files: dict[str, bytes]) -> float | tuple[float, str]
        # Note: GDPEval code rules are converted from (workflow, context) signature via one-off script (see Phase 1 in master plan)
        code = f"""
{rule.code}

# Execute evaluation
try:
    result = evaluate(
        task_input={json.dumps(task_input)},
        agent_reasoning={json.dumps(agent_reasoning)},
        output_files={{"/evaluation/{r.name}": open("/evaluation/{r.name}", "rb").read() for r in {json.dumps([r.name for r in agent_outputs])}}}
    )
    
    if isinstance(result, tuple):
        score, feedback = result
    else:
        score = float(result)
        feedback = f"Code rule '{rule.name}' scored {{score}}/{{max_score}}"
    
    print(json.dumps({{
        "score": score,
        "feedback": feedback,
        "evaluated_resource_ids": {json.dumps([str(r.id) for r in agent_outputs])}
    }}))
except Exception as e:
    print(json.dumps({{
        "score": 0.0,
        "feedback": f"Error executing code rule: {{str(e)}}",
        "evaluated_resource_ids": []
    }}))
"""
        
        execution = await sandbox_manager.sandbox.run_code(code, language="python", timeout=30)
        
        # Parse result
        output = "\n".join(execution.logs.stdout) if execution.logs else ""
        try:
            result_data = json.loads(output)
            score = min(max(result_data["score"], 0.0), max_score)
            feedback = result_data["feedback"]
            evaluated_resource_ids = result_data.get("evaluated_resource_ids", [])
        except (json.JSONDecodeError, KeyError):
            error_msg = "\n".join(execution.logs.stderr) if execution.logs else "Failed to parse result"
            score = 0.0
            feedback = f"Error evaluating code rule: {error_msg}"
            evaluated_resource_ids = []
        
        return CriterionEvaluationResult(
            stage_num=stage_idx,
            criterion_num=rule_idx,
            score=score,
            max_score=max_score,
            feedback=feedback,
            evaluated_resource_ids=evaluated_resource_ids,
        )
    
    finally:
        if should_terminate:
            await sandbox_manager.terminate()

async def _evaluate_llm_judge(
    agent_reasoning: str,
    agent_outputs: list[Resource],
    rule: LLMJudgeRule,
    stage: EvaluationStage,
    stage_idx: int,
    rule_idx: int,
    task_input: str,
    max_score: float,
) -> CriterionEvaluationResult:
    """Execute LLM judge evaluation."""
    client = AsyncOpenAI()
    
    # Build messages with multimodal content
    messages = [
        {
            "role": "system",
            "content": rule.judge_prompt,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"""
Task Input: {task_input}

Agent Reasoning/Output: {agent_reasoning}

Criterion: {rule.description}
{"Expectation: " + rule.expectation if rule.expectation else ""}

Please evaluate this output and provide:
1. A score from 0 to {max_score}
2. Detailed feedback explaining your score
""",
                },
                # Add file content as images (for PDFs, Excel, etc.)
                *[
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{resource.mime_type};base64,{base64.b64encode(resource.load_content()).decode()}"
                        }
                    }
                    for resource in agent_outputs
                    if resource.mime_type.startswith("image/") or resource.mime_type in ["application/pdf", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]
                ],
            ],
        },
    ]
    
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=500,
    )
    
    # Parse LLM response (expects score and feedback)
    # Format: "Score: X\nFeedback: ..."
    content = response.choices[0].message.content
    
    # Extract score (look for "Score: X" pattern)
    import re
    score_match = re.search(r"Score:\s*([\d.]+)", content)
    if score_match:
        score = min(max(float(score_match.group(1)), 0.0), max_score)
    else:
        score = max_score * 0.5  # Default to midpoint if parsing fails
    
    feedback = content
    
    return CriterionEvaluationResult(
        stage_num=stage_idx,
        criterion_num=rule_idx,
        score=score,
        max_score=max_score,
        feedback=feedback,
        evaluated_resource_ids=[str(r.id) for r in agent_outputs],
    )
```

---

### 2. Iterate Rubric

```python
# h_arcane/evaluation/rubric_flattener.py
from paper_code_structure_plans.schemas.staged_rubric_schema import StagedRubric, EvaluationStage
from manager_agent_gym.core.agents.manager_agent.implementations.rubric_generation_manager.rubric_generation import (
    CodeRule,
    LLMJudgeRule,
)

def iterate_rubric_criteria(rubric: StagedRubric) -> list[tuple[EvaluationStage, CodeRule | LLMJudgeRule, int, int]]:
    """
    Iterate over all criteria in rubric, returning (stage, rule, stage_idx, rule_idx) tuples.
    
    Returns:
        List of (stage, rule, stage_idx, rule_idx) tuples, one per rule in rubric
    """
    criteria = []
    
    for stage_idx, stage in enumerate(rubric.stages):
        for rule_idx, rule in enumerate(stage.rules):
            criteria.append((stage, rule, stage_idx, rule_idx))
    
    return criteria
```

---

### 3. evaluate_task_run (Inngest Function)

```python
# h_arcane/inngest/functions.py
from h_arcane.evaluation.criteria_evaluator import evaluate_criteria
from h_arcane.evaluation.rubric_flattener import flatten_rubric
from h_arcane.db import queries

@inngest_client.create_function(
    fn_id="evaluate-task-run",
    trigger=inngest.TriggerEvent(event="evaluation/start"),
    retries=1,
)
async def evaluate_task_run(
    ctx: inngest.Context,
    step: inngest.Step,
) -> dict:
    """
    Evaluate a task run against ground truth rubric.
    
    Event data:
        run_id: UUID
        task_input: str
        agent_reasoning: str
        agent_output_resource_ids: list[str]
    """
    run_id = UUID(ctx.event.data["run_id"])
    task_input = ctx.event.data["task_input"]
    agent_reasoning = ctx.event.data["agent_reasoning"]
    agent_output_resource_ids = ctx.event.data["agent_output_resource_ids"]
    
    # Load experiment and rubric
    run = await step.run("load-run", lambda: queries.runs.get(run_id))
    experiment = await step.run(
        "load-experiment",
        lambda: queries.experiments.get(run.experiment_id)
    )
    
    ground_truth = StagedRubric(**experiment.ground_truth_rubric)
    
    # Load output resources
    all_resources = await step.run("load-resources", lambda: queries.resources.get_all(run_id))
    agent_outputs = [
        r for r in all_resources
        if str(r.id) in agent_output_resource_ids
    ]
    
    # Iterate over rubric criteria
    criteria = iterate_rubric_criteria(ground_truth)
    
    # Evaluate all criteria (parallel via step.invoke)
    criterion_results = []
    for stage, rule, stage_idx, rule_idx in criteria:
        result = await step.invoke(
            inngest.Event(
                name="evaluation/criterion",
                data={
                    "run_id": str(run_id),
                    "stage": stage.model_dump(),
                    "rule": rule.model_dump(),
                    "stage_idx": stage_idx,
                    "rule_idx": rule_idx,
                    "task_input": task_input,
                    "agent_reasoning": agent_reasoning,
                    "agent_output_resource_ids": agent_output_resource_ids,
                },
            )
        )
        criterion_results.append(CriterionEvaluationResult(**result))
    
    # Rebuild into stage structure
    stage_results = _rebuild_stage_results(criterion_results, ground_truth)
    
    # Calculate aggregate scores
    aggregate = _calculate_aggregate_scores(stage_results, ground_truth)
    
    # Save to database
    # Store per-criterion results
    for cr in criterion_results:
        await step.run(
            f"store-criterion-{cr.stage_num}-{cr.criterion_num}",
            lambda c=cr: queries.criterion_results.create(
                run_id=run_id,
                stage_num=c.stage_num,
                stage_name=ground_truth.stages[c.stage_num].name,
                criterion_num=c.criterion_num,
                criterion_type=c.criterion_type,  # "code" or "llm_judge"
                criterion_description=ground_truth.stages[c.stage_num].rules[c.criterion_num].description,
                score=c.score,
                max_score=c.max_score,
                feedback=c.feedback,
                evaluated_action_ids=c.evaluated_action_ids,
                evaluated_resource_ids=c.evaluated_resource_ids,
            )
        )
    
    # Store aggregate evaluation
    await step.run(
        "store-evaluation",
        lambda: queries.evaluations.create(
            run_id=run_id,
            total_score=aggregate["total_score"],
            max_score=aggregate["max_score"],
            normalized_score=aggregate["normalized_score"],
            stages_evaluated=aggregate["stages_evaluated"],
            stages_passed=aggregate["stages_passed"],
            failed_gate=aggregate.get("failed_gate"),
        )
    )
    
    return aggregate

def _rebuild_stage_results(
    criterion_results: list[CriterionEvaluationResult],
    rubric: StagedRubric,
) -> list[dict]:
    """Rebuild criterion results into stage structure."""
    stage_results = []
    
    for stage_idx, stage in enumerate(rubric.stages):
        stage_criteria = [
            cr for cr in criterion_results
            if cr.stage_num == stage_idx
        ]
        
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
                    "evaluated_action_ids": cr.evaluated_action_ids,
                    "evaluated_resource_ids": cr.evaluated_resource_ids,
                }
                for cr in stage_criteria
            ],
        }
        stage_results.append(stage_result)
    
    return stage_results

def _calculate_aggregate_scores(
    stage_results: list[dict],
    rubric: StagedRubric,
) -> dict:
    """Calculate aggregate scores with gate logic."""
    total_score = 0.0
    stages_evaluated = 0
    stages_passed = 0
    failed_gate = None
    stopped_at = None
    
    for stage_result in stage_results:
        stages_evaluated += 1
        
        if stage_result["passed"]:
            stages_passed += 1
        
        # Check gate failure
        stage = rubric.stages[stage_result["stage_num"]]
        if not stage_result["passed"] and stage.is_required:
            failed_gate = stage.name
            
            if stage.on_failure_action == "zero_category":
                total_score = getattr(stage, "on_failure_score", 0.0)
                stopped_at = stage.name
                break
            elif stage.on_failure_action == "skip_remaining":
                stopped_at = stage.name
                break
        
        total_score += stage_result["score"]
    
    total_score = min(total_score, rubric.max_total_score)
    normalized_score = total_score / rubric.max_total_score
    
    return {
        "total_score": total_score,
        "max_score": rubric.max_total_score,
        "normalized_score": normalized_score,
        "stages_evaluated": stages_evaluated,
        "stages_passed": stages_passed,
        "failed_gate": failed_gate,
        "stopped_at": stopped_at,
    }
```

---

### 4. evaluate_criteria (Inngest Function)

```python
@inngest_client.create_function(
    fn_id="evaluate-criterion",
    trigger=inngest.TriggerEvent(event="evaluation/criterion"),
    retries=1,
)
async def evaluate_criterion_handler(
    ctx: inngest.Context,
    step: inngest.Step,
) -> dict:
    """Handle single criterion evaluation."""
    from paper_code_structure_plans.schemas.staged_rubric_schema import EvaluationStage
    from manager_agent_gym.core.agents.manager_agent.implementations.rubric_generation_manager.rubric_generation import (
        CodeRule,
        LLMJudgeRule,
    )
    
    run_id = UUID(ctx.event.data["run_id"])
    stage = EvaluationStage(**ctx.event.data["stage"])
    rule_data = ctx.event.data["rule"]
    rule = CodeRule(**rule_data) if rule_data["type"] == "code" else LLMJudgeRule(**rule_data)
    stage_idx = ctx.event.data["stage_idx"]
    rule_idx = ctx.event.data["rule_idx"]
    task_input = ctx.event.data["task_input"]
    agent_reasoning = ctx.event.data["agent_reasoning"]
    agent_output_resource_ids = ctx.event.data["agent_output_resource_ids"]
    
    # Load resources
    all_resources = await step.run("load-resources", lambda: queries.resources.get_all(run_id))
    agent_outputs = [
        r for r in all_resources
        if str(r.id) in agent_output_resource_ids
    ]
    
    # Evaluate (no sandbox needed - create temporary if code rule)
    result = await step.run(
        "evaluate-criterion",
        lambda: evaluate_criteria(
            agent_reasoning=agent_reasoning,
            agent_outputs=agent_outputs,
            stage=stage,
            rule=rule,
            stage_idx=stage_idx,
            rule_idx=rule_idx,
            task_input=task_input,
            sandbox_manager=None,  # Will create temporary if needed
        )
    )
    
    return result.model_dump()
```

---

### 5. Updated run_evaluate

```python
@inngest_client.create_function(
    fn_id="run-evaluate",
    trigger=inngest.TriggerEvent(event="execution/done"),
    retries=1,
)
async def run_evaluate(
    ctx: inngest.Context,
    step: inngest.Step,
) -> dict:
    """Evaluate execution against ground truth rubric."""
    run_id = UUID(ctx.event.data["run_id"])
    
    # Mark evaluating
    await step.run(
        "mark-evaluating",
        lambda: queries.runs.update(run_id, status="evaluating")
    )
    
    # Load state
    run = await step.run("load-run", lambda: queries.runs.get(run_id))
    experiment = await step.run(
        "load-experiment",
        lambda: queries.experiments.get(run.experiment_id)
    )
    
    # Invoke evaluation
    evaluation_result = await step.invoke(
        inngest.Event(
            name="evaluation/start",
            data={
                "run_id": str(run_id),
                "task_input": experiment.task_description,
                "agent_reasoning": run.output_text or "",
                "agent_output_resource_ids": run.output_resource_ids,
            },
        )
    )
    
    # Mark complete
    await step.run(
        "complete-run",
        lambda: queries.runs.update(
            run_id=run_id,
            status="completed",
            completed_at=datetime.utcnow(),
            final_score=evaluation_result["total_score"],
            normalized_score=evaluation_result["normalized_score"],
        )
    )
    
    return {
        "run_id": str(run_id),
        "normalized_score": evaluation_result["normalized_score"],
        "questions_asked": run.questions_asked,
    }
```

---

## Key Design Decisions

1. **Functional approach**: No bound methods on `StagedRubric` - pure functions
2. **Reuse MA-gym classes**: Use `EvaluationStage`, `CodeRule`, `LLMJudgeRule` directly - no wrapper classes
3. **Parallel evaluation**: Each criterion evaluated independently via `step.invoke`
4. **Sandbox reuse**: Code rules can use temporary sandbox or reuse run's sandbox
5. **Multimodal LLM**: LLM judges get file content as images (PDFs, Excel → images)
6. **Iterate structure**: Rubric iterated to (stage, rule, indices) tuples, then rebuilt after evaluation
7. **Gate logic**: Handled in `_calculate_aggregate_scores` after all criteria evaluated

---

## Open Questions

1. **Sandbox reuse**: Should code rule evaluation reuse the run's sandbox or create temporary?
   - **Decision**: Create temporary for now (simpler), can optimize later

2. **LLM file handling**: How to handle large files? Upload to object storage first?
   - **Decision**: Use base64 encoding for now, optimize if needed

3. **Error handling**: What if a criterion evaluation fails?
   - **Decision**: Score = 0, feedback = error message, continue with other criteria

4. **Action tracking**: How do we know which actions were evaluated?
   - **Decision**: For now, code rules can return action IDs, LLM judges evaluate all outputs

5. **Code rule signature**: What should code rules receive?
   - **Decision**: `evaluate(task_input: str, agent_reasoning: str, output_files: dict[str, bytes]) -> float | tuple[float, str]`

