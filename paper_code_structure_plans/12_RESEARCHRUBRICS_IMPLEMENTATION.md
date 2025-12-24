# ResearchRubrics Implementation Plan

## Overview

This document outlines the implementation plan for the **ResearchRubrics** benchmark - the third and final benchmark in our multi-baseline architecture. ResearchRubrics studies **adaptive stakeholder querying** using deep research tasks with weighted evaluation criteria.

**Source**: [07_MULTI_BASELINE_ARCHITECTURE.md](./07_MULTI_BASELINE_ARCHITECTURE.md) - Phase 3

## Current Status

### ✅ Common Infrastructure (Complete)

| Component | Status | Location |
|-----------|--------|----------|
| `BenchmarkName.RESEARCHRUBRICS` enum | ✅ | `core/models/enums.py` |
| `BaseStakeholder` protocol | ✅ | `core/agents/base.py` |
| `BaseToolkit` protocol | ✅ | `core/agents/base.py` |
| `BaseRubric` protocol | ✅ | `core/evaluation/base.py` |
| `LLMJudgeRule` (used by ResearchRubrics) | ✅ | `core/evaluation/rules/` |
| Registry pattern | ✅ | `benchmarks/registry.py` |
| Worker execution via Inngest | ✅ | `core/orchestration/` |
| Exploration notebook | ✅ | `notebooks/explore_researchrubrics.ipynb` |

### ❌ ResearchRubrics-Specific (To Implement)

```
benchmarks/researchrubrics/     # DOES NOT EXIST
├── __init__.py
├── schemas.py                  # ResearchRubricsTask, RubricCriterion, etc.
├── loader.py                   # Load from ScaleAI/researchrubrics
├── stakeholder.py              # RubricAwareStakeholder
├── rubric.py                   # ResearchRubricsRubric with compute_scores()
├── factories.py                # create_stakeholder, create_toolkit
├── toolkit.py                  # Exa tools wrapper
├── config.py                   # WorkerConfig
├── sandbox.py                  # SandboxManager (web access)
├── metrics.py                  # Question analysis metrics
└── skills/
    ├── __init__.py
    ├── responses.py            # ExaSearchResponse, ExaQAResponse, etc.
    ├── exa_search.py
    ├── exa_qa.py
    └── exa_get_content.py
```

## Research Design

### Research Questions (Priority Order)

1. **Do agents know WHEN to ask?** - Timing analysis of stakeholder questions
2. **Does asking improve outcomes?** - Score comparison: asked vs didn't ask  
3. **Do agents ask the RIGHT questions?** - Question-criterion relevance

### Dataset: ScaleAI/researchrubrics

- **101 tasks** across 10 domains (AI & ML, Business Planning, Historical Analysis, etc.)
- **~25 weighted criteria per task** (2,593 total criteria)
- Criteria organized by **axis type**:

| Axis | % of Criteria | Research Relevance |
|------|---------------|-------------------|
| **Implicit Criteria** | 39.4% | Key target - agent can't know without asking |
| **Explicit Criteria** | 27.7% | In prompt, should survive ablation |
| Synthesis of Information | 15.8% | Quality of reasoning |
| Communication Quality | 7.8% | Style/format preferences |
| Instruction Following | 5.8% | Format constraints |
| References & Citation Quality | 3.5% | Source quality |

### Ablation Strategy

Prompts are **ablated** (manually with QA) to:
- Remove context that specifies preferences
- Create uncertainty requiring stakeholder querying
- Preserve enough structure for rubric evaluation

**Stakeholder Design**:
- Knows: rubric criteria + original (unablated) question
- Answers based on rubric criteria when relevant
- Responds "I don't have a preference on that" for out-of-scope questions

---

## Implementation Phases

### Phase 1: Schemas & Data Loading

**Goal**: Load ResearchRubrics dataset into database

#### 1.1 Create Schemas (`benchmarks/researchrubrics/schemas.py`)

```python
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
    weight: float = Field(description="Criterion weight (can be negative)")


class ResearchRubricsTask(BaseModel):
    """Parsed ResearchRubrics task from HuggingFace."""
    sample_id: str
    domain: str
    original_prompt: str
    rubrics: list[RubricCriterion]


class AblatedPrompt(BaseModel):
    """An ablated prompt for a ResearchRubrics task."""
    sample_id: str
    ablated_prompt: str
    ablation_type: Literal["preference_removal", "scope_removal", "full"] = "preference_removal"
    removed_elements: list[str] | None = None
```

#### 1.2 Create Loader (`benchmarks/researchrubrics/loader.py`)

