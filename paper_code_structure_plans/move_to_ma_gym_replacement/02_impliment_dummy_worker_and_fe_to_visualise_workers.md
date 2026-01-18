# 02: Workflow Diagnostic Dashboard

## Overview

This document details the plan for a diagnostic dashboard that allows users to visualize running (and historical) workflow executions. The dashboard provides real-time visibility into:

- **DAG visualization** with hierarchical task levels (L1 → L2 → L3)
- **Task status** progression through the workflow
- **Agent action streams** as they happen
- **Resources** created by each task
- **E2B sandbox** state and metrics

---

## Complete File Structure After Implementation

```
arcane_extension/
│
├── docker-compose.yml                    # Updated: adds arcane-dashboard service
├── Dockerfile.api                        # Existing: Python API container
│
├── h_arcane/                             # Python package (existing + new dashboard module)
│   ├── __init__.py
│   ├── task.py                           # PUBLIC: Task, Resource, TaskStatus
│   ├── runner.py                         # PUBLIC: execute_task() - MODIFIED to emit events
│   ├── worker.py                         # PUBLIC: BaseWorker protocol
│   │
│   ├── _internal/
│   │   │
│   │   ├── dashboard/                    # NEW: Dashboard event emission
│   │   │   ├── __init__.py
│   │   │   ├── events.py                 # Event constants + payload dataclasses
│   │   │   └── emitter.py                # DashboardEmitter class
│   │   │
│   │   ├── task/
│   │   │   ├── __init__.py
│   │   │   ├── events.py                 # Existing task events
│   │   │   ├── registry.py               # TaskRegistry
│   │   │   ├── propagation.py            # MODIFIED: emit dashboard events
│   │   │   └── persistence.py            # MODIFIED: emit resource events
│   │   │
│   │   ├── inngest/
│   │   │   ├── __init__.py
│   │   │   ├── client.py
│   │   │   ├── task_functions.py         # MODIFIED: emit task status events
│   │   │   ├── eval_functions.py
│   │   │   └── workflow_functions.py     # MODIFIED: emit workflow events
│   │   │
│   │   ├── infrastructure/
│   │   │   ├── __init__.py
│   │   │   ├── sandbox.py                # MODIFIED: emit sandbox events
│   │   │   └── inngest_client.py
│   │   │
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── registry.py
│   │   │   └── base.py                   # MODIFIED: emit action events from workers
│   │   │
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── connection.py
│   │   │   ├── models.py
│   │   │   └── queries.py
│   │   │
│   │   ├── evaluation/
│   │   │   └── ... (unchanged)
│   │   │
│   │   └── communication/
│   │       └── ... (unchanged)
│   │
│   ├── benchmarks/
│   │   ├── __init__.py
│   │   ├── smoke_test/                   # NEW: Fast smoke test benchmark
│   │   │   ├── __init__.py
│   │   │   ├── config.py                 # WorkerConfig for smoke test
│   │   │   ├── toolkit.py                # SmokeTestToolkit with stub tools
│   │   │   ├── stakeholder.py            # Simple mock stakeholder
│   │   │   ├── loader.py                 # Load smoke test experiments
│   │   │   ├── factories.py              # Factory functions
│   │   │   ├── stub_responses.py         # Pydantic response models
│   │   │   └── cli.py                    # CLI to run smoke tests
│   │   │
│   │   ├── gdpeval/
│   │   ├── minif2f/
│   │   └── researchrubrics/
│   │
│   ├── api/
│   │   └── main.py                       # Existing FastAPI server
│   │
│   └── config/
│       └── ... (unchanged)
│
├── arcane-dashboard/                     # NEW: Next.js diagnostic dashboard
│   │
│   ├── package.json
│   ├── package-lock.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── Dockerfile
│   │
│   ├── src/
│   │   │
│   │   ├── app/                          # Next.js App Router
│   │   │   ├── layout.tsx                # Root layout with providers
│   │   │   ├── page.tsx                  # Home: list of active/recent runs
│   │   │   │
│   │   │   ├── run/
│   │   │   │   └── [runId]/
│   │   │   │       ├── page.tsx          # Main DAG view for a run
│   │   │   │       └── task/
│   │   │   │           └── [taskId]/
│   │   │   │               └── page.tsx  # Task detail view
│   │   │   │
│   │   │   └── api/
│   │   │       ├── inngest/
│   │   │       │   └── route.ts          # Inngest webhook endpoint
│   │   │       └── ws/
│   │   │           └── route.ts          # WebSocket upgrade endpoint
│   │   │
│   │   ├── inngest/                      # Inngest event subscribers
│   │   │   ├── client.ts                 # Inngest client config
│   │   │   ├── index.ts                  # Export all functions
│   │   │   └── functions/
│   │   │       ├── workflow-events.ts    # workflow.started, workflow.completed
│   │   │       ├── task-events.ts        # task.status_changed, task.assigned
│   │   │       ├── action-events.ts      # action.started, action.completed
│   │   │       └── resource-events.ts    # resource.published
│   │   │
│   │   ├── lib/
│   │   │   ├── state/
│   │   │   │   ├── types.ts              # TypeScript types (WorkflowRun, TaskNode, etc.)
│   │   │   │   └── store.ts              # In-memory DashboardStore class
│   │   │   │
│   │   │   ├── ws/
│   │   │   │   ├── server.ts             # WebSocket server setup
│   │   │   │   └── broadcast.ts          # Broadcast to subscribed clients
│   │   │   │
│   │   │   └── utils.ts                  # Shared utilities
│   │   │
│   │   ├── components/
│   │   │   │
│   │   │   ├── dag/                      # DAG visualization
│   │   │   │   ├── DAGCanvas.tsx         # Main react-flow canvas
│   │   │   │   ├── TaskNode.tsx          # Custom node component
│   │   │   │   ├── TaskEdge.tsx          # Custom edge component
│   │   │   │   └── LevelSelector.tsx     # L1/L2/L3 navigation tabs
│   │   │   │
│   │   │   ├── panels/                   # Detail panels
│   │   │   │   ├── TaskDetailPanel.tsx   # Slide-out task details
│   │   │   │   ├── ActionStreamPanel.tsx # Live action list
│   │   │   │   ├── ResourcePanel.tsx     # Input/output resources
│   │   │   │   ├── SandboxPanel.tsx      # E2B sandbox info
│   │   │   │   └── RunListPanel.tsx      # Home page run list
│   │   │   │
│   │   │   ├── common/                   # Shared UI components
│   │   │   │   ├── StatusBadge.tsx       # Colored status indicator
│   │   │   │   ├── SearchInput.tsx       # Search/filter input
│   │   │   │   ├── TimeAgo.tsx           # Relative time display
│   │   │   │   └── LoadingSpinner.tsx
│   │   │   │
│   │   │   └── providers/
│   │   │       └── WebSocketProvider.tsx # React context for WS connection
│   │   │
│   │   └── hooks/
│   │       ├── useWebSocket.ts           # WebSocket connection hook
│   │       ├── useRunState.ts            # Subscribe to run updates
│   │       └── useTaskDetails.ts         # Get task with actions/resources
│   │
│   └── public/
│       └── ... (static assets)
│
└── tests/
    ├── unit/
    │   ├── test_task.py
    │   ├── test_dag.py
    │   ├── test_persistence.py
    │   └── test_dashboard_emitter.py     # NEW: Test event emission
    │
    └── integration/
        └── test_dashboard_events.py      # NEW: E2E event flow tests
```

### Key Changes Summary

| Area | Files Added/Modified |
|------|---------------------|
| **Python: Smoke Test Benchmark** | `h_arcane/benchmarks/smoke_test/` (new benchmark following existing pattern) |
| **Python: Dashboard Module** | `h_arcane/_internal/dashboard/` (new directory with `events.py`, `emitter.py`) |
| **Python: Event Emission Points** | Modify `tracing.py` to emit dashboard events after writing to PG |
| **Next.js: Full App** | `arcane-dashboard/` (new directory - entire Next.js application) |
| **Docker** | `docker-compose.yml` updated, `arcane-dashboard/Dockerfile` added |

---

## Design Philosophy

1. **Separation of Concerns**: The dashboard is a separate Next.js application (BFF pattern) - keeps the core `h_arcane` package focused on execution
2. **Event-Driven**: Python emits Inngest events → Next.js subscribes → pushes to frontend via WebSocket
3. **Dockerized**: Runs as its own container, exposed on port 3000
4. **Read-Only**: Dashboard observes but doesn't control (no task management from UI)
5. **Fully Dynamic**: Dashboard has **zero prior knowledge** of runs - it's purely reactive to events. Users can start runs from CLI, SDK, or any entry point and the dashboard will pick them up automatically.

---

## Part 0: Smoke Test Benchmark (Key Deliverable)

### 0.1 Purpose

Before building the full dashboard UI, we need a reliable way to test the entire event pipeline end-to-end. The **smoke test benchmark**:

1. Follows the **exact same pattern** as existing benchmarks (gdpeval, minif2f, researchrubrics)
2. Uses OpenAI Agents SDK with **stubbed tools** that return mock data instantly
3. Runs 3-5 tool calls max per task (fast execution)
4. Validates: PostgreSQL persistence, Inngest events, dashboard event emission

### 0.2 Smoke Test File Structure

```
h_arcane/benchmarks/smoke_test/
├── __init__.py
├── config.py             # WorkerConfig for smoke test
├── toolkit.py            # SmokeTestToolkit with stub tools
├── stakeholder.py        # Simple mock stakeholder
├── loader.py             # Load smoke test "experiments" 
├── factories.py          # Factory functions (like other benchmarks)
└── stub_responses.py     # Pydantic response models for stub tools
```

### 0.3 Stub Tools (Following Existing Pattern)

```python
# h_arcane/benchmarks/smoke_test/stub_responses.py

from pydantic import BaseModel

class StubReadFileResponse(BaseModel):
    """Response from stub read_file tool."""
    success: bool = True
    content: str
    size_bytes: int
    error: str | None = None

class StubWriteFileResponse(BaseModel):
    """Response from stub write_file tool."""
    success: bool = True
    path: str
    size_bytes: int
    error: str | None = None

class StubAnalyzeResponse(BaseModel):
    """Response from stub analyze tool."""
    success: bool = True
    summary: str
    findings: list[str]
    error: str | None = None
```

