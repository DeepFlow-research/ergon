# E2E Smoke Test Suite

## Overview

**Run a real task through the entire pipeline, then assert on database state.**

This is the right level to test at. If a full run completes with correct state in PostgreSQL:
- Lean is installed (MiniF2F)
- Exa API works (ResearchRubrics)  
- Sandbox dependencies are present (GDPEval)
- Orchestration works
- Evaluation runs correctly

No need to test `lean --version` or toolkit methods in isolation.

### Testing Philosophy

```
❌ Bad: Test components in isolation
   - toolkit.verify_proof()
   - sbx.commands.run("lean --version")
   - Check if pdfplumber is installed

✅ Good: Run a complete task, assert completion, print failures
   - Run.status == COMPLETED
   - Evaluation produced scores
   - Print any tool failures for manual review
```

**No automatic error classification** - all failures printed for human review.
The human decides if failures are infrastructure issues or expected agent mistakes.

### What E2E Tests Catch

| Run a task in... | If it completes successfully, this works: |
|------------------|------------------------------------------|
| MiniF2F | Lean, Mathlib, elan, proof verification |
| GDPEval | pdfplumber, pandas, python-docx, sandbox |
| ResearchRubrics | Exa API, EXA_API_KEY, report tools |

### Schema Changes Required

Simple error tracking - just record what failed, review manually:

```python
# h_arcane/core/db/models.py

from pydantic import BaseModel


class ExecutionError(BaseModel):
    """
    Error details for failed tool calls or evaluations.
    
    Stored as JSON in the `error` column.
    If error is None, the action/evaluation succeeded.
    
    No automatic classification - just record what happened, review manually.
    """
    message: str
    exception_type: str | None = None  # e.g., "ModuleNotFoundError"
    stack_trace: str | None = None     # Full traceback for debugging
    details: dict | None = None        # Optional: sandbox logs, extra context


# Helper to create ExecutionError from exception
def create_execution_error(
    exception: Exception | None = None,
    message: str | None = None,
    details: dict | None = None,
) -> ExecutionError:
    """
    Create ExecutionError with full stack trace.
    
    Usage:
        try:
            ...
        except Exception as e:
            error = create_execution_error(e)
    """
    import traceback
    
    if exception:
        return ExecutionError(
            message=message or str(exception),
            exception_type=type(exception).__name__,
            stack_trace=traceback.format_exc(),
            details=details,
        )
    else:
        return ExecutionError(
            message=message or "Unknown error",
            exception_type=None,
            stack_trace=None,
            details=details,
        )


class Action(SQLModel, table=True):
    # ... existing fields ...
    
    # Single JSON column for error (None = success)
    error: ExecutionError | None = Field(default=None, sa_column=Column(JSON))
    
    @property
    def success(self) -> bool:
        """Convenience: success means no error."""
        return self.error is None


class CriterionResult(SQLModel, table=True):
    # ... existing fields ...
    
    # Single JSON column for error (None = ran successfully)
    error: ExecutionError | None = Field(default=None, sa_column=Column(JSON))
    
    @property
    def ran_successfully(self) -> bool:
        return self.error is None
```

**Benefits:**
- Dead simple - just record errors, no fragile classification
- `error = None` implies success (no separate `success` bool needed)
- All failures flagged for manual review
- Easy to grep/query for specific error types later

### Prerequisites

```bash
# Start all services
docker compose up -d

# Set API keys in .env
```

---

## Test Database Architecture

**Tests use a separate database with identical schema.**

This ensures:
- Clean separation from production data
- Safe to wipe between test runs
- No risk of test pollution
- Can run tests in parallel without conflicts
- Easy inspection of test results in isolation

### Database Setup

```
Production: postgresql://...@localhost:5433/h_arcane
Test:       postgresql://...@localhost:5433/h_arcane_test
```

Same PostgreSQL server, same schema (same models), different database.

### Settings Extension