```python
from datasets import load_dataset
from h_arcane.benchmarks.researchrubrics.schemas import ResearchRubricsTask, RubricCriterion

def load_researchrubrics_to_database(
    num_examples: int | None = None,
    drop_old_results: bool = False,
    ablated_dataset_name: str | None = None,
) -> int:
    """
    Load ResearchRubrics from HuggingFace ablated dataset into database.
    
    The ablated dataset is a superset containing:
    - All original fields (sample_id, domain, prompt, rubrics, etc.)
    - Ablated prompts (ablated_prompt, ablation_type, removed_elements)
    
    Args:
        num_examples: Limit number of examples to load (None = all)
        drop_old_results: Whether to drop existing experiments first
        ablated_dataset_name: HuggingFace dataset name for ablated dataset
                             (e.g., "{username}/researchrubrics-ablated")
                             If None, attempts to auto-detect from HuggingFace credentials
    """
    # Load ablated dataset (superset - contains everything)
    if ablated_dataset_name is None:
        # Auto-detect from HuggingFace credentials
        from huggingface_hub import HfApi
        api = HfApi()
        user_info = api.whoami()
        username = user_info["name"]
        ablated_dataset_name = f"{username}/researchrubrics-ablated"
    
    ds = load_dataset(ablated_dataset_name)["train"]
    
    # Parse and create Experiment records
    # For each task:
    #   - task_description = ablated_prompt (what worker sees)
    #   - ground_truth_rubric = ResearchRubricsRubric with criteria from rubrics field
    #   - benchmark_specific_data = {
    #       "domain": domain,
    #       "ablation_type": ablation_type,
    #       "removed_elements": removed_elements
    #     }  # Metadata only - stakeholder gets ablated prompt + rubrics
    ...
```

**Data Source**:
- **Ablated dataset**: `{username}/researchrubrics-ablated` from HuggingFace (superset containing original data + ablated prompts)

**Loader Logic**:
1. Load ablated dataset (contains all fields: rubrics, original prompt, ablated prompt)
2. For each row:
   - `task_description` = `ablated_prompt` (what worker and stakeholder see)
   - `ground_truth_rubric` = `ResearchRubricsRubric` with criteria from `rubrics` field (stakeholder uses this to express preferences)
   - `benchmark_specific_data` = metadata only (`domain`, `ablation_type`, `removed_elements`) for analysis

#### 1.3 Tasks

- [ ] Create `benchmarks/researchrubrics/__init__.py`
- [ ] Create `benchmarks/researchrubrics/schemas.py` with models above
- [ ] Create `benchmarks/researchrubrics/loader.py`
- [ ] Load from ablated HuggingFace dataset (superset - contains all data)
- [ ] Extract `ablated_prompt` for `task_description` (what worker and stakeholder see)
- [ ] Extract `rubrics` for `ground_truth_rubric` (stakeholder uses to express preferences)
- [ ] Extract metadata (`domain`, `ablation_type`, `removed_elements`) for `benchmark_specific_data`
- [ ] Store in database with `benchmark_name=RESEARCHRUBRICS`

**Note**: Requires HuggingFace credentials (`huggingface-cli login`) to auto-detect ablated dataset name. Alternatively, pass `ablated_dataset_name` parameter explicitly.

---

### Phase 2: Rubric & Evaluation

**Goal**: Implement `ResearchRubricsRubric` with `compute_scores()`

#### 2.1 Create Rubric (`benchmarks/researchrubrics/rubric.py`)