```python
# h_arcane/benchmarks/smoke_test/toolkit.py

"""Smoke test toolkit with fast stub tools."""

from uuid import UUID
from agents import function_tool, Tool

from h_arcane._internal.agents.base import BaseToolkit, BaseStakeholder
from h_arcane.benchmarks.smoke_test.stub_responses import (
    StubReadFileResponse,
    StubWriteFileResponse,
    StubAnalyzeResponse,
)


class SmokeTestToolkit(BaseToolkit):
    """Fast toolkit with stub tools for smoke testing."""

    def __init__(
        self,
        run_id: UUID,
        experiment_id: UUID,
        stakeholder: BaseStakeholder,
        max_questions: int = 3,
    ):
        self.run_id = run_id
        self.experiment_id = experiment_id
        self.stakeholder = stakeholder
        self.max_questions = max_questions
        self._questions_asked = 0

    @property
    def questions_asked(self) -> int:
        return self._questions_asked

    def get_tools(self) -> list[Tool]:
        return [
            self._read_file(),
            self._write_file(),
            self._analyze(),
            self._ask_stakeholder(),
        ]

    async def ask_stakeholder(self, question: str) -> str:
        if self._questions_asked >= self.max_questions:
            return f"[Maximum questions ({self.max_questions}) reached.]"
        self._questions_asked += 1
        return await self.stakeholder.answer(question)

    def _read_file(self) -> Tool:
        @function_tool
        async def read_file(file_path: str) -> StubReadFileResponse:
            """
            Read a file from the workspace.
            
            Args:
                file_path: Path to the file (e.g., "/inputs/data.txt")
            
            Returns:
                File content and metadata.
            """
            # Stub: return mock content immediately
            return StubReadFileResponse(
                success=True,
                content=f"Mock content from {file_path}\n\nThis is simulated file data for testing.",
                size_bytes=1234,
            )
        return read_file

    def _write_file(self) -> Tool:
        @function_tool
        async def write_file(file_path: str, content: str) -> StubWriteFileResponse:
            """
            Write content to a file in the workspace.
            
            Args:
                file_path: Where to write (e.g., "/workspace/output.txt")
                content: Content to write
            
            Returns:
                Confirmation with file path and size.
            """
            # Stub: pretend to write, return success
            return StubWriteFileResponse(
                success=True,
                path=file_path,
                size_bytes=len(content),
            )
        return write_file

    def _analyze(self) -> Tool:
        @function_tool
        async def analyze_data(data: str) -> StubAnalyzeResponse:
            """
            Analyze data and return insights.
            
            Args:
                data: Data to analyze
            
            Returns:
                Analysis summary and key findings.
            """
            # Stub: return mock analysis
            return StubAnalyzeResponse(
                success=True,
                summary="Mock analysis complete. Data appears valid.",
                findings=[
                    "Finding 1: Data structure is consistent",
                    "Finding 2: No anomalies detected",
                    "Finding 3: Ready for processing",
                ],
            )
        return analyze_data

    def _ask_stakeholder(self) -> Tool:
        @function_tool
        async def ask_stakeholder(question: str) -> str:
            """
            Ask the stakeholder a clarifying question.
            
            Args:
                question: Your question
            
            Returns:
                Stakeholder's response.
            """
            return await self.ask_stakeholder(question)
        return ask_stakeholder
```

### 0.4 Simple Mock Stakeholder

```python
# h_arcane/benchmarks/smoke_test/stakeholder.py

from h_arcane._internal.agents.base import BaseStakeholder
from h_arcane._internal.communication.schemas import MessageResponse


class MockStakeholder(BaseStakeholder):
    """Simple stakeholder that returns canned responses."""

    def __init__(self):
        self._responses = [
            "Yes, that approach sounds good.",
            "Please proceed with the standard format.",
            "The output should be saved to /workspace/final_output/",
        ]
        self._call_count = 0

    @property
    def model(self) -> str:
        return "mock"

    @property
    def system_prompt(self) -> str:
        return "Mock stakeholder for smoke testing."

    async def answer(
        self,
        question: str,
        history: list[MessageResponse] | None = None,
    ) -> str:
        response = self._responses[self._call_count % len(self._responses)]
        self._call_count += 1
        return response
```

### 0.5 Smoke Test Loader

```python
# h_arcane/benchmarks/smoke_test/loader.py

"""Load smoke test experiments into database."""

from uuid import UUID
from h_arcane._internal.db.models import Experiment
from h_arcane._internal.db.queries import queries
from h_arcane.benchmarks.enums import BenchmarkName


SMOKE_TEST_TASKS = [
    {
        "task_id": "smoke_simple_001",
        "description": "Read the input file and summarize its contents in a new file.",
        "category": "simple",
    },
    {
        "task_id": "smoke_analysis_001",
        "description": "Analyze the provided data and write a brief report with your findings.",
        "category": "analysis",
    },
    {
        "task_id": "smoke_multistep_001",
        "description": "Read the input, ask any clarifying questions, analyze the data, and produce a final output document.",
        "category": "multistep",
    },
]


class SmokeTestLoader:
    """Load smoke test tasks into database."""

    def load_tasks(self, limit: int | None = None) -> list[dict]:
        tasks = SMOKE_TEST_TASKS[:limit] if limit else SMOKE_TEST_TASKS
        return tasks

    def load_to_database(self, tasks: list[dict]) -> list[UUID]:
        experiment_ids = []
        for task in tasks:
            experiment = queries.experiments.create(
                Experiment(
                    benchmark_name=BenchmarkName.SMOKE_TEST,
                    task_id=task["task_id"],
                    task_description=task["description"],
                    category=task["category"],
                    ground_truth_rubric={},  # No evaluation for smoke test
                )
            )
            experiment_ids.append(experiment.id)
        return experiment_ids
```

### 0.6 CLI Entry Point

```python
# h_arcane/benchmarks/smoke_test/cli.py

"""CLI for running smoke tests."""

import asyncio
import typer
from rich.console import Console

app = typer.Typer(help="Smoke test CLI")
console = Console()


@app.command()
def run(
    task_id: str = typer.Option("smoke_simple_001", "--task", "-t"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m"),
):
    """Run a smoke test task."""
    asyncio.run(_run_task(task_id, model))


async def _run_task(task_id: str, model: str):
    from h_arcane.benchmarks.smoke_test.loader import SmokeTestLoader
    from h_arcane._internal.infrastructure.inngest_client import inngest_client
    
    console.print(f"[cyan]Running smoke test: {task_id}[/cyan]")
    
    # Load task to DB
    loader = SmokeTestLoader()
    tasks = [t for t in loader.load_tasks() if t["task_id"] == task_id]
    if not tasks:
        console.print(f"[red]Task not found: {task_id}[/red]")
        return
    
    experiment_ids = loader.load_to_database(tasks)
    experiment_id = experiment_ids[0]
    
    console.print(f"[green]Created experiment: {experiment_id}[/green]")
    
    # Trigger run via Inngest
    await inngest_client.send(
        "run/start",
        data={
            "experiment_id": str(experiment_id),
            "worker_model": model,
            "max_questions": 3,
        },
    )
    
    console.print("[green]Run triggered! Check dashboard at http://localhost:3000[/green]")


if __name__ == "__main__":
    app()
```

### 0.7 Usage

```bash
# Run a simple smoke test
python -m h_arcane.benchmarks.smoke_test.cli run --task smoke_simple_001

# Run with a specific model
python -m h_arcane.benchmarks.smoke_test.cli run --task smoke_analysis_001 --model gpt-4o

# Open dashboard to watch
open http://localhost:3000
```

### 0.8 What This Validates

| Component | Validated By |
|-----------|-------------|
| **Existing benchmark pattern** | Uses same toolkit/stakeholder/loader structure |
| **OpenAI Agents SDK** | Uses `@function_tool`, `Agent`, `Runner.run()` |
| **Action tracing** | Existing `log_actions_from_result()` records to PG |
| **Inngest orchestration** | Same `run/start` event as other benchmarks |
| **Dashboard events** | Events emitted at same points as production |
| **Fast execution** | Stub tools return immediately (no E2B, no real LLM for tools) |

### 0.5 Test Workflows

```python
# h_arcane/benchmarks/smoke_test/workflows.py

"""
Pre-defined test workflows for smoke testing.

Each workflow exercises different DAG patterns:
- Single task
- Linear chain (A → B → C)
- Parallel tasks (A → [B, C] → D)
- Nested hierarchy (composite tasks)
"""

from h_arcane import Task, Resource
from h_arcane.benchmarks.smoke_test.dummy_worker import DummyWorker


def create_single_task_workflow() -> Task:
    """Simplest case: one task, one worker."""
    worker = DummyWorker(name="single_worker", execution_delay_ms=50)
    
    return Task(
        name="Simple Analysis",
        description="Analyze a single file and produce a summary.",
        assigned_to=worker,
        resources=[
            Resource(path="data/input.txt", name="Input Data"),
        ],
    )


def create_linear_chain_workflow() -> Task:
    """Linear dependency: A → B → C"""
    worker = DummyWorker(name="chain_worker", execution_delay_ms=50)
    
    task_a = Task(
        name="Gather Data",
        description="Collect raw data from sources.",
        assigned_to=worker,
        resources=[Resource(path="data/raw.csv", name="Raw Data")],
    )
    
    task_b = Task(
        name="Process Data",
        description="Clean and transform the data.",
        assigned_to=worker,
        depends_on=[task_a],
    )
    
    task_c = Task(
        name="Generate Report",
        description="Create final report from processed data.",
        assigned_to=worker,
        depends_on=[task_b],
    )
    
    return Task(
        name="Linear Pipeline",
        description="A simple A → B → C workflow",
        assigned_to=worker,
        children=[task_a, task_b, task_c],
    )


def create_parallel_workflow() -> Task:
    """Parallel tasks that converge: A → [B, C] → D"""
    analyst = DummyWorker(name="analyst", execution_delay_ms=75)
    writer = DummyWorker(name="writer", execution_delay_ms=50)
    
    gather = Task(
        name="Gather Requirements",
        description="Collect all requirements.",
        assigned_to=analyst,
        resources=[Resource(path="requirements.md", name="Requirements")],
    )
    
    analyze_tech = Task(
        name="Technical Analysis",
        description="Analyze technical feasibility.",
        assigned_to=analyst,
        depends_on=[gather],
    )
    
    analyze_business = Task(
        name="Business Analysis", 
        description="Analyze business impact.",
        assigned_to=analyst,
        depends_on=[gather],
    )
    
    write_report = Task(
        name="Write Final Report",
        description="Combine analyses into final report.",
        assigned_to=writer,
        depends_on=[analyze_tech, analyze_business],
    )
    
    return Task(
        name="Parallel Analysis",
        description="Gather → [Tech, Business] → Report",
        assigned_to=writer,
        children=[gather, analyze_tech, analyze_business, write_report],
    )


def create_nested_hierarchy_workflow() -> Task:
    """
    Nested composite tasks (L1 → L2 → L3):
    
    Root (L1)
    ├── Research Phase (L2)
    │   ├── Literature Review (L3)
    │   └── Data Collection (L3)
    └── Analysis Phase (L2)
        ├── Statistical Analysis (L3)
        └── Write Findings (L3)
    """
    researcher = DummyWorker(name="researcher", execution_delay_ms=60)
    analyst = DummyWorker(name="analyst", execution_delay_ms=80)
    
    # L3 tasks under Research Phase
    lit_review = Task(
        name="Literature Review",
        description="Review existing papers.",
        assigned_to=researcher,
        resources=[Resource(path="papers/", name="Papers Directory")],
    )
    
    data_collection = Task(
        name="Data Collection",
        description="Gather experimental data.",
        assigned_to=researcher,
        depends_on=[lit_review],
    )
    
    # L2 composite: Research Phase
    research_phase = Task(
        name="Research Phase",
        description="Complete background research.",
        assigned_to=researcher,
        children=[lit_review, data_collection],
    )
    
    # L3 tasks under Analysis Phase
    stats_analysis = Task(
        name="Statistical Analysis",
        description="Run statistical tests.",
        assigned_to=analyst,
    )
    
    write_findings = Task(
        name="Write Findings",
        description="Document the findings.",
        assigned_to=analyst,
        depends_on=[stats_analysis],
    )
    
    # L2 composite: Analysis Phase
    analysis_phase = Task(
        name="Analysis Phase",
        description="Analyze collected data.",
        assigned_to=analyst,
        children=[stats_analysis, write_findings],
        depends_on=[research_phase],  # Analysis waits for Research
    )
    
    # L1 root
    return Task(
        name="Research Project",
        description="Full research project with nested phases.",
        assigned_to=analyst,
        children=[research_phase, analysis_phase],
    )


# Registry of all test workflows
SMOKE_TEST_WORKFLOWS = {
    "single": create_single_task_workflow,
    "linear": create_linear_chain_workflow,
    "parallel": create_parallel_workflow,
    "nested": create_nested_hierarchy_workflow,
}
```