```python
# h_arcane/settings.py (add test database URL)

class Settings(BaseSettings):
    # ... existing fields ...
    
    # Separate test database
    database_url_test: str = "postgresql://h_arcane:h_arcane_dev@localhost:5433/h_arcane_test"
```

### Docker Compose Addition

```yaml
# docker-compose.yml - init script creates both databases
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: h_arcane
      POSTGRES_PASSWORD: h_arcane_dev
      POSTGRES_DB: h_arcane
    volumes:
      - ./init-db.sh:/docker-entrypoint-initdb.d/init-db.sh
    ports:
      - "5433:5432"
```

```bash
# init-db.sh - creates test database alongside main one
#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE h_arcane_test;
    GRANT ALL PRIVILEGES ON DATABASE h_arcane_test TO h_arcane;
EOSQL
```

### Rationale

Why separate database (not transactions/rollback)?
- E2E tests trigger Inngest events → run in separate processes
- Those processes need to read/write DB state
- Can't share a transaction across process boundaries
- Separate DB is the only clean solution for true E2E tests

### Critical: Worker Must Use Test DB

**The worker process must ALSO be configured to use the test database during E2E tests.**

Since tests trigger Inngest events → worker handles them → writes to DB, the worker needs to write to `h_arcane_test`, not `h_arcane`.

**Option 1: Environment Variable Override (Recommended)**

```bash
# Run worker with test DB
DATABASE_URL=postgresql://h_arcane:h_arcane_dev@localhost:5433/h_arcane_test \
  python -m h_arcane.api.main
```

**Option 2: Separate Docker Compose for Tests**

```yaml
# docker-compose.test.yml
services:
  worker:
    environment:
      - DATABASE_URL=postgresql://h_arcane:h_arcane_dev@postgres:5432/h_arcane_test
```

**Option 3: Unified Connection Logic**

```python
# h_arcane/core/db/connection.py

import os

def get_engine():
    global _engine
    if _engine is None:
        # Use DATABASE_URL env var if set, otherwise settings default
        db_url = os.environ.get("DATABASE_URL", settings.database_url)
        _engine = create_engine(db_url, ...)
    return _engine
```

Then run tests with:
```bash
DATABASE_URL=...h_arcane_test pytest tests/e2e/
```

---

## Directory Structure

```
arcane_extension/
├── h_arcane/
│   ├── core/
│   │   └── db/models.py         # + ExecutionError model
│   └── settings.py              # + database_url_test
├── init-db.sh                   # Creates both h_arcane and h_arcane_test
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # DB fixtures (uses test DB), run helpers
│   ├── utils/
│   │   ├── __init__.py
│   │   └── assertions.py        # Reusable test assertions
│   └── e2e/
│       ├── __init__.py
│       ├── test_gdpeval_e2e.py
│       ├── test_minif2f_e2e.py
│       └── test_researchrubrics_e2e.py
```

No fixtures directory needed - tests use real benchmark loaders.

---

## Core Fixtures (`conftest.py`)

