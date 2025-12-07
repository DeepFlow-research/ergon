# Experiment Layout

How to run the 200 GDPEval experiments systematically.

**Scope: ReAct Baseline Only**

---

## GDPEval Data

### Self-Contained Data Structure

All GDPEval data is copied into the plan folder for self-containment:

```
paper_code_structure_plans/
├── data/                           # Self-contained GDPEval data
│   ├── raw/
│   │   ├── gdpeval.parquet         # Original task data
│   │   ├── metadata.json
│   │   └── reference_files/        # 262 input files (xlsx, pdf, docx)
│   └── generated/
│       └── staged_v2/
│           ├── staged_rubrics.jsonl  # Nested rubrics for each task
│           ├── train_rubrics.jsonl   # Train split
│           └── eval_rubrics.jsonl    # Eval split
└── schemas/                        # Local schema copies
    └── staged_rubric_schema.py     # StagedRubric, GDPEvalStagedRubric
```

### Setup: Copying Data

Before running experiments, copy GDPEval data from manager_agent_gym:

```bash
# Copy data directory
cp -r manager_agent_gym/curation/gdpeval/data paper_code_structure_plans/

# Copy schema module
cp manager_agent_gym/curation/gdpeval/src/staged_rubric_schema.py paper_code_structure_plans/schemas/
```

### Data Loading

```python
# h_arcane/experiments/loader.py
import json
import mimetypes
from pathlib import Path
from uuid import uuid4
from pydantic import BaseModel
import pandas as pd

# Use local schemas (self-contained)
from paper_code_structure_plans.schemas.staged_rubric_schema import (
    StagedRubric,
    GDPEvalStagedRubric,
)

# Default paths relative to project root
DATA_DIR = Path(__file__).parent.parent.parent / "paper_code_structure_plans" / "data"

class GDPEvalTask(BaseModel):
    """A GDPEval task with its rubric."""
    task_id: str
    task_description: str
    reference_files: list[Path]
    rubric: StagedRubric
    category: str

def extract_task_description(task_id: str) -> str:
    """Extract task description from gdpeval.parquet."""
    tasks_df = pd.read_parquet(DATA_DIR / "raw" / "gdpeval.parquet")
    task_row = tasks_df[tasks_df["task_id"] == task_id]
    if task_row.empty:
        raise ValueError(f"Task {task_id} not found in gdpeval.parquet")
    return task_row.iloc[0]["task_description"]

def find_reference_files(task_id: str, reference_dir: Path) -> list[Path]:
    """Find reference files for a task."""
    task_files = []
    for file_path in reference_dir.glob(f"{task_id}*"):
        task_files.append(file_path)
    return sorted(task_files)

def get_mime_type(file_path: Path) -> str:
    """Get MIME type from file extension using standard library."""
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "application/octet-stream"

def load_gdpeval_tasks(
    rubric_file: Path | None = None,
    reference_dir: Path | None = None,
    limit: int | None = None,
) -> list[GDPEvalTask]:
    """Load GDPEval tasks with their staged rubrics."""
    if rubric_file is None:
        rubric_file = DATA_DIR / "generated" / "staged_v2" / "staged_rubrics.jsonl"
    if reference_dir is None:
        reference_dir = DATA_DIR / "raw" / "reference_files"
    
    tasks = []
    
    with open(rubric_file) as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            
            data = json.loads(line)
            staged_rubric = GDPEvalStagedRubric(**data)
            
            task = GDPEvalTask(
                task_id=staged_rubric.task_id,
                task_description=extract_task_description(staged_rubric.task_id),
                reference_files=find_reference_files(staged_rubric.task_id, reference_dir),
                rubric=staged_rubric.rubric,
                category=staged_rubric.rubric.category_name.split(" – ")[0],
            )
            tasks.append(task)
    
    return tasks

def load_to_database(tasks: list[GDPEvalTask]) -> list[UUID]:
    """Load tasks into experiments table and create input Resource records."""
    experiment_ids = []
    
    for task in tasks:
        experiment_id = uuid4()
        
        # Create experiment record
        queries.experiments.create(
            id=experiment_id,
            gdpeval_task_id=task.task_id,
            task_description=task.task_description,
            ground_truth_rubric=task.rubric.model_dump(),
            category=task.category,
        )
        
        # Create Resource records for input files (not JSON)
        for ref_file in task.reference_files:
            queries.resources.create(
                experiment_id=experiment_id,
                run_id=None,  # Input files don't belong to a run
                name=ref_file.name,
                mime_type=get_mime_type(ref_file),
                file_path=str(ref_file),
                size_bytes=ref_file.stat().st_size,
            )
        
        experiment_ids.append(experiment_id)
    
    return experiment_ids
```