### 0.6 CLI Entry Point

```python
# h_arcane/benchmarks/smoke_test/cli.py

"""
CLI for running smoke test workflows.

Usage:
    # Run a specific workflow
    python -m h_arcane.benchmarks.smoke_test.cli run --workflow single
    
    # Run all workflows
    python -m h_arcane.benchmarks.smoke_test.cli run --all
    
    # List available workflows
    python -m h_arcane.benchmarks.smoke_test.cli list
"""

import asyncio
import typer
from rich.console import Console
from rich.table import Table

from h_arcane import execute_task
from h_arcane.benchmarks.smoke_test.workflows import SMOKE_TEST_WORKFLOWS

app = typer.Typer(help="Smoke test CLI for h_arcane dashboard development")
console = Console()


@app.command()
def list():
    """List available smoke test workflows."""
    table = Table(title="Available Smoke Test Workflows")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    
    for name, factory in SMOKE_TEST_WORKFLOWS.items():
        workflow = factory()
        table.add_row(name, workflow.description)
    
    console.print(table)


@app.command()
def run(
    workflow: str = typer.Option(None, "--workflow", "-w", help="Workflow name to run"),
    all_workflows: bool = typer.Option(False, "--all", "-a", help="Run all workflows"),
    delay_ms: int = typer.Option(100, "--delay", "-d", help="Execution delay per action (ms)"),
):
    """Run smoke test workflow(s)."""
    
    if all_workflows:
        workflows_to_run = list(SMOKE_TEST_WORKFLOWS.keys())
    elif workflow:
        if workflow not in SMOKE_TEST_WORKFLOWS:
            console.print(f"[red]Unknown workflow: {workflow}[/red]")
            console.print(f"Available: {', '.join(SMOKE_TEST_WORKFLOWS.keys())}")
            raise typer.Exit(1)
        workflows_to_run = [workflow]
    else:
        console.print("[red]Specify --workflow or --all[/red]")
        raise typer.Exit(1)
    
    asyncio.run(_run_workflows(workflows_to_run))


async def _run_workflows(workflow_names: list[str]):
    """Execute the specified workflows."""
    for name in workflow_names:
        console.print(f"\n[bold cyan]Running workflow: {name}[/bold cyan]")
        
        factory = SMOKE_TEST_WORKFLOWS[name]
        workflow = factory()
        
        console.print(f"  Root task: {workflow.name}")
        console.print(f"  Description: {workflow.description}")
        
        try:
            result = await execute_task(workflow)
            
            if result.success:
                console.print(f"  [green]✓ Completed in {result.duration_seconds:.2f}s[/green]")
            else:
                console.print(f"  [red]✗ Failed: {result.error}[/red]")
                
        except Exception as e:
            console.print(f"  [red]✗ Error: {e}[/red]")
    
    console.print("\n[bold green]Smoke test complete![/bold green]")
    console.print("Check the dashboard at http://localhost:3000 to see the runs.")


if __name__ == "__main__":
    app()
```

### 0.7 How to Use

```bash
# 1. Start the infrastructure
docker-compose up -d postgres inngest-dev arcane-api arcane-dashboard

# 2. List available smoke tests
python -m h_arcane.benchmarks.smoke_test.cli list

# 3. Run a single workflow
python -m h_arcane.benchmarks.smoke_test.cli run --workflow nested

# 4. Run all workflows
python -m h_arcane.benchmarks.smoke_test.cli run --all

# 5. Open dashboard to watch
open http://localhost:3000
```

### 0.8 What This Validates

| Component | Validated By |
|-----------|-------------|
| **Task schema** | Workflows create valid Task trees |
| **DAG execution** | Dependencies resolve correctly |
| **Event emission** | All dashboard events fire |
| **PostgreSQL** | Runs, TaskExecutions, Resources persist |
| **Inngest** | Events route to dashboard functions |
| **WebSocket** | Live updates reach frontend |
| **DAG visualization** | Multiple hierarchy levels render |

### 0.9 File Location Summary

All smoke test code goes in `h_arcane/benchmarks/smoke_test/`:

| File | Purpose | Section |
|------|---------|---------|
| `__init__.py` | Package init, exports | - |
| `stub_responses.py` | Pydantic models for stub tool responses | 0.3 |
| `toolkit.py` | `SmokeTestToolkit` with `@function_tool` stub tools | 0.3 |
| `stakeholder.py` | `MockStakeholder` returning canned responses | 0.4 |
| `loader.py` | `SmokeTestLoader` + `SMOKE_TEST_TASKS` definitions | 0.5 |
| `workflows.py` | Pre-defined DAG patterns (single, linear, parallel, nested) | 0.5 |
| `cli.py` | Typer CLI entry point (`list`, `run` commands) | 0.6 |

**Also needed** (from Part 2):

| File | Purpose |
|------|---------|
| `h_arcane/_internal/dashboard/__init__.py` | Package init |
| `h_arcane/_internal/dashboard/events.py` | `DashboardEvents` constants + payload dataclasses |
| `h_arcane/_internal/dashboard/emitter.py` | `DashboardEmitter` class wrapping Inngest sends |

---

## Part 1: Architecture Overview

### 1.1 Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           h_arcane (Python)                                  │
│                                                                             │
│  Task Execution ──► Inngest Events ──► Inngest Cloud/Dev Server            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Events forwarded
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        arcane-dashboard (Next.js)                           │
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │ Inngest         │    │ State Store     │    │ WebSocket       │         │
│  │ Functions       │───►│ (In-Memory)     │───►│ Server          │         │
│  │ (Subscribers)   │    │                 │    │                 │         │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘         │
│                                                        │                    │
│  ┌─────────────────────────────────────────────────────┼──────────────────┐ │
│  │                    React Frontend                   │                  │ │
│  │                                                     ▼                  │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐              │ │
│  │  │ DAG View │  │ Task     │  │ Action   │  │ Resource │              │ │
│  │  │          │  │ Details  │  │ Stream   │  │ Panel    │              │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Responsibilities

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| **h_arcane** | Python/Inngest | Emit events for all state changes, actions, resources |
| **arcane-dashboard** | Next.js 14 (App Router) | BFF: subscribe to events, serve frontend, WebSocket server |
| **State Store** | In-memory (Map) | Hold current state of all active runs for quick access |
| **Frontend** | React + Tailwind | Render DAG, task details, action streams |

### 1.3 Why This Architecture?

| Decision | Rationale |
|----------|-----------|
| **Separate Next.js app** | Keeps h_arcane as a pure Python research package; dashboard is optional |
| **Inngest for event transport** | Already using Inngest for orchestration; reuse same infrastructure |
| **In-memory state** | Simplicity; dashboard is ephemeral/diagnostic, not a DB of record |
| **WebSocket (not SSE)** | Bidirectional if needed later; better library support for complex streams |

---

## Part 2: Events to Emit from Python

### 2.1 Event Categories

We need to emit events for the dashboard to build a complete picture:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Event Categories                             │
├─────────────────────────────────────────────────────────────────┤
│ 1. WORKFLOW LIFECYCLE    │ Start, complete, fail                │
│ 2. TASK LIFECYCLE        │ Ready, started, completed, failed    │
│ 3. AGENT ACTIONS         │ Action started, completed, streamed  │
│ 4. RESOURCES             │ Input loaded, output published       │
│ 5. SANDBOX (optional)    │ Sandbox created, command run, closed │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Event Schemas