```python
from typing import Literal
import inngest
from pydantic import BaseModel, Field

from h_arcane.core.db.models import TaskEvaluationResult
from h_arcane.core.evaluation.rules import LLMJudgeRule
from h_arcane.benchmarks.researchrubrics.schemas import RubricCriterion


class ResearchRubricsRubric(BaseModel):
    """ResearchRubrics rubric for weighted criteria evaluation."""
    
    benchmark: Literal["researchrubrics"] = "researchrubrics"
    criteria: list[RubricCriterion]
    
    async def compute_scores(
        self,
        context: "TaskEvaluationContext",
        inngest_ctx: inngest.Context,
    ) -> TaskEvaluationResult:
        """
        Evaluate research output against weighted criteria.
        
        Uses LLMJudgeRule for each criterion, aggregates weighted scores.
        
        Process:
        1. Convert each RubricCriterion to LLMJudgeRule with judge prompt
        2. Create CriterionEvaluationEvent for each criterion
        3. Evaluate all criteria in parallel via Inngest steps
        4. Aggregate: weighted sum of scores (criterion.weight * score)
        5. Return TaskEvaluationResult
        """
        # Import here to avoid circular imports
        from h_arcane.core.orchestration.criteria_evaluator import evaluate_criterion_fn
        from h_arcane.core.orchestration.events import CriterionEvaluationEvent
        from h_arcane.core.evaluation.rules import LLMJudgeRule
        
        # Step 1: Convert RubricCriterion to LLMJudgeRule
        async def convert_criteria_step():
            """Convert criteria to LLMJudgeRule objects with judge prompts."""
            llm_rules = []
            for idx, criterion in enumerate(self.criteria):
                # Build judge prompt for this criterion
                judge_prompt = self._build_judge_prompt(criterion)
                
                # Create LLMJudgeRule
                llm_rule = LLMJudgeRule(
                    description=criterion.criterion,
                    judge_prompt=judge_prompt,
                    expectation=None,  # Criterion text is self-explanatory
                    axis=criterion.axis,
                )
                llm_rules.append((idx, criterion, llm_rule))
            return llm_rules
        
        criteria_with_rules = await inngest_ctx.step.run(
            "convert-criteria-to-rules",
            convert_criteria_step,
        )
        
        # Step 2: Create parallel invokers for each criterion
        def make_criterion_invoker(
            criterion_idx: int,
            criterion: RubricCriterion,
            llm_rule: LLMJudgeRule,
        ):
            """Create an invoker for evaluating a single criterion."""
            step_id = f"criterion-{criterion_idx}"
            # Max score is the criterion weight (can be negative!)
            max_score = criterion.weight
            
            # Build event data
            event_data = CriterionEvaluationEvent(
                run_id=str(context.run_id),
                task_input=context.task_input,
                agent_reasoning=context.agent_reasoning,
                agent_outputs=context.agent_outputs,
                stage_name=f"Criterion-{criterion_idx}",  # No stages in ResearchRubrics
                stage_idx=0,  # All criteria at same level
                rule_idx=criterion_idx,
                max_score=max_score,
                rule=llm_rule,  # Pydantic handles serialization
            )
            event_data_dict = event_data.model_dump(mode="json")
            
            # Return lambda that invokes the generic criterion evaluator
            return (
                lambda ctx_ref=inngest_ctx, sid=step_id, data=event_data_dict: ctx_ref.step.invoke(
                    step_id=sid,
                    function=evaluate_criterion_fn,
                    data=data,
                )
            )
        
        # Build list of parallel invokers
        parallel_invokers = tuple(
            make_criterion_invoker(idx, criterion, llm_rule)
            for idx, criterion, llm_rule in criteria_with_rules
        )
        
        # Step 3: Execute ALL criteria in parallel
        criterion_results_tuple = await inngest_ctx.group.parallel(parallel_invokers)
        criterion_results = list(criterion_results_tuple)
        
        # Step 4: Aggregate weighted scores
        async def aggregate_scores_step():
            """Calculate weighted sum of scores."""
            total_score = 0.0
            max_possible_score = 0.0  # Sum of positive weights
            min_possible_score = 0.0  # Sum of negative weights
            
            for idx, (_, criterion, _) in enumerate(criteria_with_rules):
                result = criterion_results[idx]
                # Weighted score: criterion.weight * (score / max_score)
                # Since max_score = criterion.weight, this simplifies to just score
                # But we need to handle the case where weight != max_score
                if result.max_score != 0:
                    weighted_score = (result.score / result.max_score) * criterion.weight
                else:
                    weighted_score = 0.0
                
                total_score += weighted_score
                
                # Track possible score range
                if criterion.weight > 0:
                    max_possible_score += criterion.weight
                else:
                    min_possible_score += criterion.weight
            
            # Normalized score: (total - min) / (max - min) if range > 0
            score_range = max_possible_score - min_possible_score
            if score_range > 0:
                normalized_score = (total_score - min_possible_score) / score_range
            else:
                normalized_score = 0.0
            
            return {
                "total_score": total_score,
                "max_score": max_possible_score,
                "min_score": min_possible_score,
                "normalized_score": normalized_score,
            }
        
        aggregate = await inngest_ctx.step.run(
            "aggregate-weighted-scores",
            aggregate_scores_step,
        )
        
        # Convert CriterionResult objects to dicts for JSON storage
        criterion_results_dicts = [cr.model_dump() if hasattr(cr, 'model_dump') else cr for cr in criterion_results]
        
        return TaskEvaluationResult(
            run_id=context.run_id,
            criterion_results=criterion_results_dicts,
            total_score=aggregate["total_score"],
            max_score=aggregate["max_score"],
            normalized_score=aggregate["normalized_score"],
            stages_evaluated=1,  # All criteria evaluated
            stages_passed=1 if aggregate["total_score"] > 0 else 0,
            failed_gate=None,  # No gate logic in ResearchRubrics
        )
    
    def _build_judge_prompt(self, criterion: RubricCriterion) -> str:
        """
        Build judge prompt for evaluating a single criterion.
        
        Args:
            criterion: The RubricCriterion to build a prompt for
        
        Returns:
            System prompt for the LLM judge
        """
        axis_context = f"\n\nThis criterion belongs to the '{criterion.axis}' axis." if criterion.axis else ""
        weight_note = f"\n\nWeight: {criterion.weight}" if criterion.weight != 1.0 else ""
        
        return f"""You are an expert evaluator assessing research reports against specific criteria.

Your task is to evaluate whether a research report meets this criterion:
{criterion.criterion}{axis_context}{weight_note}

You will be given:
- The original task/request given to the researcher
- The researcher's reasoning and thought process
- The final research report/output

Evaluate whether the output meets this criterion. Provide:
1. Detailed reasoning explaining your decision, citing specific evidence from the task input, researcher reasoning, and outputs
2. A binary verdict: True if the criterion is met, False otherwise

This is a pass/fail decision. The criterion is either satisfied (True) or not satisfied (False).
Be thorough but fair in your evaluation."""
```

