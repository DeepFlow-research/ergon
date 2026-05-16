"""Tests for the ``run`` CLI subcommands."""

from argparse import Namespace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from ergon_cli.commands import run as run_cmd
from ergon_cli.main import build_parser
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord, RunRecord
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


# ---------------------------------------------------------------------------
# Parser registration tests
# ---------------------------------------------------------------------------


def test_run_subcommands_are_registered_in_main_parser() -> None:
    parser = build_parser()

    status_args = parser.parse_args(["run", "status", str(uuid4())])
    list_args = parser.parse_args(["run", "list", "--experiment", "ablation-x"])

    assert status_args.run_action == "status"
    assert list_args.run_action == "list"
    assert list_args.experiment == "ablation-x"


# ---------------------------------------------------------------------------
# SQLite session fixture (mirrors Task 1 pattern)
# ---------------------------------------------------------------------------


@pytest.fixture()
def session_factory():
    _ = BenchmarkDefinitionRecord
    _ = ExperimentDefinition
    _ = RunGraphNode
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _get_session() -> Session:
        return Session(engine)

    return _get_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bdr(*, experiment: str | None = None) -> BenchmarkDefinitionRecord:
    return BenchmarkDefinitionRecord(
        id=uuid4(),
        name="ci experiment",
        benchmark_type="ci-benchmark",
        sample_count=1,
        experiment=experiment,
    )


def _run_record(*, experiment_id: object) -> RunRecord:
    return RunRecord(
        id=uuid4(),
        experiment_id=experiment_id,
        workflow_definition_id=uuid4(),
        benchmark_type="ci-benchmark",
        instance_key="k",
        worker_team_json={},
        status=RunStatus.PENDING,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# test_run_status_prints_status_fields
# ---------------------------------------------------------------------------


def test_run_status_prints_status_fields(monkeypatch, capsys):
    run_id = uuid4()
    bdr_id = uuid4()
    fake_run = RunRecord(
        id=run_id,
        experiment_id=bdr_id,
        workflow_definition_id=uuid4(),
        benchmark_type="ci-benchmark",
        instance_key="sample-1",
        worker_team_json={},
        status=RunStatus.COMPLETED,
        created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
    )

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, model, pk):
            assert pk == run_id
            return fake_run

    monkeypatch.setattr(run_cmd, "get_session", lambda: FakeSession())
    monkeypatch.setattr(run_cmd, "ensure_db", lambda: None)

    rc = run_cmd.status_run(Namespace(run_id=str(run_id)))

    assert rc == 0
    out = capsys.readouterr().out
    assert str(run_id) in out
    assert "completed" in out
    assert "ci-benchmark" in out
    assert "sample-1" in out


# ---------------------------------------------------------------------------
# test_run_status_reports_invalid_uuid
# ---------------------------------------------------------------------------


def test_run_status_reports_invalid_uuid(monkeypatch, capsys):
    monkeypatch.setattr(run_cmd, "ensure_db", lambda: None)

    rc = run_cmd.status_run(Namespace(run_id="not-a-valid-uuid"))

    assert rc == 1
    out = capsys.readouterr().out
    assert "Invalid UUID" in out or "invalid" in out.lower()


# ---------------------------------------------------------------------------
# test_run_status_reports_missing_run
# ---------------------------------------------------------------------------


def test_run_status_reports_missing_run(monkeypatch, capsys):
    run_id = uuid4()

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, model, pk):
            return None

    monkeypatch.setattr(run_cmd, "get_session", lambda: FakeSession())
    monkeypatch.setattr(run_cmd, "ensure_db", lambda: None)

    rc = run_cmd.status_run(Namespace(run_id=str(run_id)))

    assert rc == 1
    out = capsys.readouterr().out
    assert str(run_id) in out or "not found" in out.lower() or "No run" in out


# ---------------------------------------------------------------------------
# test_run_list_filters_by_experiment
# ---------------------------------------------------------------------------


def test_run_list_filters_by_experiment(monkeypatch, session_factory, capsys):
    """Only runs whose parent BenchmarkDefinitionRecord.experiment=='ablation-x' appear."""
    bdr_matching = _bdr(experiment="ablation-x")
    bdr_other = _bdr(experiment="other-exp")

    run_matching = _run_record(experiment_id=bdr_matching.id)
    run_other = _run_record(experiment_id=bdr_other.id)

    # Capture IDs before the session closes to avoid DetachedInstanceError
    matching_id = str(run_matching.id)
    other_id = str(run_other.id)

    with session_factory() as session:
        session.add(bdr_matching)
        session.add(bdr_other)
        session.add(run_matching)
        session.add(run_other)
        session.commit()

    monkeypatch.setattr(run_cmd, "get_session", session_factory)
    monkeypatch.setattr(run_cmd, "ensure_db", lambda: None)

    rc = run_cmd.list_runs(Namespace(experiment="ablation-x", status=None, limit=20))

    assert rc == 0
    out = capsys.readouterr().out
    assert matching_id in out
    assert other_id not in out