```python
# h_arcane/_internal/dashboard/events.py

"""
Events emitted for dashboard consumption.

These events are subscribed to by the Next.js dashboard app.
All events include run_id for correlation.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from typing import Any


# === Event Names (constants for Inngest) ===

class DashboardEvents:
    """Events the dashboard subscribes to."""
    
    # Workflow lifecycle
    WORKFLOW_STARTED = "dashboard/workflow.started"
    WORKFLOW_COMPLETED = "dashboard/workflow.completed"
    WORKFLOW_FAILED = "dashboard/workflow.failed"
    
    # Task lifecycle
    TASK_STATUS_CHANGED = "dashboard/task.status_changed"
    TASK_ASSIGNED = "dashboard/task.assigned"
    
    # Agent actions (high-frequency)
    AGENT_ACTION_STARTED = "dashboard/agent.action_started"
    AGENT_ACTION_COMPLETED = "dashboard/agent.action_completed"
    AGENT_THINKING = "dashboard/agent.thinking"  # For streaming thought process
    
    # Resources
    RESOURCE_LOADED = "dashboard/resource.loaded"
    RESOURCE_PUBLISHED = "dashboard/resource.published"
    
    # Sandbox (optional - for E2B integration)
    SANDBOX_CREATED = "dashboard/sandbox.created"
    SANDBOX_COMMAND = "dashboard/sandbox.command"
    SANDBOX_CLOSED = "dashboard/sandbox.closed"


# === Event Payloads ===

@dataclass
class WorkflowStartedPayload:
    """Emitted when execute_task() is called."""
    run_id: str
    experiment_id: str
    workflow_name: str
    task_tree: dict  # Full DAG structure for rendering
    started_at: str  # ISO format
    
    # Metadata for display
    total_tasks: int
    total_leaf_tasks: int


@dataclass
class WorkflowCompletedPayload:
    run_id: str
    status: str  # "completed" | "failed"
    completed_at: str
    duration_seconds: float
    final_score: float | None
    error: str | None


@dataclass  
class TaskStatusChangedPayload:
    """Emitted on any task status transition."""
    run_id: str
    task_id: str
    task_name: str
    parent_task_id: str | None  # For DAG hierarchy
    
    old_status: str | None
    new_status: str  # pending | ready | running | completed | failed
    
    # Context
    triggered_by: str | None  # "dependency_satisfied", "worker_started", etc.
    timestamp: str
    
    # For running tasks
    assigned_worker_id: str | None
    assigned_worker_name: str | None


@dataclass
class TaskAssignedPayload:
    """Emitted when a worker is assigned to execute a task."""
    run_id: str
    task_id: str
    task_name: str
    worker_id: str
    worker_name: str
    worker_model: str
    timestamp: str


@dataclass
class AgentActionStartedPayload:
    """Emitted when an agent begins an action (tool call)."""
    run_id: str
    task_id: str
    action_id: str
    worker_id: str
    worker_name: str
    
    action_type: str  # Tool name or "thinking"
    action_input: dict | str  # Tool arguments or prompt
    timestamp: str


@dataclass
class AgentActionCompletedPayload:
    """Emitted when an agent completes an action."""
    run_id: str
    task_id: str
    action_id: str
    worker_id: str
    
    action_type: str
    action_output: dict | str | None
    duration_ms: int
    success: bool
    error: str | None
    timestamp: str


@dataclass
class AgentThinkingPayload:
    """Emitted for streaming agent reasoning (if model supports it)."""
    run_id: str
    task_id: str
    worker_id: str
    
    content: str  # Partial thinking content
    is_complete: bool
    timestamp: str


@dataclass
class ResourcePublishedPayload:
    """Emitted when a task produces an output resource."""
    run_id: str
    task_id: str
    task_execution_id: str
    
    resource_id: str
    resource_name: str
    mime_type: str
    size_bytes: int
    preview_text: str | None  # First N chars for text files
    file_path: str  # Path in sandbox
    timestamp: str


@dataclass
class SandboxCreatedPayload:
    """Emitted when an E2B sandbox is created for a run."""
    run_id: str
    sandbox_id: str
    template_id: str
    created_at: str


@dataclass
class SandboxCommandPayload:
    """Emitted when a command runs in the sandbox."""
    run_id: str
    sandbox_id: str
    command: str
    stdout: str | None
    stderr: str | None
    exit_code: int
    duration_ms: int
    timestamp: str
```

### 2.3 Emitting Events from Python

Add emission points throughout the execution flow:

```python
# h_arcane/_internal/dashboard/emitter.py

"""
Dashboard event emitter.

Wraps Inngest event sending with dashboard-specific payloads.
"""

from h_arcane._internal.inngest.client import inngest
from h_arcane._internal.dashboard.events import (
    DashboardEvents,
    WorkflowStartedPayload,
    TaskStatusChangedPayload,
    AgentActionStartedPayload,
    AgentActionCompletedPayload,
    ResourcePublishedPayload,
)


class DashboardEmitter:
    """
    Emits events for dashboard consumption.
    
    Usage:
        emitter = DashboardEmitter()
        await emitter.workflow_started(run_id, experiment_id, task_tree)
    """
    
    def __init__(self, enabled: bool = True):
        self._enabled = enabled
    
    async def workflow_started(
        self,
        run_id: str,
        experiment_id: str,
        workflow_name: str,
        task_tree: dict,
        total_tasks: int,
        total_leaf_tasks: int,
    ) -> None:
        if not self._enabled:
            return
        
        await inngest.send(
            DashboardEvents.WORKFLOW_STARTED,
            data=WorkflowStartedPayload(
                run_id=run_id,
                experiment_id=experiment_id,
                workflow_name=workflow_name,
                task_tree=task_tree,
                started_at=datetime.now(timezone.utc).isoformat(),
                total_tasks=total_tasks,
                total_leaf_tasks=total_leaf_tasks,
            ).__dict__
        )
    
    async def task_status_changed(
        self,
        run_id: str,
        task_id: str,
        task_name: str,
        parent_task_id: str | None,
        old_status: str | None,
        new_status: str,
        triggered_by: str | None = None,
        assigned_worker_id: str | None = None,
        assigned_worker_name: str | None = None,
    ) -> None:
        if not self._enabled:
            return
        
        await inngest.send(
            DashboardEvents.TASK_STATUS_CHANGED,
            data=TaskStatusChangedPayload(
                run_id=run_id,
                task_id=task_id,
                task_name=task_name,
                parent_task_id=parent_task_id,
                old_status=old_status,
                new_status=new_status,
                triggered_by=triggered_by,
                timestamp=datetime.now(timezone.utc).isoformat(),
                assigned_worker_id=assigned_worker_id,
                assigned_worker_name=assigned_worker_name,
            ).__dict__
        )
    
    async def agent_action_started(
        self,
        run_id: str,
        task_id: str,
        action_id: str,
        worker_id: str,
        worker_name: str,
        action_type: str,
        action_input: dict | str,
    ) -> None:
        if not self._enabled:
            return
        
        await inngest.send(
            DashboardEvents.AGENT_ACTION_STARTED,
            data=AgentActionStartedPayload(
                run_id=run_id,
                task_id=task_id,
                action_id=action_id,
                worker_id=worker_id,
                worker_name=worker_name,
                action_type=action_type,
                action_input=action_input,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ).__dict__
        )
    
    async def agent_action_completed(
        self,
        run_id: str,
        task_id: str,
        action_id: str,
        worker_id: str,
        action_type: str,
        action_output: dict | str | None,
        duration_ms: int,
        success: bool,
        error: str | None = None,
    ) -> None:
        if not self._enabled:
            return
        
        await inngest.send(
            DashboardEvents.AGENT_ACTION_COMPLETED,
            data=AgentActionCompletedPayload(
                run_id=run_id,
                task_id=task_id,
                action_id=action_id,
                worker_id=worker_id,
                action_type=action_type,
                action_output=action_output,
                duration_ms=duration_ms,
                success=success,
                error=error,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ).__dict__
        )
    
    async def resource_published(
        self,
        run_id: str,
        task_id: str,
        task_execution_id: str,
        resource_id: str,
        resource_name: str,
        mime_type: str,
        size_bytes: int,
        file_path: str,
        preview_text: str | None = None,
    ) -> None:
        if not self._enabled:
            return
        
        await inngest.send(
            DashboardEvents.RESOURCE_PUBLISHED,
            data=ResourcePublishedPayload(
                run_id=run_id,
                task_id=task_id,
                task_execution_id=task_execution_id,
                resource_id=resource_id,
                resource_name=resource_name,
                mime_type=mime_type,
                size_bytes=size_bytes,
                preview_text=preview_text,
                file_path=file_path,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ).__dict__
        )


# Global instance (can be disabled via config)
dashboard_emitter = DashboardEmitter(enabled=True)
```

### 2.4 Integration Points in h_arcane

Where to emit events in the existing codebase:

| Location | Event(s) to Emit |
|----------|------------------|
| `runner.py` → `execute_task()` start | `WORKFLOW_STARTED` with full task_tree |
| `_internal/inngest/task_functions.py` → task status changes | `TASK_STATUS_CHANGED` |
| `_internal/inngest/task_functions.py` → task execution start | `TASK_ASSIGNED` |
| Worker `execute()` → before tool call | `AGENT_ACTION_STARTED` |
| Worker `execute()` → after tool call | `AGENT_ACTION_COMPLETED` |
| Worker `execute()` → streaming callback | `AGENT_THINKING` |
| `_internal/task/persistence.py` → resource created | `RESOURCE_PUBLISHED` |
| `_internal/infrastructure/sandbox.py` → sandbox lifecycle | `SANDBOX_*` events |
| `runner.py` → workflow completion | `WORKFLOW_COMPLETED` |

### 2.5 File Location Summary (Part 2)

**New files to create:**

| File | Contents | Section |
|------|----------|---------|
| `h_arcane/_internal/dashboard/__init__.py` | Package init, re-exports | - |
| `h_arcane/_internal/dashboard/events.py` | `DashboardEvents` class + payload dataclasses | 2.2 |
| `h_arcane/_internal/dashboard/emitter.py` | `DashboardEmitter` class + global `dashboard_emitter` | 2.3 |

**Existing files to modify:**

| File | Modification |
|------|--------------|
| `h_arcane/runner.py` | Add `dashboard_emitter.workflow_started()` and `workflow_completed()` calls |
| `h_arcane/_internal/inngest/task_functions.py` | Add `dashboard_emitter.task_status_changed()` calls |
| `h_arcane/_internal/task/persistence.py` | Add `dashboard_emitter.resource_published()` calls |
| `h_arcane/_internal/infrastructure/sandbox.py` | Add `dashboard_emitter.sandbox_*()` calls |
| `h_arcane/benchmarks/common/workers/tracing.py` | Add `dashboard_emitter.agent_action_*()` calls after PG writes |

---

## Part 3: Next.js Dashboard Application

### 3.1 Project Structure