#### 2.2 Update Types (`benchmarks/types.py`)

Add `ResearchRubricsRubric` to `AnyRubric` union:

```python
from h_arcane.benchmarks.researchrubrics.rubric import ResearchRubricsRubric

AnyRubric = Annotated[
    Union[StagedRubric, MiniF2FRubric, ResearchRubricsRubric],
    Field(discriminator="benchmark"),
]
```

#### 2.3 Implementation Details

**Criterion Evaluation Flow**:
1. **Convert Criteria**: Each `RubricCriterion` → `LLMJudgeRule` with:
   - `description` = `criterion.criterion` (the criterion text)
   - `judge_prompt` = Built via `_build_judge_prompt()` method
   - `axis` = `criterion.axis` (for analysis)
   - `expectation` = None (criterion text is self-explanatory)

2. **Parallel Evaluation**: All criteria evaluated in parallel via `inngest_ctx.group.parallel()`:
   - Each criterion invokes `evaluate_criterion_fn` (generic Inngest function)
   - Uses `CriterionEvaluationEvent` with `rule=LLMJudgeRule`
   - Returns `CriterionResult` with score (0 or max_score) and feedback

3. **Weighted Aggregation**:
   - Each criterion has a `weight` (can be positive or negative)
   - Score calculation: `(result.score / result.max_score) * criterion.weight`
   - Since `max_score = criterion.weight`, this simplifies to just `result.score`
   - Total score = sum of all weighted scores
   - Normalized score = `(total - min_possible) / (max_possible - min_possible)`
   - `min_possible` = sum of negative weights
   - `max_possible` = sum of positive weights

4. **Judge Prompt Structure**:
   - Includes criterion text
   - Includes axis context (if present)
   - Includes weight note (if weight != 1.0)
   - Instructions for binary verdict (True/False)

**Key Differences from GDPEval**:
- No staged evaluation (all criteria at same level)
- Weighted scoring (weights can be negative)
- No gate logic (all criteria evaluated regardless)
- Simpler aggregation (weighted sum, not stage-based)

#### 2.4 Tasks

- [ ] Create `benchmarks/researchrubrics/rubric.py`
- [ ] Implement `compute_scores()` method with:
  - [ ] `convert_criteria_step()` to convert `RubricCriterion` → `LLMJudgeRule`
  - [ ] `make_criterion_invoker()` to create Inngest invokers
  - [ ] Parallel evaluation via `inngest_ctx.group.parallel()`
  - [ ] `aggregate_scores_step()` for weighted score calculation
  - [ ] `_build_judge_prompt()` helper method
- [ ] Add to `AnyRubric` union in `benchmarks/types.py`
- [ ] Test with sample criteria to verify:
  - [ ] Judge prompts are correctly formatted
  - [ ] Parallel evaluation works
  - [ ] Weighted aggregation handles negative weights correctly
  - [ ] Normalized score calculation is correct

---

### Phase 3: Stakeholder

**Goal**: Implement `RubricAwareStakeholder`

#### 3.1 Create Stakeholder (`benchmarks/researchrubrics/stakeholder.py`)