---

## Experiment Configuration

```python
# h_arcane/experiments/config.py
from pydantic import BaseModel, Field
from enum import Enum

class BaselineType(str, Enum):
    """Available baseline worker types."""
    REACT = "react"  # ReActWorker - asks questions organically

class ExperimentConfig(BaseModel):
    """Configuration for experiment runs."""
    
    # Baseline selection
    baseline: BaselineType = Field(default=BaselineType.REACT)
    
    # Worker configuration
    worker_model: str = Field(default="gpt-4o")
    max_questions: int = Field(default=10, description="Safety limit per run")
    
    # Concurrency
    max_concurrent_runs: int = Field(default=10)
    
    # Retry policy
    max_retries: int = Field(default=2)

DEFAULT_CONFIG = ExperimentConfig()
```

---

## Experiment Runner

```python
# h_arcane/experiments/runner.py
import asyncio
from uuid import UUID
import structlog

from h_arcane.db import queries
from h_arcane.inngest.client import inngest_client
from h_arcane.experiments.loader import load_gdpeval_tasks, load_to_database
from h_arcane.experiments.config import ExperimentConfig, DEFAULT_CONFIG, BaselineType

logger = structlog.get_logger()

class ExperimentRunner:
    """Runs experiments in batches."""
    
    def __init__(self, config: ExperimentConfig | None = None):
        self.config = config or DEFAULT_CONFIG
    
    async def run_full_suite(
        self,
        task_limit: int | None = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Run all GDPEval experiments.
        
        Args:
            task_limit: Limit number of tasks (for testing)
            dry_run: If True, don't actually start runs
        
        Returns:
            Summary of started runs
        """
        # Load tasks
        logger.info("Loading GDPEval tasks", limit=task_limit)
        tasks = load_gdpeval_tasks(limit=task_limit)
        
        # Load to database
        logger.info("Loading tasks to database", count=len(tasks))
        experiment_ids = load_to_database(tasks)
        
        # Create one run per experiment
        run_ids = []
        for exp_id in experiment_ids:
            run_id = await self._create_run(exp_id)
            run_ids.append(run_id)
        
        logger.info("Created runs", count=len(run_ids))
        
        if dry_run:
            return {"dry_run": True, "experiments": len(experiment_ids)}
        
        # Start runs with concurrency control
        logger.info("Starting runs", max_concurrent=self.config.max_concurrent_runs)
        
        semaphore = asyncio.Semaphore(self.config.max_concurrent_runs)
        
        async def start_run(run_id: UUID):
            async with semaphore:
                await inngest_client.send(
                    inngest.Event(
                        name="run/start",
                        data={"run_id": str(run_id)},
                    )
                )
        
        await asyncio.gather(*[start_run(rid) for rid in run_ids])
        
        return {"started": len(run_ids), "experiments": len(experiment_ids)}
    
    async def _create_run(self, experiment_id: UUID) -> UUID:
        """Create a run record with configured baseline."""
        # Select worker based on baseline type
        # For now, only ReActWorker is available
        if self.config.baseline == BaselineType.REACT:
            worker_model = self.config.worker_model
        else:
            raise ValueError(f"Unknown baseline: {self.config.baseline}")
        
        return queries.runs.create(
            experiment_id=experiment_id,
            worker_model=worker_model,
            max_questions=self.config.max_questions,
        )
    
    async def get_progress(self) -> dict:
        """Get current experiment progress."""
        stats = queries.runs.get_stats()
        return {
            "pending": stats.pending,
            "running": stats.running,
            "completed": stats.completed,
            "failed": stats.failed,
            "total": stats.total,
            "completion_rate": stats.completed / stats.total if stats.total > 0 else 0,
        }
    
    async def retry_failed(self) -> int:
        """Retry failed runs."""
        failed_runs = queries.runs.get_by_status(RunStatus.FAILED)
        retried = 0
        
        for run in failed_runs:
            queries.runs.reset_for_retry(run.id)
            await inngest_client.send(
                inngest.Event(
                    name="run/start",
                    data={"run_id": str(run.id)},
                )
            )
            retried += 1
        
        return retried
```

---

## Results Analysis

### Aggregation Queries