```
arcane-dashboard/
├── package.json
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
├── Dockerfile
│
├── src/
│   ├── app/                      # Next.js App Router
│   │   ├── layout.tsx            # Root layout with WebSocket provider
│   │   ├── page.tsx              # Home: list of active/recent runs
│   │   ├── run/
│   │   │   └── [runId]/
│   │   │       ├── page.tsx      # Main DAG view for a run
│   │   │       └── task/
│   │   │           └── [taskId]/
│   │   │               └── page.tsx  # Task detail view
│   │   └── api/
│   │       ├── inngest/
│   │       │   └── route.ts      # Inngest function endpoint
│   │       └── ws/
│   │           └── route.ts      # WebSocket upgrade endpoint
│   │
│   ├── inngest/                  # Inngest functions (event subscribers)
│   │   ├── client.ts             # Inngest client config
│   │   ├── functions/
│   │   │   ├── workflow-events.ts
│   │   │   ├── task-events.ts
│   │   │   ├── action-events.ts
│   │   │   └── resource-events.ts
│   │   └── index.ts              # Export all functions
│   │
│   ├── lib/
│   │   ├── state/
│   │   │   ├── store.ts          # In-memory state store
│   │   │   └── types.ts          # TypeScript types for state
│   │   ├── ws/
│   │   │   ├── server.ts         # WebSocket server logic
│   │   │   └── broadcast.ts      # Broadcast to connected clients
│   │   └── utils.ts
│   │
│   ├── components/
│   │   ├── dag/
│   │   │   ├── DAGCanvas.tsx     # Main DAG visualization
│   │   │   ├── TaskNode.tsx      # Individual task node
│   │   │   ├── TaskEdge.tsx      # Dependency edge
│   │   │   └── LevelSelector.tsx # L1/L2/L3 level navigation
│   │   ├── panels/
│   │   │   ├── TaskDetailPanel.tsx
│   │   │   ├── ActionStreamPanel.tsx
│   │   │   ├── ResourcePanel.tsx
│   │   │   └── RunListPanel.tsx
│   │   ├── common/
│   │   │   ├── StatusBadge.tsx
│   │   │   ├── SearchInput.tsx
│   │   │   └── TimeAgo.tsx
│   │   └── providers/
│   │       └── WebSocketProvider.tsx
│   │
│   └── hooks/
│       ├── useWebSocket.ts
│       ├── useRunState.ts
│       └── useTaskDetails.ts
│
└── public/
    └── ... (static assets)
```

### 3.2 State Store Design

```typescript
// src/lib/state/types.ts

export type TaskStatus = 'pending' | 'ready' | 'running' | 'completed' | 'failed';

export interface TaskNode {
  id: string;
  name: string;
  description: string;
  parentId: string | null;
  childIds: string[];
  dependsOnIds: string[];
  
  status: TaskStatus;
  assignedWorkerId: string | null;
  assignedWorkerName: string | null;
  
  // Timestamps
  startedAt: string | null;
  completedAt: string | null;
  
  // For leaf tasks
  isLeaf: boolean;
  
  // Computed
  level: number;  // 1, 2, 3, etc. (depth in tree)
}

export interface AgentAction {
  id: string;
  taskId: string;
  workerId: string;
  workerName: string;
  
  type: string;  // Tool name
  input: unknown;
  output: unknown | null;
  
  status: 'started' | 'completed' | 'failed';
  startedAt: string;
  completedAt: string | null;
  durationMs: number | null;
  error: string | null;
}

export interface Resource {
  id: string;
  taskId: string;
  name: string;
  mimeType: string;
  sizeBytes: number;
  previewText: string | null;
  filePath: string;
  createdAt: string;
}

export interface WorkflowRun {
  id: string;
  experimentId: string;
  name: string;
  status: 'running' | 'completed' | 'failed';
  
  // Task DAG
  tasks: Map<string, TaskNode>;
  rootTaskId: string;
  
  // Actions (append-only, keyed by taskId for filtering)
  actionsByTask: Map<string, AgentAction[]>;
  
  // Resources
  resourcesByTask: Map<string, Resource[]>;
  
  // Timing
  startedAt: string;
  completedAt: string | null;
  durationSeconds: number | null;
  
  // Metrics
  totalTasks: number;
  completedTasks: number;
  runningTasks: number;
  failedTasks: number;
}

// src/lib/state/store.ts

import { WorkflowRun, TaskNode, AgentAction, Resource } from './types';

/**
 * In-memory state store for active workflow runs.
 * 
 * This is intentionally simple - the dashboard is a diagnostic tool,
 * not a database of record. The Python backend + DB is the source of truth.
 */
class DashboardStore {
  private runs: Map<string, WorkflowRun> = new Map();
  private listeners: Set<(runId: string, event: string) => void> = new Set();
  
  // === Queries ===
  
  getRun(runId: string): WorkflowRun | undefined {
    return this.runs.get(runId);
  }
  
  getAllRuns(): WorkflowRun[] {
    return Array.from(this.runs.values());
  }
  
  getActiveRuns(): WorkflowRun[] {
    return this.getAllRuns().filter(r => r.status === 'running');
  }
  
  getTask(runId: string, taskId: string): TaskNode | undefined {
    return this.runs.get(runId)?.tasks.get(taskId);
  }
  
  getTasksAtLevel(runId: string, level: number): TaskNode[] {
    const run = this.runs.get(runId);
    if (!run) return [];
    return Array.from(run.tasks.values()).filter(t => t.level === level);
  }
  
  getActionsForTask(runId: string, taskId: string): AgentAction[] {
    return this.runs.get(runId)?.actionsByTask.get(taskId) ?? [];
  }
  
  getResourcesForTask(runId: string, taskId: string): Resource[] {
    return this.runs.get(runId)?.resourcesByTask.get(taskId) ?? [];
  }
  
  // === Mutations (called by Inngest event handlers) ===
  
  initializeRun(
    runId: string,
    experimentId: string,
    name: string,
    taskTree: Record<string, unknown>,
    startedAt: string,
  ): void {
    const tasks = this.parseTaskTree(taskTree);
    const rootTaskId = taskTree.id as string;
    
    this.runs.set(runId, {
      id: runId,
      experimentId,
      name,
      status: 'running',
      tasks,
      rootTaskId,
      actionsByTask: new Map(),
      resourcesByTask: new Map(),
      startedAt,
      completedAt: null,
      durationSeconds: null,
      totalTasks: tasks.size,
      completedTasks: 0,
      runningTasks: 0,
      failedTasks: 0,
    });
    
    this.notify(runId, 'workflow.started');
  }
  
  updateTaskStatus(
    runId: string,
    taskId: string,
    status: TaskStatus,
    workerId?: string,
    workerName?: string,
    timestamp?: string,
  ): void {
    const run = this.runs.get(runId);
    const task = run?.tasks.get(taskId);
    if (!run || !task) return;
    
    const oldStatus = task.status;
    task.status = status;
    
    if (workerId) task.assignedWorkerId = workerId;
    if (workerName) task.assignedWorkerName = workerName;
    if (status === 'running' && timestamp) task.startedAt = timestamp;
    if ((status === 'completed' || status === 'failed') && timestamp) {
      task.completedAt = timestamp;
    }
    
    // Update run metrics
    this.recalculateRunMetrics(run);
    
    this.notify(runId, 'task.status_changed');
  }
  
  addAction(runId: string, action: AgentAction): void {
    const run = this.runs.get(runId);
    if (!run) return;
    
    const taskActions = run.actionsByTask.get(action.taskId) ?? [];
    
    // Update or append
    const existingIndex = taskActions.findIndex(a => a.id === action.id);
    if (existingIndex >= 0) {
      taskActions[existingIndex] = action;
    } else {
      taskActions.push(action);
    }
    
    run.actionsByTask.set(action.taskId, taskActions);
    this.notify(runId, 'action.updated');
  }
  
  addResource(runId: string, resource: Resource): void {
    const run = this.runs.get(runId);
    if (!run) return;
    
    const taskResources = run.resourcesByTask.get(resource.taskId) ?? [];
    taskResources.push(resource);
    run.resourcesByTask.set(resource.taskId, taskResources);
    
    this.notify(runId, 'resource.published');
  }
  
  completeRun(runId: string, status: 'completed' | 'failed', completedAt: string): void {
    const run = this.runs.get(runId);
    if (!run) return;
    
    run.status = status;
    run.completedAt = completedAt;
    run.durationSeconds = 
      (new Date(completedAt).getTime() - new Date(run.startedAt).getTime()) / 1000;
    
    this.notify(runId, 'workflow.completed');
  }
  
  // === Helpers ===
  
  private parseTaskTree(
    tree: Record<string, unknown>,
    parentId: string | null = null,
    level: number = 1,
  ): Map<string, TaskNode> {
    const tasks = new Map<string, TaskNode>();
    
    const node: TaskNode = {
      id: tree.id as string,
      name: tree.name as string,
      description: (tree.description as string) ?? '',
      parentId,
      childIds: ((tree.children as unknown[]) ?? []).map((c: any) => c.id),
      dependsOnIds: ((tree.depends_on as string[]) ?? []),
      status: 'pending',
      assignedWorkerId: null,
      assignedWorkerName: null,
      startedAt: null,
      completedAt: null,
      isLeaf: !tree.children || (tree.children as unknown[]).length === 0,
      level,
    };
    
    tasks.set(node.id, node);
    
    // Recurse for children
    for (const child of (tree.children as Record<string, unknown>[]) ?? []) {
      const childTasks = this.parseTaskTree(child, node.id, level + 1);
      childTasks.forEach((v, k) => tasks.set(k, v));
    }
    
    return tasks;
  }
  
  private recalculateRunMetrics(run: WorkflowRun): void {
    let completed = 0, running = 0, failed = 0;
    
    for (const task of run.tasks.values()) {
      if (task.status === 'completed') completed++;
      else if (task.status === 'running') running++;
      else if (task.status === 'failed') failed++;
    }
    
    run.completedTasks = completed;
    run.runningTasks = running;
    run.failedTasks = failed;
  }
  
  // === Subscriptions ===
  
  subscribe(listener: (runId: string, event: string) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  
  private notify(runId: string, event: string): void {
    this.listeners.forEach(fn => fn(runId, event));
  }
}

export const store = new DashboardStore();
```

### 3.3 Inngest Functions (Event Subscribers)

