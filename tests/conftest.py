"""
Fixtures for E2E tests.

By default, tests run against the MAIN database (same as the worker).
This ensures the test and worker see the same data.

Set E2E_USE_TEST_DB=1 to use a separate test database (requires starting
the worker with DATABASE_URL pointing to h_arcane_test).

All benchmark runs are dispatched at session start for maximum parallelism.
Individual tests just wait for their specific runs to complete.
"""

import asyncio
import os
import pytest
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import inngest
from datasets import load_dataset
from sqlmodel import SQLModel, Session, select, create_engine

from h_arcane.core.settings import settings
from h_arcane.core._internal.db.models import (
    Action,
    AgentConfig,
    CriterionResult,
    Evaluation,
    Experiment,
    Message,
    ResourceRecord,
    Run,
    RunStatus,
    TaskEvaluationResult,
    Thread,
    ThreadMessage,
)
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.utils import get_mime_type
from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.gdpeval.loader import get_data_dir, load_gdpeval_tasks
from h_arcane.benchmarks.minif2f.loader import (
    download_minif2f,
    parse_lean_problems,
    get_data_dir as get_minif2f_data_dir,
)
from h_arcane.benchmarks.minif2f.rubric import MiniF2FRubric
from h_arcane.benchmarks.researchrubrics.loader import get_ablated_dataset_name
from h_arcane.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from h_arcane.benchmarks.researchrubrics.schemas import RubricCriterion
from h_arcane.core._internal.db import models  # noqa: F401 - register models


# Number of samples per benchmark - configurable via env var
N_SAMPLES = int(os.environ.get("N_SAMPLES", "3"))


# =============================================================================
# Database Engine Configuration
# =============================================================================

_test_engine = None

# Use test DB only if explicitly requested
USE_TEST_DB = os.environ.get("E2E_USE_TEST_DB", "").lower() in ("1", "true", "yes")


def get_test_engine():
    """
    Get database engine for E2E tests.

    By default uses MAIN database (same as worker).
    Set E2E_USE_TEST_DB=1 to use separate test database.
    """
    global _test_engine
    if _test_engine is None:
        if USE_TEST_DB:
            db_url = settings.database_url_test
            print(f"🔧 Using TEST database: {db_url}")
        else:
            db_url = settings.database_url
            print(f"🔧 Using MAIN database: {db_url}")

        _test_engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _test_engine


def init_test_db():
    """Initialize database - create all tables if they don't exist."""

    engine = get_test_engine()
    SQLModel.metadata.create_all(engine)
    print("✅ Database tables created/verified")