```python
# h_arcane/experiments/analysis.py
import pandas as pd
from sqlalchemy import text
from h_arcane.db.connection import get_engine

def get_results_dataframe() -> pd.DataFrame:
    """Get all completed runs as a DataFrame."""
    query = """
    SELECT 
        r.id as run_id,
        r.final_score,
        r.normalized_score,
        r.questions_asked,
        r.total_cost_usd,
        e.gdpeval_task_id,
        e.category,
        ev.stages_passed,
        ev.stages_evaluated,
        ev.failed_gate
    FROM runs r
    JOIN experiments e ON r.experiment_id = e.id
    LEFT JOIN evaluations ev ON ev.run_id = r.id
    WHERE r.status = 'completed'
    """
    
    engine = get_engine()
    return pd.read_sql(query, engine)

def aggregate_by_questions(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate results by number of questions asked."""
    return df.groupby('questions_asked').agg({
        'normalized_score': ['mean', 'std', 'min', 'max'],
        'total_cost_usd': 'mean',
        'run_id': 'count',
    }).round(4)

def aggregate_by_category(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate results by task category."""
    return df.groupby('category').agg({
        'normalized_score': ['mean', 'std'],
        'questions_asked': ['mean', 'std'],
        'run_id': 'count',
    }).round(4)

def analyze_question_value(df: pd.DataFrame):
    """
    Analyze: does asking more questions improve scores?
    
    Key questions for ReAct baseline:
    - Correlation between questions_asked and score
    - Do certain categories benefit more from questions?
    - What's the marginal value of each additional question?
    """
    corr = df['questions_asked'].corr(df['normalized_score'])
    
    by_q = df.groupby('questions_asked').agg({
        'normalized_score': 'mean',
        'run_id': 'count',
    })
    
    return by_q, corr
```

---

## Running Experiments

### CLI Script

Simple CLI for running experiments:

```python
# scripts/run_experiments.py
import asyncio
import argparse
from h_arcane.experiments.runner import ExperimentRunner
from h_arcane.experiments.config import BaselineType, ExperimentConfig

async def main():
    parser = argparse.ArgumentParser(
        description="Run H-ARCANE experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 10 examples with ReAct baseline
  python scripts/run_experiments.py --num-examples 10 --baseline react
  
  # Check progress
  python scripts/run_experiments.py --progress
  
  # Retry failed runs
  python scripts/run_experiments.py --retry-failed
        """
    )
    
    parser.add_argument(
        "--num-examples",
        type=int,
        help="Number of examples to run (default: all available)"
    )
    parser.add_argument(
        "--baseline",
        type=str,
        choices=["react"],
        default="react",
        help="Baseline to run (default: react)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually start runs, just show what would run"
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry failed runs"
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Show current experiment progress"
    )
    
    args = parser.parse_args()
    
    # Create config
    config = ExperimentConfig(
        baseline=BaselineType(args.baseline),
    )
    
    runner = ExperimentRunner(config=config)
    
    if args.progress:
        progress = await runner.get_progress()
        print(f"Progress: {progress}")
        return
    
    if args.retry_failed:
        retried = await runner.retry_failed()
        print(f"Retried {retried} failed runs")
        return
    
    result = await runner.run_full_suite(
        task_limit=args.num_examples,
        dry_run=args.dry_run,
    )
    
    print(f"\n✅ Completed!")
    print(f"   Started: {result.get('started', 0)} runs")
    print(f"   Experiments: {result.get('experiments', 0)}")

if __name__ == "__main__":
    asyncio.run(main())
```

**Usage:**
```bash
# Run 10 examples with ReAct baseline
python scripts/run_experiments.py --num-examples 10 --baseline react

# Run all examples
python scripts/run_experiments.py --baseline react

# Check progress
python scripts/run_experiments.py --progress

# Retry failed runs
python scripts/run_experiments.py --retry-failed
```

### Docker Compose for Local Dev

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: h_arcane
      POSTGRES_PASSWORD: h_arcane_dev
      POSTGRES_DB: h_arcane
    ports:
      - "5433:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  inngest-dev:
    image: inngest/inngest:latest
    command: inngest dev
    ports:
      - "8289:8288"
    environment:
      - INNGEST_DEV=1
  
  api:
    build: .
    ports:
      - "8001:8000"
    environment:
      - DATABASE_URL=postgresql://h_arcane:h_arcane_dev@postgres:5432/h_arcane
      - INNGEST_DEV=1
      - INNGEST_EVENT_KEY=dev
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - postgres
      - inngest-dev
    volumes:
      - ./paper_code_structure_plans/data:/app/data

volumes:
  postgres_data:
```