```python
"""
Fixtures for E2E tests.

Tests run against a SEPARATE test database with identical schema.
This isolates test data from production and allows clean test runs.
"""
import asyncio
import os
import pytest
from uuid import UUID
from datetime import datetime, timedelta

import inngest
from sqlmodel import SQLModel, Session, select, create_engine

from h_arcane.settings import settings
from h_arcane.core.db.models import Run, RunStatus
from h_arcane.core.infrastructure.inngest_client import inngest_client


# ============================================================================
# Test Database Engine (separate from production)
# ============================================================================

_test_engine = None


def get_test_engine():
    """
    Get engine pointing to TEST database (h_arcane_test).
    
    Uses settings.database_url_test, NOT settings.database_url.
    """
    global _test_engine
    if _test_engine is None:
        _test_engine = create_engine(
            settings.database_url_test,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _test_engine


def init_test_db():
    """Initialize test database - create all tables."""
    from h_arcane.core.db import models  # noqa: F401 - register models
    
    engine = get_test_engine()
    SQLModel.metadata.create_all(engine)
    print("✅ Test database tables created")


def cleanup_test_db():
    """
    Clean up test database between test sessions.
    
    Drops and recreates all tables for a fresh start.
    """
    from h_arcane.core.db import models  # noqa: F401
    
    engine = get_test_engine()
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    print("🧹 Test database cleaned")


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Session-scoped: initialize test DB once at start of test session."""
    init_test_db()
    yield
    # Optional: cleanup after all tests
    # cleanup_test_db()


@pytest.fixture(scope="session")
def db_engine(setup_test_db):
    """Session-scoped test database engine."""
    return get_test_engine()


@pytest.fixture
def db_session(db_engine):
    """Per-test database session."""
    with Session(db_engine) as session:
        yield session


@pytest.fixture(scope="function")
def clean_db(db_engine):
    """
    Per-test cleanup fixture.
    
    Use this fixture in tests that need a clean slate.
    Deletes all rows from tables (but keeps schema).
    """
    yield  # test runs
    
    # Cleanup after test
    with Session(db_engine) as session:
        # Delete in dependency order
        for model in [Run, Experiment]:  # Add others as needed
            session.exec(f"DELETE FROM {model.__tablename__}")
        session.commit()


# ============================================================================
# Run Helpers
# ============================================================================

async def trigger_run(experiment_id: UUID, model: str = "gpt-4o-mini") -> UUID:
    """Trigger a run via Inngest."""
    await inngest_client.send(
        inngest.Event(
            name="run/start",
            data={
                "experiment_id": str(experiment_id),
                "worker_model": model,
                "max_questions": 3,
            },
        )
    )
    return experiment_id


async def wait_for_run_completion(
    experiment_id: UUID,
    timeout_seconds: int = 600,
    poll_interval: int = 10,
) -> Run:
    """Poll database until run completes."""
    start = datetime.now()
    timeout = timedelta(seconds=timeout_seconds)
    terminal_states = {RunStatus.COMPLETED, RunStatus.FAILED}
    
    engine = get_engine()
    
    while datetime.now() - start < timeout:
        with Session(engine) as session:
            run = session.exec(
                select(Run).where(Run.experiment_id == experiment_id)
            ).first()
            
            if run and run.status in terminal_states:
                session.refresh(run)
                return run
        
        await asyncio.sleep(poll_interval)
    
    raise TimeoutError(f"Run did not complete in {timeout_seconds}s")
```

---

## Common Test Utilities (`tests/utils/assertions.py`)

Reusable assertion functions for all E2E tests.