```python
class RubricAwareStakeholder(BaseStakeholder):
    """
    Stakeholder that knows rubric criteria + ablated prompt.
    
    Behavior:
    - Answers based on what rubric criteria expect
    - Doesn't reveal full rubric, just answers questions naturally
    - Responds "I don't have a preference" for out-of-scope questions
    """
    
    def __init__(self, experiment: Experiment):
        self._model = "gpt-4o"
        # Get ablated prompt from task_description (what worker sees)
        self._task_prompt = experiment.task_description
        # Get rubric criteria from ground_truth_rubric
        self._rubric_criteria = experiment.ground_truth_rubric["criteria"]
        
    @property
    def model(self) -> str:
        return self._model
    
    @property
    def system_prompt(self) -> str:
        return f"""You are a stakeholder who commissioned a research report.

You know exactly what you want based on these evaluation criteria:
{self._format_criteria()}

When the researcher asks questions:
- Answer based on what the criteria expect
- Be helpful but don't reveal the full rubric
- Say "I don't have a preference on that" for unrelated questions

Research request: {self._task_prompt}
"""
    
    async def answer(self, question: str) -> str:
        # LLM call to answer based on criteria
        ...
```

#### 3.2 Tasks

- [ ] Create `benchmarks/researchrubrics/stakeholder.py`
- [ ] Implement `RubricAwareStakeholder`
- [ ] Add guardrails to prevent leaking full rubric
- [ ] Handle "out of scope" questions gracefully

---

### Phase 4: Web Research Tools (Exa)

**Goal**: Implement Exa API tools for web research

#### 4.1 Add Settings

```python
# h_arcane/settings.py
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Exa API
    exa_api_key: str = ""
    
    # ... rest of settings ...
```

#### 4.2 Create Tool Responses (`benchmarks/researchrubrics/skills/responses.py`)

```python
from pydantic import BaseModel, Field


class ExaSearchResult(BaseModel):
    """Single search result from Exa."""
    title: str = Field(description="Page title")
    url: str = Field(description="Page URL")
    summary: str | None = Field(default=None, description="Summary/snippet of the page")
    content: str | None = Field(default=None, description="Extracted text content (truncated)")
    published_date: str | None = Field(default=None, description="Publication date if available")


class ExaSearchResponse(BaseModel):
    """Response from exa_search skill."""
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    query: str | None = Field(default=None, description="The search query that was executed")
    results: list[ExaSearchResult] | None = Field(default=None, description="List of search results")


class ExaQAResponse(BaseModel):
    """Response from exa_qa skill."""
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    question: str | None = Field(default=None, description="The question that was asked")
    answer: str | None = Field(default=None, description="The answer extracted from sources")
    sources: list[dict[str, str]] | None = Field(
        default=None, 
        description="List of source dicts with 'url' and 'title' keys"
    )


class ExaGetContentResponse(BaseModel):
    """Response from exa_get_content skill."""
    success: bool = Field(description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if operation failed")
    url: str | None = Field(default=None, description="URL that was fetched")
    title: str | None = Field(default=None, description="Page title")
    content: str | None = Field(default=None, description="Full extracted text content")
    published_date: str | None = Field(default=None, description="Publication date if available")
```

#### 4.3 Create Exa Client Module (`benchmarks/researchrubrics/skills/exa_client.py`)

```python
"""Shared Exa client for all Exa-based skills."""

from exa_py import Exa
from h_arcane.settings import settings

# Initialize Exa client once, reuse across skills
EXA_CLIENT = Exa(api_key=settings.exa_api_key)
```

#### 4.4 Create Exa Search Tool (`benchmarks/researchrubrics/skills/exa_search.py`)

```python
"""Exa web search skill - searches the web and returns ranked results with content."""

from .exa_client import EXA_CLIENT
from .responses import ExaSearchResponse, ExaSearchResult


async def main(
    query: str,
    num_results: int = 5,
    category: str | None = None,
) -> ExaSearchResponse:
    """
    Search the web using Exa to get ranked search results with content.
    
    Args:
        query: Search query string
        num_results: Number of results to return (default: 5, max recommended: 10)
        category: Optional content category filter (e.g., "news", "academic", "company")
    
    Returns:
        ExaSearchResponse with search results including titles, URLs, summaries, and content
    """
    try:
        if not query or not query.strip():
            return ExaSearchResponse(
                success=False,
                error="Query cannot be empty",
            )
        
        # Use search_and_contents to get both metadata and text content
        response = EXA_CLIENT.search_and_contents(
            query,
            type="auto",  # Auto-detect best search type
            text=True,    # Include text content
            num_results=num_results,
            summary=True, # Include summaries
            category=category if category else None,
        )
        
        results = [
            ExaSearchResult(
                title=result.title or "Untitled",
                url=result.url,
                summary=result.summary,
                # Truncate content to avoid huge responses (first 5000 chars)
                content=result.text[:5000] if result.text else None,
                published_date=result.published_date,
            )
            for result in response.results
        ]
        
        return ExaSearchResponse(
            success=True,
            query=query,
            results=results,
        )
        
    except Exception as e:
        return ExaSearchResponse(
            success=False,
            error=f"Error searching with Exa: {str(e)}",
        )
```

