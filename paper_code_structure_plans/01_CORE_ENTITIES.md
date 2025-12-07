# Core Entities & Database Schema

Domain models and database tables for the H-ARCANE experiment framework.

All entities are defined using SQLModel (SQLAlchemy + Pydantic), providing both database persistence and Pydantic validation.

**Scope: ReAct Baseline Only**

**7 tables total** — minimal schema for research experiments.

---

## Table of Contents

1. [Database Tables](#database-tables)
   - [Experiment & Run](#experiment--run)
   - [Messages](#messages)
   - [Actions](#actions)
   - [Resources](#resources)
   - [Evaluations](#evaluations)
2. [Domain Logic](#domain-logic)
   - [Worker Agent](#worker-agent)
   - [Stakeholder](#stakeholder)
   - [Helper Functions](#helper-functions)
3. [Database Queries](#database-queries)

---

## Database Tables

### Experiment & Run

#### Experiment

GDPEval tasks with their ground truth rubrics.

```python
from sqlmodel import SQLModel, Field, Column, Index
from sqlalchemy import JSON
from uuid import UUID, uuid4
from datetime import datetime

class Experiment(SQLModel, table=True):
    """A GDPEval task with ground truth rubric."""
    __tablename__ = "experiments"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    gdpeval_task_id: str = Field(index=True, unique=True)
    
    # Task definition
    task_description: str
    
    # Ground truth rubric (stored as JSON, loaded as StagedRubric)
    ground_truth_rubric: dict = Field(sa_column=Column(JSON))
    
    # Metadata
    category: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**Note**: Input files are stored as Resource records with `experiment_id` set (not as JSON). Query with `queries.resources.get_by_experiment(experiment_id)`.

**Note**: `ground_truth_rubric` stored as JSON in DB, loaded as `StagedRubric`:

```python
from paper_code_structure_plans.schemas.staged_rubric_schema import StagedRubric

def get_rubric(experiment: Experiment) -> StagedRubric:
    return StagedRubric(**experiment.ground_truth_rubric)
```

#### Run

A single execution of an experiment. Contains the output directly.

```python
from enum import Enum

class RunStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"

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
    output_text: str | None = None  # Quick text summary/output
    output_resource_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON)
    )  # UUIDs of output resources (files or text stored as resources)
    
    # Results (populated on completion, derived from messages/actions)
    final_score: float | None = None
    normalized_score: float | None = None
    questions_asked: int | None = None
    
    __table_args__ = (
        Index("ix_runs_experiment", "experiment_id"),
        Index("ix_runs_status", "status"),
    )
```

---

### Messages

Worker ↔ Stakeholder communication.

```python
class MessageRole(str, Enum):
    WORKER = "worker"
    STAKEHOLDER = "stakeholder"

class Message(SQLModel, table=True):
    """A message in the run's conversation history."""
    __tablename__ = "messages"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    
    # Core content
    sender: MessageRole
    content: str
    sequence_num: int  # 0, 1, 2, ...
    
    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Metadata
    tokens: int | None = None
    cost_usd: float | None = None
    
    __table_args__ = (
        Index("ix_messages_run_seq", "run_id", "sequence_num"),
    )
```

---

### Actions

Flattened trace of tool calls during execution. Each row = one tool call.

```python
class Action(SQLModel, table=True):
    """A single action in the worker's execution trace."""
    __tablename__ = "actions"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    
    # Ordering
    action_num: int  # 0, 1, 2, ...
    
    # Action details
    action_type: str  # Tool name: "ask_stakeholder", "read_pdf", etc.
    input: str  # Tool input (JSON or text)
    output: str | None = None  # Tool output
    
    # Timing
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    duration_ms: int | None = None
    
    # Cost
    tokens: int | None = None
    cost_usd: float | None = None
    
    __table_args__ = (
        Index("ix_actions_run_num", "run_id", "action_num"),
        Index("ix_actions_run_type", "run_id", "action_type"),
    )
```

**Note**: `action_type` is a string, not an enum. Tool names come from the GDPEval toolkit dynamically.

---

### Resources

Files associated with experiments and runs.

**Note**: 
- **Input files**: Stored as Resource records with `experiment_id` set (not `run_id`)
- **Output files**: Stored as Resource records with `run_id` set (generated by worker)

```python
class Resource(SQLModel, table=True):
    """A file resource (input or output)."""
    __tablename__ = "resources"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # Association: either experiment_id (input) or run_id (output)
    experiment_id: UUID | None = Field(foreign_key="experiments.id", index=True, default=None)
    run_id: UUID | None = Field(foreign_key="runs.id", index=True, default=None)
    
    # File info
    name: str
    mime_type: str
    file_path: str
    size_bytes: int
    
    preview_text: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_resources_experiment", "experiment_id"),
        Index("ix_resources_run", "run_id"),
        # Constraint: exactly one of experiment_id or run_id must be set
        # (enforced at application level or via CHECK constraint)
    )
```

**Note**: 
- **Input resources**: `experiment_id` set, `run_id=None` (created when experiment is loaded)
- **Output resources**: `run_id` set, `experiment_id=None` (created by worker during execution)
- Use `queries.resources.get_by_experiment(experiment_id)` for input files
- Use `queries.resources.get_by_run(run_id)` for output files

---

### Evaluations

#### Evaluation

Aggregate evaluation scores for a run.

```python
class Evaluation(SQLModel, table=True):
    """Aggregate evaluation result for a run."""
    __tablename__ = "evaluations"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True, unique=True)
    
    # Aggregate scores
    total_score: float
    max_score: float
    normalized_score: float
    
    # Stage summary
    stages_evaluated: int
    stages_passed: int
    failed_gate: str | None = None  # First required stage that failed
    
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
```

#### CriterionResult

Per-criterion evaluation results. One row per (run, stage, criterion).

```python
class CriterionResult(SQLModel, table=True):
    """One row per (run, stage, criterion) — fully queryable."""
    __tablename__ = "criterion_results"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    
    # Stage context
    stage_num: int
    stage_name: str
    
    # Criterion identity
    criterion_num: int  # 0, 1, 2 within stage
    criterion_type: str  # "code_rule" or "llm_judge"
    criterion_description: str
    
    # Scoring
    score: float
    max_score: float
    # passed is derivable: score >= threshold
    
    # Evaluator reasoning (mandatory)
    feedback: str
    
    # What was evaluated — references
    evaluated_action_ids: list[str] = Field(
        default_factory=list, 
        sa_column=Column(JSON)
    )  # UUIDs of actions
    evaluated_resource_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON)
    )  # UUIDs of output resources
    
    __table_args__ = (
        Index("ix_criterion_results_run", "run_id"),
        Index("ix_criterion_results_stage", "stage_name"),
    )
```

---

## Table Summary

| Table | Purpose | Key Indexes |
|-------|---------|-------------|
| experiments | GDPEval tasks + ground truth + input_files | gdpeval_task_id, category |
| runs | Execution attempts + output | experiment_id, status |
| messages | Worker↔Stakeholder Q&A | run_id+sequence_num |
| actions | Flattened tool call trace | run_id+action_num, run_id+action_type |
| resources | Input files (experiment_id) + Output files (run_id) | experiment_id, run_id |
| evaluations | Aggregate scores | run_id |
| criterion_results | Per-criterion scores + feedback | run_id, stage_name |

**Total: 7 tables**

---

## Domain Logic

### Worker Agent

#### WorkerToolkit

```python
class WorkerToolkit:
    """
    Tools available to the worker during execution.
    
    - ask_stakeholder: Clarification tool (executes outside sandbox)
    - GDPEval tools: Documents, spreadsheets, RAG, OCR, code execution (execute in E2B sandbox)
    
    See SANDBOX_ARCHITECTURE.md for sandbox execution details.
    """
    
    def __init__(
        self,
        run_id: UUID,
        stakeholder: RubricStakeholder,
        sandbox_manager: SandboxManager,  # Replaces ResourceFileManager
        max_questions: int = 10,
    ):
        self.run_id = run_id
        self.stakeholder = stakeholder
        self.sandbox_manager = sandbox_manager
        self.max_questions = max_questions
        self._questions_asked = 0
        self._action_num = 0
        self._message_num = 0
    
    async def ask_stakeholder(self, question: str) -> str:
        """Ask the stakeholder a clarification question."""
        if self._questions_asked >= self.max_questions:
            return f"[Maximum questions ({self.max_questions}) reached.]"
        
        # Log worker question
        await queries.messages.create(
            run_id=self.run_id,
            sender=MessageRole.WORKER,
            content=question,
            sequence_num=self._message_num,
        )
        self._message_num += 1
        
        # Get answer
        answer = await self.stakeholder.answer(question)
        
        # Log stakeholder answer
        await queries.messages.create(
            run_id=self.run_id,
            sender=MessageRole.STAKEHOLDER,
            content=answer,
            sequence_num=self._message_num,
        )
        self._message_num += 1
        
        # Log as action
        await queries.actions.create(
            run_id=self.run_id,
            action_num=self._action_num,
            action_type="ask_stakeholder",
            input=question,
            output=answer,
        )
        self._action_num += 1
        
        self._questions_asked += 1
        return answer
    
    @property
    def questions_asked(self) -> int:
        return self._questions_asked
    
    def get_gdpeval_tools(self) -> list[Tool]:
        """Get GDPEval tools that execute in sandbox."""
        # Set sandbox manager for execute_in_sandbox()
        from h_arcane.agents.sandbox_executor import set_sandbox_manager
        set_sandbox_manager(self.sandbox_manager)
        
        # Import tool functions (they're @function_tool decorated and call execute_in_sandbox internally)
        from h_arcane.agents.tools import (
            read_pdf,
            create_docx,
            read_excel,
            create_excel,
            # ... etc
        )
        
        return [
            read_pdf,
            create_docx,
            read_excel,
            create_excel,
            # ... etc
        ]
```

#### Tools Architecture

```
# Tool modules (uploaded to sandbox):
h_arcane/tools/
├── read_pdf.py
├── create_docx.py
├── read_excel.py
└── ...                  # Other tool modules

# H-ARCANE execution layer:
h_arcane/agents/
├── toolkit.py          # WorkerToolkit with ask_stakeholder + get_gdpeval_tools()
├── sandbox_executor.py # execute_in_sandbox() function
└── tools.py            # @function_tool wrappers (call execute_in_sandbox)

# Note: Tool logic extracted from manager_agent_gym, but execution happens in E2B sandbox
# See SANDBOX_ARCHITECTURE.md for details
```

#### ReActWorker

```python
from agents import Agent, Runner, function_tool
from pydantic import BaseModel

class WorkerExecutionOutput(BaseModel):
    """Structured output from worker execution."""
    reasoning: str  # Explanation of approach and decisions made
    output_text: str  # Text summary/output
    output_resources: list[Resource]  # Resources created during execution

class ReActWorker:
    """ReAct-style worker with ask_stakeholder + GDPEval tools."""
    
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
    
    async def execute(
        self, 
        run_id: UUID,
        task_description: str,
        input_resources: list[Resource],
        toolkit: WorkerToolkit,
    ) -> WorkerExecutionOutput:
        """Execute task, return structured output with reasoning and resources."""
        
        tools = [
            self._make_ask_tool(toolkit),
            *self._wrap_gdpeval_tools(toolkit),
        ]
        
        agent = Agent(
            name="TaskWorker",
            model=self.model,
            instructions=REACT_WORKER_PROMPT,
            tools=tools,
            output_type=WorkerExecutionOutput,
        )
        
        result = await Runner.run(
            agent,
            messages=[{
                "role": "user",
                "content": self._format_task(task_description, input_resources),
            }],
        )
        
        # Extract structured output
        execution_output: WorkerExecutionOutput = result.final_output
        
        # Worker creates resources during execution via toolkit
        # Get actual resources from database to ensure they're up to date
        db_resources = await queries.resources.get_all(run_id)
        
        # Update output_resources with actual Resource objects from DB
        execution_output.output_resources = db_resources
        
        return execution_output
    
    def _make_ask_tool(self, toolkit: WorkerToolkit):
        @function_tool
        async def ask_stakeholder(question: str) -> str:
            """Ask the stakeholder a clarification question about the task."""
            return await toolkit.ask_stakeholder(question)
        return ask_stakeholder
    
    def _wrap_gdpeval_tools(self, toolkit: WorkerToolkit) -> list:
        """Wrap GDPEval tools with action logging."""
        gdpeval_tools = toolkit.get_gdpeval_tools()
        return [self._wrap_with_logging(t, toolkit) for t in gdpeval_tools]
```

#### System Prompt

```python
REACT_WORKER_PROMPT = """
You are a skilled worker completing a task for a stakeholder.

You have access to tools including:
- `ask_stakeholder`: Ask clarification questions when uncertain
- Document tools: read_pdf, create_docx, etc.
- Spreadsheet tools: read_excel, create_excel, read_csv, etc.
- Search tools: search_documents
- Code execution: execute_python_code

Use ask_stakeholder when you're uncertain about:
- What exactly the stakeholder wants
- How to interpret ambiguous requirements  
- Preferences between different approaches

Think step by step. Complete the task to the best of your ability.

When you finish, provide:
1. Your reasoning: Explain your approach and key decisions
2. Output text: A summary or text output of what you accomplished
3. Output resources: List all files/resources you created
"""
```

---

### Stakeholder

```python
from openai import AsyncOpenAI
from paper_code_structure_plans.schemas.staged_rubric_schema import StagedRubric

class RubricStakeholder:
    """Stakeholder that answers questions based on ground truth rubric."""
    
    ANSWER_PROMPT = """
    You are a stakeholder with specific preferences for how a task should be done.
    
    Your preferences (internal, don't reveal directly):
    {rubric_summary}
    
    A worker asks you: "{question}"
    
    Task context: {task_description}
    
    Answer helpfully and specifically based on your preferences.
    Don't reveal your full rubric — just answer the specific question.
    Be concise but complete.
    """
    
    def __init__(
        self,
        ground_truth_rubric: StagedRubric,
        task_description: str,
        model: str = "gpt-4o",
    ):
        self.ground_truth_rubric = ground_truth_rubric
        self.task_description = task_description
        self.model = model
        self._rubric_summary = self._summarize_rubric(ground_truth_rubric)
    
    async def answer(self, question: str) -> str:
        """Answer based on ground truth rubric."""
        client = AsyncOpenAI()
        
        response = await client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": self.ANSWER_PROMPT.format(
                    rubric_summary=self._rubric_summary,
                    question=question,
                    task_description=self.task_description,
                ),
            }],
            max_tokens=500,
        )
        
        return response.choices[0].message.content
    
    def _summarize_rubric(self, rubric: StagedRubric) -> str:
        """Create a summary of the rubric for the prompt."""
        return "\n".join(
            f"- {stage.name} ({stage.max_points} pts): {stage.description}"
            for stage in rubric.stages
        )
```

---

### Helper Functions

#### Loading Messages

```python
def get_messages(run_id: UUID) -> list[Message]:
    """Load all messages for a run, ordered by sequence."""
    return queries.messages.get_all(run_id, order_by="sequence_num")

def count_questions(run_id: UUID) -> int:
    """Count worker questions."""
    messages = get_messages(run_id)
    return sum(1 for m in messages if m.sender == MessageRole.WORKER)
```

#### Querying Criteria

```python
def get_criterion_breakdown(run_id: UUID) -> list[CriterionResult]:
    """Get all criterion results for a run."""
    return queries.criterion_results.get_all(
        run_id=run_id, 
        order_by=["stage_num", "criterion_num"]
    )

def get_failed_criteria(run_id: UUID, threshold: float = 1.0) -> list[CriterionResult]:
    """Get criteria that didn't achieve full score."""
    results = get_criterion_breakdown(run_id)
    return [cr for cr in results if cr.score < cr.max_score * threshold]
```

---

## Database Queries

### Key Queries

```sql
-- Get all messages for a run
SELECT sender, content, sequence_num, created_at
FROM messages
WHERE run_id = :run_id
ORDER BY sequence_num;

-- Get action breakdown for a run
SELECT action_type, COUNT(*) as count
FROM actions
WHERE run_id = :run_id
GROUP BY action_type
ORDER BY count DESC;

-- Aggregate: questions asked vs score
SELECT 
    questions_asked,
    AVG(normalized_score) as avg_score,
    COUNT(*) as num_runs
FROM runs
WHERE status = 'completed'
GROUP BY questions_asked
ORDER BY questions_asked;

-- Full criterion breakdown for a run
SELECT 
    cr.stage_num, 
    cr.stage_name, 
    cr.criterion_num,
    cr.criterion_description,
    cr.score, 
    cr.max_score, 
    cr.feedback
FROM criterion_results cr
WHERE cr.run_id = :run_id
ORDER BY cr.stage_num, cr.criterion_num;

-- Which criteria fail most often?
SELECT 
    stage_name, 
    criterion_description, 
    COUNT(*) as total,
    SUM(CASE WHEN score < max_score THEN 1 ELSE 0 END) as failures,
    AVG(score / max_score) as avg_pct
FROM criterion_results
GROUP BY stage_name, criterion_description
ORDER BY failures DESC;

-- Get criterion with the actions that were evaluated
SELECT 
    cr.stage_name,
    cr.criterion_description,
    cr.score,
    cr.feedback,
    a.action_type,
    a.input,
    a.output
FROM criterion_results cr
CROSS JOIN LATERAL unnest(cr.evaluated_action_ids) AS action_id
JOIN actions a ON a.id::text = action_id
WHERE cr.run_id = :run_id
ORDER BY cr.stage_num, cr.criterion_num;

-- Debug view: inputs → actions → criterion scores
SELECT 
    e.task_description,
    e.input_files,
    r.output_text,
    r.output_resource_ids,
    res.name as output_file_name,
    res.file_path as output_file_path,
    cr.stage_name,
    cr.criterion_description,
    cr.score,
    cr.max_score,
    cr.feedback
FROM runs r
JOIN experiments e ON e.id = r.experiment_id
JOIN criterion_results cr ON cr.run_id = r.id
LEFT JOIN LATERAL unnest(r.output_resource_ids) AS resource_id ON true
LEFT JOIN resources res ON res.id::text = resource_id
WHERE r.id = :run_id
ORDER BY cr.stage_num, cr.criterion_num;
```

---

## Summary

| Entity | Table | Purpose |
|--------|-------|---------|
| `Experiment` | `experiments` | GDPEval task + ground truth rubric + input_files |
| `Run` | `runs` | Execution attempt + output |
| `Message` | `messages` | Worker↔Stakeholder Q&A |
| `Action` | `actions` | Flattened tool call trace |
| `Resource` | `resources` | Output files (worker-generated) |
| `Evaluation` | `evaluations` | Aggregate scores |
| `CriterionResult` | `criterion_results` | Per-criterion score + feedback + what was evaluated |

**7 entities, 7 tables**