```python
"""
tests/utils/assertions.py

Common assertion utilities for E2E tests.

Uses the simplified schema where Action.error and CriterionResult.error
are either None (success) or an ExecutionError object.
"""
from dataclasses import dataclass

from sqlmodel import Session, select

from h_arcane.core.db.models import (
    Run, RunStatus, Action, CriterionResult, Evaluation
)


@dataclass
class RunResult:
    """Result of checking a run - all failures flagged for review."""
    run_status: RunStatus
    failed_actions: list[Action]
    failed_evals: list[CriterionResult]
    has_evaluation: bool
    has_scores: bool
    
    @property
    def completed(self) -> bool:
        return self.run_status == RunStatus.COMPLETED
    
    def print_failures(self, show_stack_traces: bool = True):
        """Print all failures for manual review."""
        if self.failed_actions:
            print(f"\n⚠️  FAILED ACTIONS ({len(self.failed_actions)}):")
            for a in self.failed_actions:
                print(f"\n  [{a.action_type}]")
                if a.error:
                    print(f"    message: {a.error.message}")
                    if a.error.exception_type:
                        print(f"    exception: {a.error.exception_type}")
                    if show_stack_traces and a.error.stack_trace:
                        print(f"    stack trace:")
                        # Indent each line of stack trace
                        for line in a.error.stack_trace.strip().split('\n'):
                            print(f"      {line}")
        
        if self.failed_evals:
            print(f"\n⚠️  FAILED EVALUATIONS ({len(self.failed_evals)}):")
            for cr in self.failed_evals:
                print(f"\n  [{cr.criterion_description}]")
                if cr.error:
                    print(f"    message: {cr.error.message}")
                    if show_stack_traces and cr.error.stack_trace:
                        print(f"    stack trace:")
                        for line in cr.error.stack_trace.strip().split('\n'):
                            print(f"      {line}")


def check_run(run: Run, session: Session) -> RunResult:
    """
    Check run state and return result with all failures.
    
    No automatic classification - just collects failures for manual review.
    """
    # Get all actions
    actions = session.exec(
        select(Action).where(Action.run_id == run.id)
    ).all()
    
    # Any action with error is a failure
    failed_actions = [a for a in actions if not a.success]
    
    # Get criterion results
    criterion_results = session.exec(
        select(CriterionResult).where(CriterionResult.run_id == run.id)
    ).all()
    
    failed_evals = [cr for cr in criterion_results if not cr.ran_successfully]
    
    # Check evaluation exists
    evaluation = session.exec(
        select(Evaluation).where(Evaluation.run_id == run.id)
    ).first()
    
    has_evaluation = evaluation is not None
    has_scores = (
        has_evaluation and 
        evaluation.total_score is not None and
        run.final_score is not None
    )
    
    return RunResult(
        run_status=run.status,
        failed_actions=failed_actions,
        failed_evals=failed_evals,
        has_evaluation=has_evaluation,
        has_scores=has_scores,
    )


# ============================================================================
# Assertion Functions
# ============================================================================

def assert_run_completed(run: Run, session: Session):
    """Assert run reached COMPLETED status."""
    assert run.status == RunStatus.COMPLETED, \
        f"Run failed with status {run.status}"


def assert_evaluation_ran(run: Run, session: Session):
    """Assert evaluation was executed and produced scores."""
    evaluation = session.exec(
        select(Evaluation).where(Evaluation.run_id == run.id)
    ).first()
    
    assert evaluation is not None, "No Evaluation record created"
    assert evaluation.total_score is not None, "Evaluation missing total_score"
    
    criterion_results = session.exec(
        select(CriterionResult).where(CriterionResult.run_id == run.id)
    ).all()
    
    assert len(criterion_results) > 0, "No CriterionResult records - evaluation didn't run"


def assert_run_completed_and_print_failures(run: Run, session: Session):
    """
    Assert run completed, print any failures for manual review.
    
    Does NOT fail on tool errors - just prints them.
    The human reviews the output to decide if failures are concerning.
    """
    result = check_run(run, session)
    
    # Always print failures for review
    result.print_failures()
    
    # Only assert on completion and evaluation
    assert result.completed, f"Run failed with status {result.run_status}"
    assert result.has_evaluation, "No Evaluation record created"
    assert result.has_scores, "Missing scores"
```

---

## 1. GDPEval E2E Test (`test_gdpeval_e2e.py`)

Uses real benchmark loader - no hardcoded synthetic tasks.