#### 4.5 Create Exa QA Tool (`benchmarks/researchrubrics/skills/exa_qa.py`)

```python
"""Exa QA skill - gets direct answers to questions from web sources."""

from .exa_client import EXA_CLIENT
from .responses import ExaQAResponse


async def main(question: str, num_results: int = 3) -> ExaQAResponse:
    """
    Get direct answers to questions using Exa's neural search capabilities.
    
    Uses Exa's "neural" search type optimized for question-answering.
    Returns the best answer from top sources.
    
    Args:
        question: Question to answer
        num_results: Number of sources to use for answering (default: 3)
    
    Returns:
        ExaQAResponse with answer and source citations
    """
    try:
        if not question or not question.strip():
            return ExaQAResponse(
                success=False,
                error="Question cannot be empty",
            )
        
        # Use neural search type optimized for Q&A
        response = EXA_CLIENT.search_and_contents(
            question,
            type="neural",  # Neural search for better Q&A
            text=True,
            num_results=num_results,
            summary=True,  # Get summaries which often contain answers
        )
        
        if not response.results:
            return ExaQAResponse(
                success=True,
                question=question,
                answer="No answer found for this question.",
                sources=[],
            )
        
        # Use the summary from the top result as the answer
        # Summaries from neural search are often direct answers
        top_result = response.results[0]
        answer = top_result.summary or top_result.text[:500] if top_result.text else "No answer found."
        
        # Collect all sources for citation
        sources = [
            {"url": result.url, "title": result.title or "Untitled"}
            for result in response.results
        ]
        
        return ExaQAResponse(
            success=True,
            question=question,
            answer=answer,
            sources=sources,
        )
        
    except Exception as e:
        return ExaQAResponse(
            success=False,
            error=f"Error getting answer with Exa: {str(e)}",
        )
```

#### 4.6 Create Exa Get Content Tool (`benchmarks/researchrubrics/skills/exa_get_content.py`)

```python
"""Exa get content skill - extracts full content from a URL."""

from .exa_client import EXA_CLIENT
from .responses import ExaGetContentResponse


async def main(url: str) -> ExaGetContentResponse:
    """
    Extract full content from a URL using Exa.
    
    Args:
        url: URL to extract content from
    
    Returns:
        ExaGetContentResponse with extracted content, title, and metadata
    """
    try:
        if not url or not url.strip():
            return ExaGetContentResponse(
                success=False,
                error="URL cannot be empty",
            )
        
        # Validate URL format (basic check)
        if not url.startswith(("http://", "https://")):
            return ExaGetContentResponse(
                success=False,
                error=f"Invalid URL format: {url}",
            )
        
        # Get contents for the URL
        response = EXA_CLIENT.get_contents(
            [url],
            text=True,  # Include full text content
        )
        
        if not response.results:
            return ExaGetContentResponse(
                success=False,
                error=f"No content found for URL: {url}",
            )
        
        result = response.results[0]
        
        return ExaGetContentResponse(
            success=True,
            url=url,
            title=result.title,
            content=result.text,  # Full text content
            published_date=result.published_date,
        )
        
    except Exception as e:
        return ExaGetContentResponse(
            success=False,
            error=f"Error extracting content from URL: {str(e)}",
        )
```

#### 4.7 Create Skills Init (`benchmarks/researchrubrics/skills/__init__.py`)

```python
"""ResearchRubrics skills exports."""

from .exa_search import main as exa_search
from .exa_qa import main as exa_qa
from .exa_get_content import main as exa_get_content

__all__ = ["exa_search", "exa_qa", "exa_get_content"]
```

#### 4.8 Implementation Details

**Error Handling**:
- All tools wrap API calls in try/except blocks
- Return `success=False` with error message on failure
- Validate inputs (non-empty strings, URL format, etc.)

**Content Truncation**:
- `exa_search`: Truncates content to 5000 chars per result to avoid huge responses
- `exa_get_content`: Returns full content (no truncation) since it's a single URL
- `exa_qa`: Uses summary or first 500 chars of text as answer

