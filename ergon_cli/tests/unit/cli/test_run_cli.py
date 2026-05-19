"""Tests for the ``run`` CLI subcommands."""

from argparse import Namespace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from ergon_cli.commands import run as run_cmd
from ergon_cli.main import build_parser
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.persistence.telemetry.models import RunRecord
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


# ---------------------------------------------------------------------------
# Parser registration tests
# ---------------------------------------------------------------------------


def test_run_subcommands_are_registered_in_main_parser() -> None:
    parser = build_parser()

    status_args = parser.parse_args(["run", "status", str(uuid4())])
    definition_id = uuid4()
    list_args = parser.parse_args(["run", "list", "--definition-id", str(definition_id)])

    assert status_args.run_action == "status"
    assert list_args.run_action == "list"
    assert list_args.definition_id == str(definition_id)


def test_run_list_accepts_experiment_tag_filter() -> None:
    parser = build_parser()

    list_args = parser.parse_args(["run", "list", "--experiment", "alpha"])

    assert list_args.run_action == "list"
    assert list_args.experiment == "alpha"


# ---------------------------------------------------------------------------
# SQLite session fixture (mirrors Task 1 pattern)
# ---------------------------------------------------------------------------


@pytest.fixture()
def session_factory():
    _ = ExperimentDefinition
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(
        engine,
        tables=[ExperimentDefinition.__table__, RunRecord.__table__],
    )

    def _get_session() -> Session:
        return Session(engine)

    return _get_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _definition(*, name: str) -> ExperimentDefinition:
    return ExperimentDefinition(
        id=uuid4(),
        benchmark_type="ci-benchmark",
        name=name,
        metadata_json={},
    )


def _run_record(*, definition_id: object, experiment: str | None = None) -> RunRecord:
    return RunRecord(
        id=uuid4(),
        definition_id=definition_id,
        benchmark_type="ci-benchmark",
        instance_key="k",
        worker_team_json={},
        experiment=experiment,
        status=RunStatus.PENDING,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# test_run_status_prints_status_fields
# ---------------------------------------------------------------------------


def test_run_status_prints_status_fields(monkeypatch, capsys):
    run_id = uuid4()
    definition_id = uuid4()
    fake_run = RunRecord(
        id=run_id,
        definition_id=definition_id,
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
# test_run_list_filters_by_definition
# ---------------------------------------------------------------------------


def test_run_list_filters_by_definition(monkeypatch, session_factory, capsys):
    """Only runs for the requested definition appear."""
    definition_matching = _definition(name="matching")
    definition_other = _definition(name="other")

    run_matching = _run_record(definition_id=definition_matching.id)
    run_other = _run_record(definition_id=definition_other.id)

    # Capture IDs before the session closes to avoid DetachedInstanceError
    matching_definition_id = str(definition_matching.id)
    matching_id = str(run_matching.id)
    other_id = str(run_other.id)

    with session_factory() as session:
        session.add(definition_matching)
        session.add(definition_other)
        session.add(run_matching)
        session.add(run_other)
        session.commit()

    monkeypatch.setattr(run_cmd, "get_session", session_factory)
    monkeypatch.setattr(run_cmd, "ensure_db", lambda: None)

    rc = run_cmd.list_runs(
        Namespace(definition_id=matching_definition_id, experiment=None, status=None, limit=20)
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert matching_id in out
    assert other_id not in out


def test_run_list_filters_by_experiment_tag(monkeypatch, session_factory, capsys):
    """The experiment filter reads the v2 ``RunRecord.experiment`` tag."""
    definition = _definition(name="matching")

    run_matching = _run_record(definition_id=definition.id, experiment="alpha")
    run_other = _run_record(definition_id=definition.id, experiment="beta")

    matching_id = str(run_matching.id)
    other_id = str(run_other.id)

    with session_factory() as session:
        session.add(definition)
        session.add(run_matching)
        session.add(run_other)
        session.commit()

    monkeypatch.setattr(run_cmd, "get_session", session_factory)
    monkeypatch.setattr(run_cmd, "ensure_db", lambda: None)

    rc = run_cmd.list_runs(
        Namespace(definition_id=None, experiment="alpha", status=None, limit=20)
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert matching_id in out
    assert other_id not in out