```python
"""
tests/e2e/test_gdpeval_e2e.py

End-to-end tests for GDPEval benchmark.

Runs the first N tasks from real benchmark data and asserts on DB state.
"""
import pytest
from uuid import uuid4

from sqlmodel import Session

from h_arcane.core.db.models import Experiment
from h_arcane.benchmarks.gdpeval.loader import GDPEvalLoader
from tests.conftest import trigger_run, wait_for_run_completion
from tests.utils.assertions import assert_run_completed_and_print_failures


# Number of samples to run in E2E tests
N_SAMPLES = 3


class TestGDPEvalE2E:
    """
    Run GDPEval tasks end-to-end using real benchmark data.
    
    If these pass:
    - Sandbox creates successfully
    - Run completes
    - Evaluation runs and produces scores
    
    Any tool failures are printed for manual review.
    """
    
    @pytest.fixture(scope="class")
    def gdpeval_tasks(self):
        """Load first N tasks from real GDPEval benchmark."""
        loader = GDPEvalLoader()
        tasks = loader.load_tasks(limit=N_SAMPLES)
        return tasks

    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    @pytest.mark.parametrize("task_idx", range(N_SAMPLES))
    async def test_gdpeval_task(self, task_idx, gdpeval_tasks, db_session: Session):
        """
        Run task N from GDPEval dataset.
        
        Tool failures printed for manual review.
        """
        task = gdpeval_tasks[task_idx]
        
        # Create experiment from real task
        experiment = Experiment(
            id=uuid4(),
            benchmark_name=task.benchmark_name,
            task_id=task.task_id,
            task_description=task.task_description,
            ground_truth_rubric=task.ground_truth_rubric,
            benchmark_specific_data=task.benchmark_specific_data,
            category=task.category,
        )
        db_session.add(experiment)
        db_session.commit()
        db_session.refresh(experiment)
        
        # Trigger and wait
        await trigger_run(experiment.id, model="gpt-4o-mini")
        run = await wait_for_run_completion(experiment.id, timeout_seconds=240)
        
        # Assert run completed, print any failures for review
        assert_run_completed_and_print_failures(run, db_session)
```

---

## 2. MiniF2F E2E Test (`test_minif2f_e2e.py`)

```python
"""
tests/e2e/test_minif2f_e2e.py

End-to-end tests for MiniF2F benchmark.

Runs the first N proof tasks and asserts on DB state.
Critical failures (Lean not installed, Mathlib missing) will fail the test.
"""
import pytest
from uuid import uuid4

from sqlmodel import Session

from h_arcane.core.db.models import Experiment
from h_arcane.benchmarks.minif2f.loader import MiniF2FLoader
from tests.conftest import trigger_run, wait_for_run_completion
from tests.utils.assertions import assert_run_completed_and_print_failures


N_SAMPLES = 2  # Fewer samples - Lean is slow


class TestMiniF2FE2E:
    """
    Run MiniF2F proof tasks end-to-end.
    
    If these pass:
    - Lean is installed correctly
    - Mathlib is available  
    - Run completes and evaluation runs
    
    Any tool failures (Lean errors, proof failures) printed for manual review.
    """
    
    @pytest.fixture(scope="class")
    def minif2f_tasks(self):
        """Load first N tasks from real MiniF2F benchmark."""
        loader = MiniF2FLoader()
        # Load easy problems from test split for smoke testing
        tasks = loader.load_tasks(split="test", limit=N_SAMPLES)
        return tasks

    @pytest.mark.asyncio
    @pytest.mark.timeout(600)  # 10 minutes per task
    @pytest.mark.parametrize("task_idx", range(N_SAMPLES))
    async def test_minif2f_task(self, task_idx, minif2f_tasks, db_session: Session):
        """
        Run task N from MiniF2F dataset.
        
        Tool failures (Lean errors, wrong proofs) printed for review.
        """
        task = minif2f_tasks[task_idx]
        
        experiment = Experiment(
            id=uuid4(),
            benchmark_name=task.benchmark_name,
            task_id=task.task_id,
            task_description=task.task_description,
            ground_truth_rubric=task.ground_truth_rubric,
            benchmark_specific_data=task.benchmark_specific_data,
            category=task.category,
        )
        db_session.add(experiment)
        db_session.commit()
        db_session.refresh(experiment)
        
        # Use capable model for proofs
        await trigger_run(experiment.id, model="gpt-4o")
        run = await wait_for_run_completion(experiment.id, timeout_seconds=540)
        
        # Assert run completed, print any failures for review
        assert_run_completed_and_print_failures(run, db_session)
```

---

## 3. ResearchRubrics E2E Test (`test_researchrubrics_e2e.py`)

