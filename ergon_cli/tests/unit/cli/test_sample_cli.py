"""Tests for the ``sample`` CLI subcommands."""

from argparse import Namespace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import ergon_cli.domains.samples.commands as sample_cmd
from ergon_cli.main import build_parser
import ergon_core.core.views.samples.service as core_sample_views
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


# ---------------------------------------------------------------------------
# Parser registration tests
# ---------------------------------------------------------------------------


def test_sample_subcommands_are_registered_in_main_parser() -> None:
    parser = build_parser()

    status_args = parser.parse_args(["sample", "status", str(uuid4())])
    show_args = parser.parse_args(["sample", "show", str(uuid4())])
    events_args = parser.parse_args(["sample", "events", str(uuid4())])
    graph_args = parser.parse_args(["sample", "graph", str(uuid4())])
    definition_id = uuid4()
    list_args = parser.parse_args(["sample", "list", "--definition-id", str(definition_id)])

    assert status_args.sample_action == "status"
    assert show_args.sample_action == "show"
    assert events_args.sample_action == "events"
    assert graph_args.sample_action == "graph"
    assert list_args.sample_action == "list"
    assert list_args.definition_id == str(definition_id)


def test_sample_list_accepts_experiment_tag_filter() -> None:
    parser = build_parser()

    list_args = parser.parse_args(["sample", "list", "--experiment", "alpha"])

    assert list_args.sample_action == "list"
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
        tables=[
            ExperimentDefinition.__table__,
            SampleRecord.__table__,
            SampleGraphNode.__table__,
        ],
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


def _sample_record(*, definition_id: object, experiment: str | None = None) -> SampleRecord:
    return SampleRecord(
        id=uuid4(),
        definition_id=definition_id,
        benchmark_type="ci-benchmark",
        instance_key="k",
        worker_team_json={},
        experiment=experiment,
        status=SampleStatus.PENDING,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# test_sample_status_prints_status_fields
# ---------------------------------------------------------------------------


def test_sample_status_prints_status_fields(monkeypatch, capsys):
    sample_id = uuid4()
    definition_id = uuid4()
    fake_sample = SampleRecord(
        id=sample_id,
        definition_id=definition_id,
        benchmark_type="ci-benchmark",
        instance_key="sample-1",
        worker_team_json={},
        status=SampleStatus.COMPLETED,
        created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 3, 1, 12, 1, tzinfo=UTC),
        completed_at=datetime(2026, 3, 1, 12, 3, tzinfo=UTC),
    )

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, model, pk):
            assert pk == sample_id
            return fake_sample

    monkeypatch.setattr(core_sample_views, "get_session", lambda: FakeSession())

    rc = sample_cmd.status_sample_command(Namespace(sample_id=str(sample_id)))

    assert rc == 0
    out = capsys.readouterr().out
    assert str(sample_id) in out
    assert "completed" in out
    assert "ci-benchmark" in out
    assert "sample-1" in out
    assert "started_at:" in out
    assert "completed_at:" in out


# ---------------------------------------------------------------------------
# test_sample_status_reports_invalid_uuid
# ---------------------------------------------------------------------------


def test_sample_status_reports_invalid_uuid(monkeypatch, capsys):
    rc = sample_cmd.status_sample_command(Namespace(sample_id="not-a-valid-uuid"))

    assert rc == 2
    out = capsys.readouterr().out
    assert "valid UUID" in out


# ---------------------------------------------------------------------------
# test_sample_status_reports_missing_run
# ---------------------------------------------------------------------------


def test_sample_status_reports_missing_run(monkeypatch, capsys):
    sample_id = uuid4()

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, model, pk):
            return None

    monkeypatch.setattr(core_sample_views, "get_session", lambda: FakeSession())

    rc = sample_cmd.status_sample_command(Namespace(sample_id=str(sample_id)))

    assert rc == 3
    out = capsys.readouterr().out
    assert str(sample_id) in out or "not found" in out.lower() or "No sample" in out


# ---------------------------------------------------------------------------
# test_sample_list_filters_by_definition
# ---------------------------------------------------------------------------


def test_sample_list_filters_by_definition(monkeypatch, session_factory, capsys):
    """Only samples for the requested definition appear."""
    definition_matching = _definition(name="matching")
    definition_other = _definition(name="other")

    sample_matching = _sample_record(definition_id=definition_matching.id)
    sample_other = _sample_record(definition_id=definition_other.id)

    # Capture IDs before the session closes to avoid DetachedInstanceError
    matching_definition_id = str(definition_matching.id)
    matching_id = str(sample_matching.id)
    other_id = str(sample_other.id)

    with session_factory() as session:
        session.add(definition_matching)
        session.add(definition_other)
        session.add(sample_matching)
        session.add(sample_other)
        session.commit()

    monkeypatch.setattr(core_sample_views, "get_session", session_factory)

    rc = sample_cmd.list_samples_command(
        Namespace(definition_id=matching_definition_id, experiment=None, status=None, limit=20)
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert matching_id in out
    assert other_id not in out


def test_sample_list_filters_by_experiment_tag(monkeypatch, session_factory, capsys):
    """The experiment filter reads the v2 ``SampleRecord.experiment`` tag."""
    definition = _definition(name="matching")

    sample_matching = _sample_record(definition_id=definition.id, experiment="alpha")
    sample_other = _sample_record(definition_id=definition.id, experiment="beta")

    matching_id = str(sample_matching.id)
    other_id = str(sample_other.id)

    with session_factory() as session:
        session.add(definition)
        session.add(sample_matching)
        session.add(sample_other)
        session.commit()

    monkeypatch.setattr(core_sample_views, "get_session", session_factory)

    rc = sample_cmd.list_samples_command(
        Namespace(definition_id=None, experiment="alpha", status=None, limit=20)
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert matching_id in out
    assert other_id not in out