```typescript
// src/inngest/client.ts

import { Inngest } from 'inngest';

export const inngest = new Inngest({
  id: 'arcane-dashboard',
});


// src/inngest/functions/workflow-events.ts

import { inngest } from '../client';
import { store } from '@/lib/state/store';
import { broadcast } from '@/lib/ws/broadcast';

export const onWorkflowStarted = inngest.createFunction(
  { id: 'dashboard-workflow-started' },
  { event: 'dashboard/workflow.started' },
  async ({ event }) => {
    const { run_id, experiment_id, workflow_name, task_tree, started_at } = event.data;
    
    // Update in-memory state
    store.initializeRun(run_id, experiment_id, workflow_name, task_tree, started_at);
    
    // Broadcast to connected WebSocket clients
    broadcast(run_id, {
      type: 'workflow.started',
      runId: run_id,
      data: store.getRun(run_id),
    });
  }
);

export const onWorkflowCompleted = inngest.createFunction(
  { id: 'dashboard-workflow-completed' },
  { event: 'dashboard/workflow.completed' },
  async ({ event }) => {
    const { run_id, status, completed_at } = event.data;
    
    store.completeRun(run_id, status, completed_at);
    
    broadcast(run_id, {
      type: 'workflow.completed',
      runId: run_id,
      data: { status, completedAt: completed_at },
    });
  }
);


// src/inngest/functions/task-events.ts

import { inngest } from '../client';
import { store } from '@/lib/state/store';
import { broadcast } from '@/lib/ws/broadcast';

export const onTaskStatusChanged = inngest.createFunction(
  { id: 'dashboard-task-status-changed' },
  { event: 'dashboard/task.status_changed' },
  async ({ event }) => {
    const {
      run_id,
      task_id,
      new_status,
      assigned_worker_id,
      assigned_worker_name,
      timestamp,
    } = event.data;
    
    store.updateTaskStatus(
      run_id,
      task_id,
      new_status,
      assigned_worker_id,
      assigned_worker_name,
      timestamp,
    );
    
    broadcast(run_id, {
      type: 'task.status_changed',
      runId: run_id,
      taskId: task_id,
      data: {
        status: new_status,
        workerId: assigned_worker_id,
        workerName: assigned_worker_name,
      },
    });
  }
);


// src/inngest/functions/action-events.ts

import { inngest } from '../client';
import { store } from '@/lib/state/store';
import { broadcast } from '@/lib/ws/broadcast';
import { AgentAction } from '@/lib/state/types';

export const onAgentActionStarted = inngest.createFunction(
  { id: 'dashboard-action-started' },
  { event: 'dashboard/agent.action_started' },
  async ({ event }) => {
    const {
      run_id,
      task_id,
      action_id,
      worker_id,
      worker_name,
      action_type,
      action_input,
      timestamp,
    } = event.data;
    
    const action: AgentAction = {
      id: action_id,
      taskId: task_id,
      workerId: worker_id,
      workerName: worker_name,
      type: action_type,
      input: action_input,
      output: null,
      status: 'started',
      startedAt: timestamp,
      completedAt: null,
      durationMs: null,
      error: null,
    };
    
    store.addAction(run_id, action);
    
    broadcast(run_id, {
      type: 'action.started',
      runId: run_id,
      taskId: task_id,
      data: action,
    });
  }
);

export const onAgentActionCompleted = inngest.createFunction(
  { id: 'dashboard-action-completed' },
  { event: 'dashboard/agent.action_completed' },
  async ({ event }) => {
    const {
      run_id,
      task_id,
      action_id,
      worker_id,
      action_type,
      action_output,
      duration_ms,
      success,
      error,
      timestamp,
    } = event.data;
    
    // Get existing action and update it
    const existingActions = store.getActionsForTask(run_id, task_id);
    const existing = existingActions.find(a => a.id === action_id);
    
    if (existing) {
      const updated: AgentAction = {
        ...existing,
        output: action_output,
        status: success ? 'completed' : 'failed',
        completedAt: timestamp,
        durationMs: duration_ms,
        error,
      };
      
      store.addAction(run_id, updated);
      
      broadcast(run_id, {
        type: 'action.completed',
        runId: run_id,
        taskId: task_id,
        data: updated,
      });
    }
  }
);


// src/inngest/functions/resource-events.ts

import { inngest } from '../client';
import { store } from '@/lib/state/store';
import { broadcast } from '@/lib/ws/broadcast';
import { Resource } from '@/lib/state/types';

export const onResourcePublished = inngest.createFunction(
  { id: 'dashboard-resource-published' },
  { event: 'dashboard/resource.published' },
  async ({ event }) => {
    const {
      run_id,
      task_id,
      resource_id,
      resource_name,
      mime_type,
      size_bytes,
      preview_text,
      file_path,
      timestamp,
    } = event.data;
    
    const resource: Resource = {
      id: resource_id,
      taskId: task_id,
      name: resource_name,
      mimeType: mime_type,
      sizeBytes: size_bytes,
      previewText: preview_text,
      filePath: file_path,
      createdAt: timestamp,
    };
    
    store.addResource(run_id, resource);
    
    broadcast(run_id, {
      type: 'resource.published',
      runId: run_id,
      taskId: task_id,
      data: resource,
    });
  }
);
```

### 3.4 WebSocket Server

```typescript
// src/lib/ws/broadcast.ts

import { WebSocket } from 'ws';

/**
 * WebSocket connection manager.
 * 
 * Clients subscribe to specific run IDs. When an event occurs for that run,
 * we broadcast to all subscribed clients.
 */

// Map: runId -> Set of WebSocket connections
const subscriptions = new Map<string, Set<WebSocket>>();

// All connections (for global broadcasts)
const allConnections = new Set<WebSocket>();

export function registerConnection(ws: WebSocket): void {
  allConnections.add(ws);
  
  ws.on('close', () => {
    allConnections.delete(ws);
    // Remove from all subscriptions
    subscriptions.forEach((sockets) => sockets.delete(ws));
  });
  
  ws.on('message', (data) => {
    try {
      const msg = JSON.parse(data.toString());
      
      if (msg.type === 'subscribe' && msg.runId) {
        subscribe(ws, msg.runId);
      } else if (msg.type === 'unsubscribe' && msg.runId) {
        unsubscribe(ws, msg.runId);
      }
    } catch (e) {
      // Ignore malformed messages
    }
  });
}

export function subscribe(ws: WebSocket, runId: string): void {
  if (!subscriptions.has(runId)) {
    subscriptions.set(runId, new Set());
  }
  subscriptions.get(runId)!.add(ws);
}

export function unsubscribe(ws: WebSocket, runId: string): void {
  subscriptions.get(runId)?.delete(ws);
}

export function broadcast(runId: string, message: unknown): void {
  const sockets = subscriptions.get(runId);
  if (!sockets) return;
  
  const payload = JSON.stringify(message);
  
  for (const ws of sockets) {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(payload);
    }
  }
}

export function broadcastAll(message: unknown): void {
  const payload = JSON.stringify(message);
  
  for (const ws of allConnections) {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(payload);
    }
  }
}
```

### 3.7 File Location Summary (Part 3)

All Next.js code goes in `arcane-dashboard/`:

| File | Purpose | Section |
|------|---------|---------|
| `src/lib/state/types.ts` | TypeScript interfaces (`WorkflowRun`, `TaskNode`, etc.) | 3.2 |
| `src/lib/state/store.ts` | `DashboardStore` class (in-memory state) | 3.3 |
| `src/inngest/client.ts` | Inngest client configuration | 3.4 |
| `src/inngest/functions/workflow-events.ts` | `onWorkflowStarted`, `onWorkflowCompleted` handlers | 3.4 |
| `src/inngest/functions/task-events.ts` | `onTaskStatusChanged`, `onTaskAssigned` handlers | 3.4 |
| `src/inngest/functions/action-events.ts` | `onAgentActionStarted`, `onAgentActionCompleted` handlers | 3.4 |
| `src/inngest/index.ts` | Export all Inngest functions | 3.4 |
| `src/app/api/inngest/route.ts` | Inngest webhook endpoint | 3.4 |
| `src/lib/ws/server.ts` | WebSocket server setup | 3.5 |
| `src/lib/ws/broadcast.ts` | `broadcastToRun()`, `broadcastAll()` helpers | 3.6 |
| `src/app/api/ws/route.ts` | WebSocket upgrade endpoint | 3.5 |

**Also create:**

| File | Purpose |
|------|---------|
| `package.json` | Dependencies: `next`, `react`, `tailwindcss`, `react-flow`, `inngest`, `ws` |
| `next.config.js` | Next.js configuration |
| `tailwind.config.ts` | Tailwind configuration |
| `tsconfig.json` | TypeScript configuration |
| `Dockerfile` | Container build for dashboard |
| `src/app/layout.tsx` | Root layout with providers |
| `src/app/page.tsx` | Home page (run list) |
| `src/app/run/[runId]/page.tsx` | DAG view for a run |

---

## Part 4: Frontend Components

### 4.1 DAG Visualization

The DAG view is the core of the dashboard. It should:

1. **Show hierarchical levels** - L1 (root), L2 (children), L3 (grandchildren)
2. **Highlight active nodes** - Running tasks pulse, completed are green, failed are red
3. **Show dependencies** - Edges between dependent tasks
4. **Be interactive** - Click to drill into task details

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           DAG View                                          │
│                                                                            │
│  Level Selector: [L1] [L2] [L3 ▼]                    Search: [________]    │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                     │   │
│  │                    ┌─────────────┐                                  │   │
│  │                    │ Root Task   │ ← L1                             │   │
│  │                    │ ✓ completed │                                  │   │
│  │                    └──────┬──────┘                                  │   │
│  │              ┌────────────┼────────────┐                            │   │
│  │              ▼            ▼            ▼                            │   │
│  │        ┌─────────┐  ┌─────────┐  ┌─────────┐                        │   │
│  │        │ Task A  │  │ Task B  │  │ Task C  │ ← L2                   │   │
│  │        │ ✓       │  │ ⟳ run   │  │ ○ pend  │                        │   │
│  │        └────┬────┘  └────┬────┘  └─────────┘                        │   │
│  │             │            │                                          │   │
│  │        ┌────┴────┐  ┌────┴────┐                                     │   │
│  │        ▼         ▼  ▼         ▼                                     │   │
│  │   ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐                           │   │
│  │   │ A.1   │ │ A.2   │ │ B.1   │ │ B.2   │ ← L3                      │   │
│  │   │ ✓     │ │ ✓     │ │ ⟳     │ │ ○     │                           │   │
│  │   └───────┘ └───────┘ └───────┘ └───────┘                           │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  Running: 2 │ Completed: 4 │ Pending: 2 │ Failed: 0                        │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Task Detail Panel

When a task node is clicked, show details in a side panel:

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Task Details: "Draft Prospectus"                               [×] Close  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  Status: ⟳ Running           Started: 2 mins ago                           │
│  Assigned: analyst_worker    Model: gpt-4o                                 │
│                                                                            │
│  ─────────────────────────────────────────────────────────────────────────│
│                                                                            │
│  📝 Description                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ Write the IPO prospectus document based on the gathered financial   │ │
│  │ data and legal review results.                                      │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ─────────────────────────────────────────────────────────────────────────│
│                                                                            │
│  ⚡ Action Stream (live)                                    [Expand ↗]     │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ 14:23:01  🔧 read_file("financial_data.json")           ✓ 234ms     │ │
│  │ 14:23:05  🔧 read_file("legal_review.md")               ✓ 156ms     │ │
│  │ 14:23:08  🔧 write_file("prospectus_draft.docx")        ⟳ ...       │ │
│  │           └─ Writing section 3 of 8...                              │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ─────────────────────────────────────────────────────────────────────────│
│                                                                            │
│  📦 Resources                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │  Inputs:                                                            │ │
│  │   • financial_data.json (12.4 KB)                                   │ │
│  │   • legal_review.md (8.2 KB)                                        │ │
│  │                                                                     │ │
│  │  Outputs:                                                           │ │
│  │   • prospectus_draft.docx (in progress...)                          │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ─────────────────────────────────────────────────────────────────────────│
│                                                                            │
│  📊 Dependencies                                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │  Waiting on:                                                        │ │
│  │   ✓ Gather Financial Data (completed)                               │ │
│  │   ✓ Legal Review (completed)                                        │ │
│  │                                                                     │ │
│  │  Blocking:                                                          │ │
│  │   ○ Final Review (pending)                                          │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Action Stream Panel