```python
"""
tests/e2e/test_researchrubrics_e2e.py

End-to-end tests for ResearchRubrics benchmark.
"""
import pytest
from uuid import uuid4

from sqlmodel import Session

from h_arcane.core.db.models import Experiment
from h_arcane.benchmarks.researchrubrics.loader import ResearchRubricsLoader
from tests.conftest import trigger_run, wait_for_run_completion
from tests.utils.assertions import assert_run_completed_and_print_failures


N_SAMPLES = 3


class TestResearchRubricsE2E:
    """
    Run ResearchRubrics tasks end-to-end.
    
    If these pass:
    - Run completes
    - Evaluation produces scores
    
    Any tool failures (Exa API errors, etc.) printed for review.
    """
    
    @pytest.fixture(scope="class")
    def researchrubrics_tasks(self):
        """Load first N tasks from real ResearchRubrics benchmark."""
        loader = ResearchRubricsLoader()
        tasks = loader.load_tasks(limit=N_SAMPLES)
        return tasks

    @pytest.mark.asyncio
    @pytest.mark.timeout(300)
    @pytest.mark.parametrize("task_idx", range(N_SAMPLES))
    async def test_researchrubrics_task(self, task_idx, researchrubrics_tasks, db_session: Session):
        """
        Run task N from ResearchRubrics dataset.
        
        Tool failures (Exa API errors, etc.) printed for review.
        """
        task = researchrubrics_tasks[task_idx]
        
        experiment = Experiment(
            id=uuid4(),
            benchmark_name=task.benchmark_name,
            task_id=task.task_id,
            task_description=task.task_description,
            ground_truth_rubric=task.ground_truth_rubric,
            benchmark_specific_data=task.benchmark_specific_data,
            category=task.category,
        )
        db_session.add(experiment)
        db_session.commit()
        db_session.refresh(experiment)
        
        await trigger_run(experiment.id, model="gpt-4o-mini")
        run = await wait_for_run_completion(experiment.id, timeout_seconds=240)
        
        # Assert run completed, print any failures for review
        assert_run_completed_and_print_failures(run, db_session)
```

---

## 4. Scaling to More Tasks (Fuzz Testing)

The same pattern scales to more samples:

```python
"""
tests/e2e/test_extended.py

Run more samples for deeper testing.
Set N_SAMPLES higher for CI or stress testing.
"""
import pytest
from uuid import uuid4
import os

from sqlmodel import Session

from h_arcane.core.db.models import Experiment
from h_arcane.benchmarks.gdpeval.loader import GDPEvalLoader
from h_arcane.benchmarks.minif2f.loader import MiniF2FLoader
from h_arcane.benchmarks.researchrubrics.loader import ResearchRubricsLoader
from tests.conftest import trigger_run, wait_for_run_completion
from tests.utils.assertions import assert_run_completed_and_print_failures


# Configure via environment variable for CI
N_SAMPLES = int(os.environ.get("E2E_N_SAMPLES", "10"))


class TestExtendedGDPEval:
    """Run more GDPEval samples for stress testing."""
    
    @pytest.fixture(scope="class")
    def tasks(self):
        return GDPEvalLoader().load_tasks(limit=N_SAMPLES)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("idx", range(N_SAMPLES))
    async def test_task(self, idx, tasks, db_session: Session):
        task = tasks[idx]
        experiment = Experiment(id=uuid4(), **task.__dict__)
        db_session.add(experiment)
        db_session.commit()
        
        await trigger_run(experiment.id)
        run = await wait_for_run_completion(experiment.id)
        
        # Run completed + print failures for review
        assert_run_completed_and_print_failures(run, db_session)
```

### Running Extended Tests

```bash
# Default: 10 samples per benchmark
pytest tests/e2e/test_extended.py -v

# CI: run 50 samples
E2E_N_SAMPLES=50 pytest tests/e2e/test_extended.py -v

# Full dataset stress test
E2E_N_SAMPLES=500 pytest tests/e2e/test_extended.py -v --timeout=7200
```

---

## Running E2E Tests