**API Usage**:
- `exa_search`: Uses `search_and_contents()` with `type="auto"` for general search
- `exa_qa`: Uses `search_and_contents()` with `type="neural"` for Q&A optimization
- `exa_get_content`: Uses `get_contents()` for single URL extraction

**Client Initialization**:
- Shared `EXA_CLIENT` in `exa_client.py` module
- Initialized once with `settings.exa_api_key`
- Imported by all three skill modules

#### 4.9 Tasks

- [ ] Add `exa_api_key: str = ""` to `h_arcane/settings.py`
- [ ] Add `exa-py = "^1.0.0"` to `pyproject.toml` dependencies
- [ ] Create `benchmarks/researchrubrics/skills/__init__.py`
- [ ] Create `benchmarks/researchrubrics/skills/exa_client.py` with shared client
- [ ] Create `benchmarks/researchrubrics/skills/responses.py` with all response models
- [ ] Create `benchmarks/researchrubrics/skills/exa_search.py` with `main()` function
- [ ] Create `benchmarks/researchrubrics/skills/exa_qa.py` with `main()` function
- [ ] Create `benchmarks/researchrubrics/skills/exa_get_content.py` with `main()` function
- [ ] Test each tool with sample inputs
- [ ] Verify error handling for invalid inputs and API failures

---

### Phase 5: Toolkit & Config

**Goal**: Wire up toolkit and worker config

#### 5.1 Create Config (`benchmarks/researchrubrics/config.py`)

```python
from h_arcane.benchmarks.common.workers.config import WorkerConfig

RESEARCHRUBRICS_CONFIG = WorkerConfig(
    system_prompt="""You are a deep research assistant producing comprehensive research reports.

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
    max_iterations=30,
    max_questions=10,
)
```

#### 5.2 Create Toolkit (`benchmarks/researchrubrics/toolkit.py`)

Follow pattern from `gdpeval/toolkit.py` and `minif2f/toolkit.py`.

#### 5.3 Create Factories (`benchmarks/researchrubrics/factories.py`)

```python
def create_stakeholder(experiment: Experiment) -> RubricAwareStakeholder:
    return RubricAwareStakeholder(experiment)

def create_toolkit(
    run_id: UUID,
    stakeholder: BaseStakeholder,
    sandbox: BaseSandbox,
    max_questions: int,
) -> ResearchRubricsToolkit:
    return ResearchRubricsToolkit(run_id, stakeholder, sandbox, max_questions)
```

#### 5.4 Create Sandbox (`benchmarks/researchrubrics/sandbox.py`)

```python
class ResearchRubricsSandboxManager(BaseSandboxManager):
    """Sandbox manager for ResearchRubrics with web access."""
    
    async def _install_dependencies(self, sandbox: Sandbox) -> None:
        # Install exa-py or other dependencies
        await sandbox.run_code("pip install exa-py", language="bash")
```

#### 5.5 Update Registry (`benchmarks/registry.py`)

```python
from h_arcane.benchmarks.researchrubrics.config import RESEARCHRUBRICS_CONFIG
from h_arcane.benchmarks.researchrubrics.loader import load_researchrubrics_to_database
from h_arcane.benchmarks.researchrubrics.factories import (
    create_stakeholder as rr_create_stakeholder,
    create_toolkit as rr_create_toolkit,
)
from h_arcane.benchmarks.researchrubrics.sandbox import ResearchRubricsSandboxManager

BENCHMARK_CONFIGS: dict[BenchmarkName, BenchmarkConfig] = {
    ...
    BenchmarkName.RESEARCHRUBRICS: {
        "config": RESEARCHRUBRICS_CONFIG,
        "skills_dir": _BENCHMARKS_DIR / "researchrubrics" / "skills",
        "loader": load_researchrubrics_to_database,
        "stakeholder_factory": rr_create_stakeholder,
        "toolkit_factory": rr_create_toolkit,
        "sandbox_manager_class": ResearchRubricsSandboxManager,
    },
}
```

#### 5.6 Tasks

- [ ] Create `benchmarks/researchrubrics/config.py`
- [ ] Create `benchmarks/researchrubrics/toolkit.py`
- [ ] Create `benchmarks/researchrubrics/factories.py`
- [ ] Create `benchmarks/researchrubrics/sandbox.py`
- [ ] Add to `BENCHMARK_CONFIGS` in registry

---

### Phase 6: Metrics & Analysis (Optional)

**Goal**: Implement research-specific metrics

#### 6.1 Create Metrics (`benchmarks/researchrubrics/metrics.py`)