Full action history for a task, expandable from the detail panel:

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Action Stream: "Draft Prospectus"                      Filter: [All ▼]    │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ 14:23:01  🔧 read_file                                    ✓ 234ms   │ │
│  │ ├─ Input:  {"path": "financial_data.json"}                          │ │
│  │ └─ Output: {"content": "{ \"revenue\": 1234567, ...}", "size": 12400}│ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ 14:23:05  🔧 read_file                                    ✓ 156ms   │ │
│  │ ├─ Input:  {"path": "legal_review.md"}                              │ │
│  │ └─ Output: {"content": "# Legal Review\n\n## Compliance...", ...}   │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ 14:23:08  🔧 write_file                                   ⟳ running │ │
│  │ ├─ Input:  {"path": "prospectus_draft.docx", "content": "..."}      │ │
│  │ └─ Output: (in progress)                                            │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ 14:22:58  💭 thinking                                     ✓ 2100ms  │ │
│  │ └─ "I need to read the financial data and legal review first,       │ │
│  │    then structure the prospectus according to SEC guidelines..."    │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 4.4 Run List Panel

Home page showing all runs:

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Workflow Runs                                          Search: [________] │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  Active (2)                                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ ⟳ IPO Preparation                                                   │ │
│  │   run_abc123 • Started 5m ago • 4/8 tasks complete                  │ │
│  │   [View DAG →]                                                      │ │
│  ├──────────────────────────────────────────────────────────────────────┤ │
│  │ ⟳ Research Project                                                  │ │
│  │   run_def456 • Started 12m ago • 2/5 tasks complete                 │ │
│  │   [View DAG →]                                                      │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  Recent (showing 10)                                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ ✓ Financial Memo                                                    │ │
│  │   run_ghi789 • Completed 1h ago • Score: 0.87 • Duration: 4m 23s    │ │
│  ├──────────────────────────────────────────────────────────────────────┤ │
│  │ ✗ Data Analysis                                                     │ │
│  │   run_jkl012 • Failed 2h ago • Error: Timeout                       │ │
│  ├──────────────────────────────────────────────────────────────────────┤ │
│  │ ✓ Literature Review                                                 │ │
│  │   run_mno345 • Completed 3h ago • Score: 0.92 • Duration: 12m 45s   │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 4.5 Component Library

Key React components to build:

| Component | Props | Purpose |
|-----------|-------|---------|
| `<DAGCanvas>` | `run: WorkflowRun`, `selectedLevel: number` | Main DAG visualization using react-flow or dagre |
| `<TaskNode>` | `task: TaskNode`, `onClick` | Individual node in DAG with status indicator |
| `<TaskEdge>` | `from: string`, `to: string` | Dependency edge (can show satisfied/unsatisfied) |
| `<LevelSelector>` | `levels: number[]`, `selected`, `onChange` | Tabs for L1/L2/L3 navigation |
| `<StatusBadge>` | `status: TaskStatus` | Colored badge (green/yellow/red/gray) |
| `<TaskDetailPanel>` | `runId`, `taskId` | Slide-out panel with task info |
| `<ActionStreamPanel>` | `runId`, `taskId` | Scrollable action list with live updates |
| `<ResourcePanel>` | `resources: Resource[]` | List of input/output resources |
| `<RunListPanel>` | `runs: WorkflowRun[]` | Home page run list |
| `<SearchInput>` | `onSearch` | Search tasks by name |
| `<TimeAgo>` | `timestamp: string` | "2 mins ago" relative time display |

### 4.4 File Location Summary (Part 4)

All frontend components go in `arcane-dashboard/src/components/`:

| File | Purpose |
|------|---------|
| `dag/DAGCanvas.tsx` | Main react-flow canvas for DAG visualization |
| `dag/TaskNode.tsx` | Custom node component for tasks |
| `dag/TaskEdge.tsx` | Custom edge component for dependencies |
| `dag/LevelSelector.tsx` | L1/L2/L3 navigation tabs |
| `panels/TaskDetailPanel.tsx` | Slide-out panel with task info |
| `panels/ActionStreamPanel.tsx` | Live action list within task detail |
| `panels/ResourcePanel.tsx` | Input/output resource list |
| `panels/SandboxPanel.tsx` | E2B sandbox metrics and commands |
| `panels/RunListPanel.tsx` | Home page run list |
| `common/StatusBadge.tsx` | Colored status indicator (pending/running/completed/failed) |
| `common/SearchInput.tsx` | Search/filter input |
| `common/TimeAgo.tsx` | Relative time display |
| `common/LoadingSpinner.tsx` | Loading indicator |
| `providers/WebSocketProvider.tsx` | React context for WebSocket connection |

**Hooks** go in `arcane-dashboard/src/hooks/`:

| File | Purpose |
|------|---------|
| `useWebSocket.ts` | WebSocket connection management |
| `useRunState.ts` | Subscribe to run updates |
| `useTaskDetails.ts` | Get task with actions/resources |

---

## Part 5: E2B Sandbox Integration

### 5.1 Using e2b_sandbox_inspector