```bash
# Run all E2E tests (first N samples of each benchmark)
pytest tests/e2e/ -v

# Run specific benchmark
pytest tests/e2e/test_gdpeval_e2e.py -v          # ~5-10 min (3 samples)
pytest tests/e2e/test_minif2f_e2e.py -v          # ~15-20 min (2 samples, Lean slow)
pytest tests/e2e/test_researchrubrics_e2e.py -v  # ~5-10 min (3 samples)

# Extended testing with more samples
E2E_N_SAMPLES=20 pytest tests/e2e/test_extended.py -v

# Stop on first failure
pytest tests/e2e/ -v -x

# Verbose output on failure
pytest tests/e2e/ -v --tb=long
```

---

## Summary

### Testing Philosophy

**Run real tasks, assert completion, print failures for manual review.**

```
                                         Assert HERE
                                              ↓
Task (from loader) → Agent → Orchestration → [PostgreSQL]
                                              ↓
                                    ✓ Run completed?
                                    ✓ Evaluation ran?
                                    Print any failures → human reviews
```

### Key Concepts

| Concept | Description |
|---------|-------------|
| **Flag failures, don't classify** | All tool failures recorded and printed for manual review. No fragile auto-classification. |
| **Real data** | Tests use actual benchmark loaders, no hardcoded synthetic tasks. |
| **Assert completion** | Tests assert run completed + evaluation ran. Failures printed for human review. |

### Schema Changes Required

Simple error tracking with full stack traces:

```python
# h_arcane/core/db/models.py

class ExecutionError(BaseModel):
    message: str
    exception_type: str | None = None
    stack_trace: str | None = None  # Full traceback for debugging
    details: dict | None = None

class Action(SQLModel, table=True):
    error: ExecutionError | None = Field(default=None, sa_column=Column(JSON))
    
    @property
    def success(self) -> bool:
        return self.error is None

class CriterionResult(SQLModel, table=True):
    error: ExecutionError | None = Field(default=None, sa_column=Column(JSON))
    
    @property
    def ran_successfully(self) -> bool:
        return self.error is None
```

### What Tests Assert

| Assertion | What It Checks |
|-----------|---------------|
| `assert_run_completed_and_print_failures()` | Run completed + evaluation ran + prints all failures with stack traces |

### Test Output (Example)

```
⚠️  FAILED ACTIONS (1):

  [verify_lean_proof]
    message: path '/tools/mathlib_project/src/final_solution.lean' does not exist
    exception: FileNotFoundError
    stack trace:
      Traceback (most recent call last):
        File "/app/h_arcane/benchmarks/minif2f/toolkit.py", line 142, in verify_lean_proof
          content = await sandbox.files.read(file_path)
        File "/app/.venv/lib/python3.13/site-packages/e2b/sandbox_async/filesystem.py", line 89, in read
          raise FileNotFoundError(f"File not found: {path}")
      FileNotFoundError: File not found: /tools/mathlib_project/src/final_solution.lean

✅ Run completed, evaluation produced scores
```

Human reviews output → decides if failures are concerning (infrastructure) or expected (agent mistakes).

### Scaling

```bash
# Basic smoke test: 3 samples per benchmark
pytest tests/e2e/ -v

# CI: 20 samples
E2E_N_SAMPLES=20 pytest tests/e2e/test_extended.py

# Stress test: full dataset
E2E_N_SAMPLES=500 pytest tests/e2e/test_extended.py --timeout=7200
```

### Why This Approach Works

1. **Uses real data**: No hardcoded synthetic tasks. First N samples from actual benchmark loaders.

2. **Full stack traces**: When things fail, you see the complete traceback - not just "FileNotFoundError".

3. **No fragile classification**: Tool errors flagged for manual review, not auto-classified.

4. **Human decides**: You look at failures and decide if they're infrastructure issues or agent mistakes.

5. **Scales naturally**: Same test pattern works for 3 samples or 500 samples.

6. **Database as source of truth**: All assertions check PG state, not intermediate results.

