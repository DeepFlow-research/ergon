from collections.abc import Iterator
import os
from pathlib import Path
import subprocess
import sys
from typing import Literal
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy import inspect

import ergon_core.core.persistence.definitions.models  # noqa: F401
import ergon_core.core.persistence.samples.models  # noqa: F401
import ergon_core.core.persistence.telemetry.models  # noqa: F401
from ergon_core.api import Environment, Experiment, Sample
from ergon_core.core.application.experiments.repositories import persist_experiment
from ergon_core.core.persistence.experiments.models import ExperimentEnvironmentRow
from ergon_core.test_support.task_factory import task_with_id

ROOT = Path(__file__).resolve().parents[4]


def make_sample(environment_name: str, key: str) -> Sample:
    return Sample.from_tasks(
        name=f"{environment_name}:{key}",
        sample_key=key,
        environment_name=environment_name,
        tasks=[
            task_with_id(
                uuid4(),
                task_slug=f"solve-{environment_name}-{key}",
                instance_key=key,
                description=f"Solve {key}",
            )
        ],
    )


class MaterializedEnvironment(Environment):
    source_mode: Literal["materialized"] = "materialized"

    def iter_samples(self) -> Iterator[Sample]:
        yield make_sample(self.name, "a")


@pytest.fixture
def sqlite_session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def two_env_experiment() -> Experiment:
    return Experiment(
        name="integration smoke",
        environments=[
            MaterializedEnvironment(
                name="mini-validation",
                source_metadata={"dataset": "mini"},
            ),
            MaterializedEnvironment(
                name="swe-validation",
                source_metadata={"dataset": "swe"},
            ),
        ],
    )


def test_experiment_persistence_tables_roundtrip_json_and_fks(
    sqlite_session: Session,
    two_env_experiment: Experiment,
) -> None:
    handle = persist_experiment(session=sqlite_session, experiment=two_env_experiment)

    rows = sqlite_session.exec(
        select(ExperimentEnvironmentRow).where(
            ExperimentEnvironmentRow.experiment_id == handle.experiment_id
        )
    ).all()

    assert {row.name for row in rows} == {"mini-validation", "swe-validation"}
    assert all(isinstance(row.source_metadata_json, dict) for row in rows)


def test_alembic_upgrade_head_creates_experiment_persistence_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "experiment-persistence.sqlite"
    env = {
        **os.environ,
        "ERGON_DATABASE_URL": f"sqlite:///{db_path}",
    }

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=ROOT / "ergon_core",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    tables = set(inspect(create_engine(f"sqlite:///{db_path}")).get_table_names())
    assert {
        "experiments",
        "experiment_environments",
        "experiment_sampler_invocations",
        "experiment_sample_pool_entries",
    }.issubset(tables)


def test_alembic_offline_postgres_sql_renders_experiment_persistence_tables() -> None:
    env = {
        **os.environ,
        "ERGON_DATABASE_URL": "postgresql://ergon:ergon@localhost:5432/ergon",
    }

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head", "--sql"],
        cwd=ROOT / "ergon_core",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE experiments" in result.stdout
    assert "CREATE TABLE experiment_sample_pool_entries" in result.stdout
    assert " UUID " in result.stdout