def cleanup_test_db():
    """
    Clean up database between test sessions.

    Drops and recreates all tables for a fresh start.
    WARNING: This will delete ALL data in the database!
    """

    engine = get_test_engine()
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    print("🧹 Database cleaned (all tables dropped and recreated)")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Session-scoped: clean and initialize test DB at start of every test run.

    This guarantees that anything in the test DB is from the current test session.
    """
    # Clean slate at the start of each test run
    cleanup_test_db()
    print("🚀 Test session starting with clean database")
    yield
    # Leave data for debugging after tests complete
    # (will be cleaned on next run anyway)


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
        # Delete in dependency order (reverse of foreign key relationships)
        tables = [
            ThreadMessage,
            Thread,
            CriterionResult,
            Evaluation,
            TaskEvaluationResult,
            Action,
            AgentConfig,
            Message,
            ResourceRecord,
            Run,
            Experiment,
        ]
        for model in tables:
            session.exec(f"DELETE FROM {model.__tablename__}")  # type: ignore
        session.commit()


# =============================================================================
# Run Helpers
# =============================================================================


async def trigger_run(experiment_id: UUID, model: str = "gpt-4o-mini") -> UUID:
    """Trigger a run via Inngest using the new workflow system.

    TODO: This needs to be updated to create a proper Task from the Experiment
    and emit workflow/started with the serialized task tree. For now, tests
    should use execute_task() from h_arcane.core.runner directly.
    """
    from h_arcane.core._internal.task.events import WorkflowStartedEvent

    # Emit workflow/started event
    # Note: This requires the experiment to have a task_tree field populated
    await inngest_client.send(
        inngest.Event(
            name=WorkflowStartedEvent.name,
            data={
                "experiment_id": str(experiment_id),
                "run_id": str(uuid4()),
            },
        )
    )
    return experiment_id


async def wait_for_run_completion(
    experiment_id: UUID,
    timeout_seconds: int = 600,
    poll_interval: int = 5,
) -> Run:
    """Poll database until run completes."""
    start = datetime.now()
    timeout = timedelta(seconds=timeout_seconds)
    terminal_states = {RunStatus.COMPLETED, RunStatus.FAILED}

    engine = get_test_engine()

    while datetime.now() - start < timeout:
        with Session(engine) as session:
            run = session.exec(select(Run).where(Run.experiment_id == experiment_id)).first()

            if run and run.status in terminal_states:
                session.refresh(run)
                return run

        await asyncio.sleep(poll_interval)

    raise TimeoutError(f"Run did not complete in {timeout_seconds}s")


# =============================================================================
# Batch Dispatch - All Benchmarks at Once
# =============================================================================


@dataclass
class DispatchedExperiment:
    """Tracks a dispatched experiment and its metadata."""

    experiment: Experiment
    benchmark: BenchmarkName
    model: str
    task_data: dict = field(default_factory=dict)


@dataclass
class AllDispatchedRuns:
    """Container for all dispatched experiments across benchmarks."""

    gdpeval: list[DispatchedExperiment] = field(default_factory=list)
    minif2f: list[DispatchedExperiment] = field(default_factory=list)
    researchrubrics: list[DispatchedExperiment] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return len(self.gdpeval) + len(self.minif2f) + len(self.researchrubrics)

    def all_experiment_ids(self) -> list[UUID]:
        return [d.experiment.id for d in self.gdpeval + self.minif2f + self.researchrubrics]


def _create_gdpeval_experiments(session: Session) -> list[DispatchedExperiment]:
    """Create GDPEval experiments with input Resource records."""
    tasks = load_gdpeval_tasks(limit=N_SAMPLES)
    dispatched = []

    for task in tasks:
        experiment = Experiment(
            id=uuid4(),
            benchmark_name=BenchmarkName.GDPEVAL,
            task_id=task.task_id,
            task_description=task.task_description,
            ground_truth_rubric=task.rubric.model_dump(),
            benchmark_specific_data={
                "reference_files": [str(f) for f in task.reference_files],
            },
            category=task.category,
        )
        session.add(experiment)
        session.flush()  # Get experiment ID

        # Create Resource records for input files (critical for sandbox upload!)
        for ref_file in task.reference_files:
            try:
                file_path_relative = ref_file.relative_to(get_data_dir())
                file_path_str = str(file_path_relative)
            except ValueError:
                file_path_str = str(ref_file.absolute())

            resource = ResourceRecord(
                experiment_id=experiment.id,
                run_id=None,  # Input files don't belong to a run
                name=ref_file.name,
                mime_type=get_mime_type(ref_file),
                file_path=file_path_str,
                size_bytes=ref_file.stat().st_size,
            )
            session.add(resource)

        dispatched.append(
            DispatchedExperiment(
                experiment=experiment,
                benchmark=BenchmarkName.GDPEVAL,
                model="gpt-4o-mini",
            )
        )

    return dispatched


def _create_minif2f_experiments(session: Session) -> list[DispatchedExperiment]:
    """Create MiniF2F experiments."""
    minif2f_dir = download_minif2f(get_minif2f_data_dir())
    problems = parse_lean_problems(minif2f_dir, limit=N_SAMPLES)
    dispatched = []

    for problem in problems:
        rubric = MiniF2FRubric(
            benchmark="minif2f",
            max_score=1.0,
            partial_credit_for_syntax=0.2,
        )
        experiment = Experiment(
            id=uuid4(),
            benchmark_name=BenchmarkName.MINIF2F,
            task_id=problem.problem_id,
            task_description=problem.problem_statement,
            ground_truth_rubric=rubric.model_dump(),
            benchmark_specific_data={
                "split": problem.split,
                "ground_truth_proof": problem.ground_truth_proof,
            },
            category=f"minif2f-{problem.split}",
        )
        session.add(experiment)
        dispatched.append(
            DispatchedExperiment(
                experiment=experiment,
                benchmark=BenchmarkName.MINIF2F,
                model="gpt-4o",  # Better model for proofs
            )
        )

    return dispatched


def _create_researchrubrics_experiments(session: Session) -> list[DispatchedExperiment]:
    """Create ResearchRubrics experiments."""
    dataset_name = get_ablated_dataset_name()
    ds_dict = load_dataset(dataset_name)
    ds = ds_dict["train"]
    samples = list(ds.select(range(min(N_SAMPLES, len(ds)))))  # type: ignore[union-attr]
    dispatched = []

    for row in samples:
        row_dict: dict = dict(row)  # type: ignore[arg-type]
        sample_id = row_dict["sample_id"]

        rubric_criteria = [
            RubricCriterion(
                criterion=r["criterion"],
                axis=r["axis"],
                weight=r["weight"],
            )
            for r in row_dict["rubrics"]
        ]

        rubric = ResearchRubricsRubric(
            benchmark="researchrubrics",
            criteria=rubric_criteria,
        )

        experiment = Experiment(
            id=uuid4(),
            benchmark_name=BenchmarkName.RESEARCHRUBRICS,
            task_id=sample_id,
            task_description=row_dict["ablated_prompt"],
            ground_truth_rubric=rubric.model_dump(),
            benchmark_specific_data={
                "domain": row_dict["domain"],
                "ablation_type": row_dict.get("ablation_type"),
                "removed_elements": row_dict.get("removed_elements"),
            },
            category=row_dict["domain"],
        )
        session.add(experiment)
        dispatched.append(
            DispatchedExperiment(
                experiment=experiment,
                benchmark=BenchmarkName.RESEARCHRUBRICS,
                model="gpt-4o-mini",
            )
        )

    return dispatched


async def _dispatch_all_runs(dispatched: AllDispatchedRuns):
    """Trigger all runs via Inngest."""
    all_experiments = dispatched.gdpeval + dispatched.minif2f + dispatched.researchrubrics

    for d in all_experiments:
        await trigger_run(d.experiment.id, model=d.model)


# Global to store dispatched runs (set by session fixture)
_all_dispatched: AllDispatchedRuns | None = None


@pytest.fixture(scope="session")
def all_dispatched_runs(setup_test_db, db_engine) -> AllDispatchedRuns:
    """
    Session-scoped fixture that creates ALL experiments and dispatches ALL runs.

    This runs ONCE at session start, triggering all benchmark runs in parallel.
    Individual tests then just wait for their specific experiments.
    """
    global _all_dispatched

    print(f"\n{'=' * 60}")
    print(f"🚀 DISPATCHING ALL BENCHMARK RUNS (N_SAMPLES={N_SAMPLES})")
    print(f"{'=' * 60}")

    with Session(db_engine) as session:
        # Create all experiments
        print("\n📦 Creating GDPEval experiments...")
        gdpeval = _create_gdpeval_experiments(session)
        print(f"   ✅ {len(gdpeval)} GDPEval experiments")

        print("\n📦 Creating MiniF2F experiments...")
        minif2f = _create_minif2f_experiments(session)
        print(f"   ✅ {len(minif2f)} MiniF2F experiments")

        print("\n📦 Creating ResearchRubrics experiments...")
        researchrubrics = _create_researchrubrics_experiments(session)
        print(f"   ✅ {len(researchrubrics)} ResearchRubrics experiments")

        session.commit()

        # Refresh all experiments
        for d in gdpeval + minif2f + researchrubrics:
            session.refresh(d.experiment)

    _all_dispatched = AllDispatchedRuns(
        gdpeval=gdpeval,
        minif2f=minif2f,
        researchrubrics=researchrubrics,
    )

    # Dispatch all runs at once
    print(f"\n🚀 Triggering {_all_dispatched.total_count} runs...")
    asyncio.get_event_loop().run_until_complete(_dispatch_all_runs(_all_dispatched))
    print(f"✅ All {_all_dispatched.total_count} runs dispatched!")
    print(f"{'=' * 60}\n")

    return _all_dispatched