```python
class ResearchRubricsMetrics:
    """Per-run and aggregate metrics for research analysis."""
    
    @staticmethod
    def question_timing(run: Run) -> dict:
        """Categorize questions as early/mid/late."""
        ...
    
    @staticmethod
    def question_criterion_match(run: Run, rubric: list[RubricCriterion]) -> float:
        """Embed questions → match to criteria → sum weights."""
        ...
    
    @staticmethod
    def score_by_axis(result: TaskEvaluationResult) -> dict[str, float]:
        """Break down scores by axis type."""
        ...
```

#### 6.2 Tasks

- [ ] Create `benchmarks/researchrubrics/metrics.py`
- [ ] Implement question timing analysis
- [ ] Implement question-criterion matching (embeddings)
- [ ] Implement score breakdown by axis

---

### Phase 7: Data Preparation ✅ COMPLETE

**Status**: Ablated dataset already created and uploaded to HuggingFace

The ablated prompts dataset has been created via `notebooks/ablate_researchrubrics.ipynb` and uploaded to HuggingFace as `{username}/researchrubrics-ablated`.

**Dataset Structure**:
- Each row contains: `sample_id`, `ablated_prompt`, `ablation_type`, `removed_elements`
- Matches `sample_id` from original `ScaleAI/researchrubrics` dataset
- Loaded automatically in Phase 1 loader

**No action needed** - dataset is ready for use.

---

## File Summary

| Phase | Action | File |
|-------|--------|------|
| 1 | Create | `benchmarks/researchrubrics/__init__.py` |
| 1 | Create | `benchmarks/researchrubrics/schemas.py` |
| 1 | Create | `benchmarks/researchrubrics/loader.py` |
| 2 | Create | `benchmarks/researchrubrics/rubric.py` |
| 2 | Modify | `benchmarks/types.py` (add ResearchRubricsRubric to AnyRubric) |
| 3 | Create | `benchmarks/researchrubrics/stakeholder.py` |
| 4 | Modify | `h_arcane/settings.py` (add exa_api_key) |
| 4 | Modify | `pyproject.toml` (add exa-py) |
| 4 | Create | `benchmarks/researchrubrics/skills/__init__.py` |
| 4 | Create | `benchmarks/researchrubrics/skills/responses.py` |
| 4 | Create | `benchmarks/researchrubrics/skills/exa_search.py` |
| 4 | Create | `benchmarks/researchrubrics/skills/exa_qa.py` |
| 4 | Create | `benchmarks/researchrubrics/skills/exa_get_content.py` |
| 5 | Create | `benchmarks/researchrubrics/config.py` |
| 5 | Create | `benchmarks/researchrubrics/toolkit.py` |
| 5 | Create | `benchmarks/researchrubrics/factories.py` |
| 5 | Create | `benchmarks/researchrubrics/sandbox.py` |
| 5 | Modify | `benchmarks/registry.py` |
| 6 | Create | `benchmarks/researchrubrics/metrics.py` |
| 7 | ✅ Complete | Ablated dataset already on HuggingFace |

---

## Validation Checklist

- [ ] `python -c "from h_arcane.benchmarks.researchrubrics import *"` works
- [ ] `pyright h_arcane/benchmarks/researchrubrics/` passes
- [ ] Loader creates experiments in database
- [ ] Stakeholder answers questions appropriately
- [ ] Exa tools return proper responses
- [ ] `compute_scores()` evaluates all criteria
- [ ] End-to-end run: `python scripts/run_experiments.py --benchmark researchrubrics --num-examples 1`

---

## Dependencies

```toml
# pyproject.toml additions
[project.dependencies]
exa-py = "^1.0.0"
datasets = "^2.0.0"  # If not already present
huggingface_hub = "^0.20.0"  # For auto-detecting ablated dataset name
```

**Note**: `huggingface_hub` is needed for auto-detecting the ablated dataset name from logged-in credentials. If not using auto-detection, only `datasets` is required.

---

## Timeline Estimate

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 1: Schemas & Loading | 2-3 hours | None |
| Phase 2: Rubric & Evaluation | 3-4 hours | Phase 1 |
| Phase 3: Stakeholder | 2-3 hours | Phase 1 |
| Phase 4: Exa Tools | 3-4 hours | None (can parallel) |
| Phase 5: Toolkit & Config | 2-3 hours | Phases 1-4 |
| Phase 6: Metrics | 2-3 hours | Phase 5 |
| Phase 7: Data Prep | ✅ Complete | Already on HuggingFace |

**Total: ~1-2 days** (data preparation already complete)