You already have [e2b_sandbox_inspector](https://github.com/cm2435/e2b_sandbox_inspector) which provides:

- List running sandboxes
- Get sandbox metrics (CPU, memory, disk)
- Execute commands
- List/download files
- Kill sandboxes

### 5.2 Integration Approach

**Option A: Emit sandbox events from Python (Recommended)**

Add event emission in the sandbox wrapper:

```python
# h_arcane/_internal/infrastructure/sandbox.py

from h_arcane._internal.dashboard.emitter import dashboard_emitter

class SandboxWrapper:
    async def create(self, template_id: str, run_id: str) -> Sandbox:
        sandbox = await Sandbox.create(template_id)
        
        # Emit for dashboard
        await dashboard_emitter.sandbox_created(
            run_id=run_id,
            sandbox_id=sandbox.id,
            template_id=template_id,
        )
        
        return sandbox
    
    async def run_command(self, sandbox: Sandbox, command: str, run_id: str) -> CommandResult:
        start = time.time()
        result = await sandbox.commands.run(command)
        duration_ms = int((time.time() - start) * 1000)
        
        # Emit for dashboard
        await dashboard_emitter.sandbox_command(
            run_id=run_id,
            sandbox_id=sandbox.id,
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            duration_ms=duration_ms,
        )
        
        return result
```

**Option B: Dashboard polls sandbox API directly**

Add an API route in the Next.js dashboard that uses `e2b_sandbox_inspector`:

```typescript
// src/app/api/sandbox/[sandboxId]/route.ts

import { NextResponse } from 'next/server';

// This would require running a Python subprocess or having a Python sidecar
// Less ideal than Option A
```

**Recommendation:** Option A - emit events from Python. The dashboard stays event-driven and consistent.

### 5.3 Sandbox Panel in Dashboard

Add a "Sandbox" tab in the task detail panel for tasks with active sandboxes:

```
┌────────────────────────────────────────────────────────────────────────────┐
│  🖥️ Sandbox: sbx_abc123                                                    │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  Status: Running          Template: gdp-eval-sandbox                       │
│  Uptime: 4m 23s           Time Remaining: 55m 37s                         │
│                                                                            │
│  ─────────────────────────────────────────────────────────────────────────│
│                                                                            │
│  📊 Metrics                                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │  CPU:    ████████░░░░░░░░  42%                                      │ │
│  │  Memory: ██████░░░░░░░░░░  38% (768 MB / 2 GB)                       │ │
│  │  Disk:   ████░░░░░░░░░░░░  25% (2.5 GB / 10 GB)                      │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ─────────────────────────────────────────────────────────────────────────│
│                                                                            │
│  📁 Files: /workspace                                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │  📄 financial_data.json      12.4 KB                                │ │
│  │  📄 legal_review.md           8.2 KB                                │ │
│  │  📄 prospectus_draft.docx    24.1 KB  (modified 30s ago)            │ │
│  │  📁 templates/                                                      │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ─────────────────────────────────────────────────────────────────────────│
│                                                                            │
│  🖥️ Recent Commands                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │  14:23:01  python process_data.py     exit: 0    234ms              │ │
│  │  14:23:05  cat output.json            exit: 0     12ms              │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 6: Docker Compose Setup

### 6.1 Service Configuration

```yaml
# docker-compose.yml

version: '3.8'

services:
  # === Existing services ===
  
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: arcane
      POSTGRES_PASSWORD: arcane
      POSTGRES_DB: arcane
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
  
  inngest-dev:
    image: inngest/inngest:latest
    command: dev -u http://arcane-api:8000/api/inngest -u http://arcane-dashboard:3000/api/inngest
    ports:
      - "8288:8288"  # Inngest dev server UI
    depends_on:
      - arcane-api
      - arcane-dashboard
  
  arcane-api:
    build:
      context: .
      dockerfile: Dockerfile.api
    environment:
      DATABASE_URL: postgresql://arcane:arcane@postgres:5432/arcane
      INNGEST_DEV: "true"
      E2B_API_KEY: ${E2B_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    ports:
      - "8000:8000"
    depends_on:
      - postgres
    volumes:
      - ./h_arcane:/app/h_arcane
  
  # === NEW: Dashboard service ===
  
  arcane-dashboard:
    build:
      context: ./arcane-dashboard
      dockerfile: Dockerfile
    environment:
      INNGEST_EVENT_KEY: ${INNGEST_EVENT_KEY:-}
      INNGEST_SIGNING_KEY: ${INNGEST_SIGNING_KEY:-}
      NEXT_PUBLIC_WS_URL: ws://localhost:3000/api/ws
      NEXT_PUBLIC_API_URL: http://localhost:8000
    ports:
      - "3000:3000"
    depends_on:
      - arcane-api

volumes:
  postgres_data:
```

### 6.2 Dashboard Dockerfile

```dockerfile
# arcane-dashboard/Dockerfile

FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy source
COPY . .

# Build
RUN npm run build

# Production image
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Copy built assets
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
```

### 6.3 Next.js Configuration

```javascript
// arcane-dashboard/next.config.js

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  
  // Enable WebSocket support
  experimental: {
    serverActions: true,
  },
  
  // Proxy API requests to arcane-api in dev
  async rewrites() {
    return [
      {
        source: '/api/arcane/:path*',
        destination: 'http://localhost:8000/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
```

---

## Part 7: Implementation Roadmap

### Phase 0: Smoke Test Benchmark (1-2 days) ⭐ START HERE

**Goal:** Create the test harness that validates the entire pipeline before building UI

**Files to create:**
- `h_arcane/benchmarks/smoke_test/__init__.py`
- `h_arcane/benchmarks/smoke_test/dummy_worker.py`
- `h_arcane/benchmarks/smoke_test/stub_tools.py`
- `h_arcane/benchmarks/smoke_test/workflows.py`
- `h_arcane/benchmarks/smoke_test/cli.py`

**Tasks:**
- [ ] Implement `DummyWorker` class (implements `BaseWorker` protocol)
- [ ] Implement stub tools (`stub_read_file`, `stub_write_file`, `stub_analyze_data`)
- [ ] Create test workflows (single, linear, parallel, nested)
- [ ] Create CLI with `list` and `run` commands
- [ ] Test that `execute_task()` works with DummyWorker
- [ ] Verify workflows persist to PostgreSQL correctly
- [ ] Verify task status transitions work

**Exit criteria:** Can run `python -m h_arcane.benchmarks.smoke_test.cli run --all` and see runs in DB.

### Phase 1: Python Event Emission (1-2 days)

**Goal:** Emit all necessary events from h_arcane

**Files to create:**
- `h_arcane/_internal/dashboard/__init__.py`
- `h_arcane/_internal/dashboard/events.py` (event constants and payloads)
- `h_arcane/_internal/dashboard/emitter.py` (DashboardEmitter class)

**Tasks:**
- [ ] Define all event schemas
- [ ] Create DashboardEmitter class
- [ ] Add emission points in `runner.py` (workflow start/complete)
- [ ] Add emission points in `_internal/inngest/task_functions.py` (task status)
- [ ] Add emission points in worker execution (actions)
- [ ] Add emission points in resource persistence
- [ ] Add emission points in sandbox wrapper
- [ ] Wire up DummyWorker to emit action events
- [ ] Test events appear in Inngest dev server

**Exit criteria:** Run smoke test → events visible in Inngest dev server UI (http://localhost:8288).

### Phase 2: Next.js Project Setup (1 day)

**Goal:** Scaffold the dashboard application

**Tasks:**
- [ ] Create `arcane-dashboard/` directory
- [ ] Initialize Next.js 14 with App Router
- [ ] Configure Tailwind CSS
- [ ] Set up Inngest client
- [ ] Create Dockerfile
- [ ] Add to docker-compose.yml
- [ ] Verify Inngest receives events from Python

**Exit criteria:** Dashboard container starts, Inngest functions receive Python events.

### Phase 3: State Management & WebSocket (1-2 days)

**Goal:** Build the backend-for-frontend layer

**Files to create:**
- `src/lib/state/types.ts`
- `src/lib/state/store.ts`
- `src/lib/ws/broadcast.ts`
- `src/inngest/functions/*.ts`

**Tasks:**
- [ ] Define TypeScript types for state
- [ ] Implement DashboardStore class
- [ ] Implement WebSocket server
- [ ] Create Inngest subscriber functions
- [ ] Wire up: event → store → WebSocket broadcast
- [ ] Test with smoke test workflows

**Exit criteria:** Run smoke test → state updates in dashboard store → WebSocket broadcasts.

### Phase 4: Core UI Components (2-3 days)

**Goal:** Build the main visualization components

**Components to build:**
- [ ] `<DAGCanvas>` - Main DAG view (use react-flow or custom)
- [ ] `<TaskNode>` - Node with status indicator
- [ ] `<LevelSelector>` - L1/L2/L3 tabs
- [ ] `<StatusBadge>` - Status indicator
- [ ] `<RunListPanel>` - Home page
- [ ] Basic layout and navigation

**Exit criteria:** Can see DAG visualization of nested smoke test workflow.

### Phase 5: Detail Panels (1-2 days)

**Goal:** Build interactive detail views

**Components to build:**
- [ ] `<TaskDetailPanel>` - Slide-out task details
- [ ] `<ActionStreamPanel>` - Live action list
- [ ] `<ResourcePanel>` - Input/output resources
- [ ] WebSocket integration for live updates

**Exit criteria:** Click task node → see live action stream for DummyWorker.

### Phase 6: E2B Integration (1 day)

**Goal:** Add sandbox visibility

**Tasks:**
- [ ] Emit sandbox events from Python
- [ ] Add sandbox panel to task details
- [ ] Display metrics, files, commands

**Exit criteria:** Sandbox panel shows mock data (or real E2B if available).

### Phase 7: Polish & Testing (1-2 days)

**Goal:** Production-ready dashboard

**Tasks:**
- [ ] Add search/filter functionality
- [ ] Responsive design tweaks
- [ ] Error handling and loading states
- [ ] E2E test with all smoke test workflows
- [ ] Documentation

**Exit criteria:** All smoke test workflows run cleanly, dashboard shows everything.

### Timeline Summary

| Phase | Days | Deliverable |
|-------|------|-------------|
| **0: Smoke Test** | 1-2 | DummyWorker + test workflows + CLI |
| **1: Event Emission** | 1-2 | Dashboard events emitting from Python |
| **2: Next.js Setup** | 1 | Dashboard container receiving events |
| **3: State & WebSocket** | 1-2 | Event → Store → WebSocket pipeline |
| **4: Core UI** | 2-3 | DAG visualization working |
| **5: Detail Panels** | 1-2 | Task details with action stream |
| **6: E2B Integration** | 1 | Sandbox panel |
| **7: Polish** | 1-2 | Production ready |
| **TOTAL** | ~10-14 days | Full diagnostic dashboard |

---

## Part 8: Action Data Flow

### 8.1 How Actions Get to the Dashboard

The smoke test (and all benchmarks) use the **existing action recording infrastructure**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Action Data Flow                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ReActWorker                                                                │
│      │                                                                      │
│      │  1. Runner.run() executes agent                                      │
│      ▼                                                                      │
│  log_actions_from_result()  (existing in tracing.py)                        │
│      │                                                                      │
│      │  2. Extracts actions from RunResult                                  │
│      │  3. Writes to PostgreSQL Action table                                │
│      ▼                                                                      │
│  PostgreSQL (SSoT)                                                          │
│      │                                                                      │
│      │  4. On write, emit dashboard event                                   │
│      ▼                                                                      │
│  dashboard_emitter.agent_action_completed()                                 │
│      │                                                                      │
│      │  5. Inngest event to dashboard                                       │
│      ▼                                                                      │
│  Dashboard (real-time update)                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 What We Need to Add

The existing `log_actions_from_result()` already writes to PostgreSQL. We just need to:

1. **Emit dashboard events** after writing to PG (add calls to `dashboard_emitter`)
2. **Dashboard reads from PG** for action history (SSoT)
3. **WebSocket for live updates** (dashboard events push new actions)

### 8.3 Key Principle

**PostgreSQL is the source of truth.** Dashboard events are for real-time updates only.

When a user opens a task detail panel:
1. Fetch existing actions from PG API (complete history)
2. Subscribe to WebSocket for new actions (live updates)

---

## Part 9: Open Questions

### 9.1 Historical Runs

The current plan focuses on active runs. For historical runs:

| Option | Pros | Cons |
|--------|------|------|
| **Query DB directly** | Complete data, already stored | Requires API endpoint, more complexity |
| **Keep recent in memory** | Simple, fast | Lost on restart, memory limits |
| **Hybrid** | Best of both | More code |

**Recommendation:** Start with in-memory for active runs. Add DB query for historical as a follow-up.

### 9.2 DAG Library Choice

Options for DAG visualization:

| Library | Pros | Cons |
|---------|------|------|
| **react-flow** | Mature, customizable, handles layout | Large bundle, learning curve |
| **dagre + custom SVG** | Full control, smaller | More work |
| **vis.js** | Powerful | Heavier, less React-native |

**Recommendation:** Start with react-flow - it handles the hard parts (layout, zoom, pan) well.

### 8.3 Action Streaming Frequency

Agent actions can be high-frequency. Consider:

- **Batching:** Buffer events and send every 100ms
- **Throttling:** Rate-limit per task
- **Compression:** Truncate large outputs in preview

**Recommendation:** Start without optimization, add batching if performance issues arise.

---

## Appendix A: Event Reference

| Event | Trigger Point | Key Data |
|-------|---------------|----------|
| `dashboard/workflow.started` | `execute_task()` called | task_tree, total_tasks |
| `dashboard/workflow.completed` | All tasks done | status, duration, score |
| `dashboard/task.status_changed` | Any status transition | old_status, new_status, worker |
| `dashboard/task.assigned` | Worker picks up task | worker_id, worker_name |
| `dashboard/agent.action_started` | Before tool call | action_type, input |
| `dashboard/agent.action_completed` | After tool call | output, duration, success |
| `dashboard/agent.thinking` | Streaming thought | content, is_complete |
| `dashboard/resource.published` | Output file created | name, mime_type, preview |
| `dashboard/sandbox.created` | Sandbox spun up | sandbox_id, template |
| `dashboard/sandbox.command` | Command executed | command, stdout, exit_code |
| `dashboard/sandbox.closed` | Sandbox terminated | reason |

---

## Appendix B: UI Mockup Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  H-ARCANE Dashboard                                    [Active: 2] [⚙️]     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────┐  ┌─────────────────────────────────────────┐   │
│  │                         │  │                                         │   │
│  │     Run List Panel      │  │           DAG Canvas                    │   │
│  │                         │  │                                         │   │
│  │  ⟳ IPO Preparation      │  │     ┌───┐                               │   │
│  │  ⟳ Research Project     │  │     │ A │                               │   │
│  │  ──────────────────     │  │     └─┬─┘                               │   │
│  │  ✓ Financial Memo       │  │    ┌──┴──┐                              │   │
│  │  ✗ Data Analysis        │  │  ┌─┴─┐ ┌─┴─┐                            │   │
│  │  ✓ Literature Review    │  │  │ B │ │ C │                            │   │
│  │                         │  │  └───┘ └───┘                            │   │
│  │                         │  │                                         │   │
│  └─────────────────────────┘  └─────────────────────────────────────────┘   │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     Task Detail Panel (collapsible)                   │  │
│  │                                                                       │  │
│  │  Task B │ Status: ⟳ Running │ Worker: analyst │ Actions: 3           │  │
│  │  ───────────────────────────────────────────────────────────────────  │  │
│  │  14:23:01  read_file(...)  ✓ 234ms                                   │  │
│  │  14:23:05  read_file(...)  ✓ 156ms                                   │  │
│  │  14:23:08  write_file(...) ⟳ running                                 │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```
