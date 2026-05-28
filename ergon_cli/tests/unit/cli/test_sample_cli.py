"""Tests for the ``sample`` CLI subcommands."""

from argparse import Namespace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

import ergon_cli.domains.samples.commands as sample_cmd
import ergon_cli.domains.samples.service as sample_domain_service
from ergon_cli.main import build_parser
from ergon_core.core.application.samples.event_views import SampleStatusChangedEventView
from ergon_core.core.views.samples.models import (
    SampleDetailView,
    SampleEventsView,
    SampleGraphView,
    SampleSummaryDto,
)


def _sample_summary(
    *,
    sample_id: UUID | None = None,
    status: str = "completed",
    experiment: str | None = None,
    instance_key: str = "sample-1",
) -> SampleSummaryDto:
    return SampleSummaryDto(
        id=sample_id or uuid4(),
        name=instance_key,
        status=status,
        created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 3, 1, 12, 1, tzinfo=UTC),
        completed_at=datetime(2026, 3, 1, 12, 3, tzinfo=UTC),
        experiment=experiment,
        benchmark_type="ci-benchmark",
        instance_key=instance_key,
        sample_label=instance_key,
    )


def test_sample_subcommands_are_registered_in_main_parser() -> None:
    parser = build_parser()

    status_args = parser.parse_args(["sample", "status", str(uuid4())])
    show_args = parser.parse_args(["sample", "show", str(uuid4())])
    events_args = parser.parse_args(["sample", "events", str(uuid4())])
    graph_args = parser.parse_args(["sample", "graph", str(uuid4())])
    list_args = parser.parse_args(["sample", "list", "--experiment", "alpha"])

    assert status_args.sample_action == "status"
    assert show_args.sample_action == "show"
    assert events_args.sample_action == "events"
    assert graph_args.sample_action == "graph"
    assert list_args.sample_action == "list"
    assert list_args.experiment == "alpha"


def test_sample_list_accepts_experiment_tag_filter() -> None:
    parser = build_parser()

    list_args = parser.parse_args(["sample", "list", "--experiment", "alpha"])

    assert list_args.sample_action == "list"
    assert list_args.experiment == "alpha"


def test_sample_cancel_is_not_registered() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["sample", "cancel", str(uuid4())])


def test_sample_status_prints_status_fields(monkeypatch, capsys) -> None:
    sample_id = uuid4()

    class FakeReadService:
        def get_sample_summary(self, requested_sample_id: UUID) -> SampleSummaryDto:
            assert requested_sample_id == sample_id
            return _sample_summary(sample_id=sample_id)

    monkeypatch.setattr(sample_domain_service, "SampleSnapshotReadService", FakeReadService)

    rc = sample_cmd.status_sample_command(Namespace(sample_id=str(sample_id)))

    assert rc == 0
    out = capsys.readouterr().out
    assert str(sample_id) in out
    assert "completed" in out
    assert "ci-benchmark" in out
    assert "sample-1" in out
    assert "started_at:" in out
    assert "completed_at:" in out
    assert "environment_type:" in out
    assert "benchmark_type:" not in out


def test_sample_status_reports_invalid_uuid(capsys) -> None:
    rc = sample_cmd.status_sample_command(Namespace(sample_id="not-a-valid-uuid"))

    assert rc == 2
    out = capsys.readouterr().out
    assert "valid UUID" in out


def test_sample_status_reports_missing_sample(monkeypatch, capsys) -> None:
    sample_id = uuid4()

    class FakeReadService:
        def get_sample_summary(self, requested_sample_id: UUID) -> None:
            assert requested_sample_id == sample_id
            return None

    monkeypatch.setattr(sample_domain_service, "SampleSnapshotReadService", FakeReadService)

    rc = sample_cmd.status_sample_command(Namespace(sample_id=str(sample_id)))

    assert rc == 3
    out = capsys.readouterr().out
    assert str(sample_id) in out or "not found" in out.lower() or "No sample" in out


def test_sample_list_filters_by_experiment_tag(monkeypatch, capsys) -> None:
    matching = _sample_summary(experiment="alpha", instance_key="matching")

    class FakeReadService:
        def list_samples(self, *, limit: int, status: str | None, experiment: str | None):
            assert limit == 20
            assert status is None
            assert experiment == "alpha"
            return [matching]

    monkeypatch.setattr(sample_domain_service, "SampleSnapshotReadService", FakeReadService)

    rc = sample_cmd.list_samples_command(Namespace(experiment="alpha", status=None, limit=20))

    assert rc == 0
    out = capsys.readouterr().out
    assert str(matching.id) in out
    assert "matching" not in out


def test_sample_show_events_and_graph_use_read_models(monkeypatch, capsys) -> None:
    sample_id = uuid4()
    experiment_id = uuid4()
    environment_id = uuid4()
    event_id = uuid4()

    class FakeReadService:
        def get_sample_detail(self, requested_sample_id: UUID) -> SampleDetailView:
            assert requested_sample_id == sample_id
            return SampleDetailView(
                sample_id=sample_id,
                experiment_id=experiment_id,
                environment_id=environment_id,
                environment_name="mini-validation",
                sample_key="sample-a",
                status="completed",
                created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
            )

        def list_sample_events(self, requested_sample_id: UUID) -> SampleEventsView:
            assert requested_sample_id == sample_id
            return SampleEventsView(
                items=[
                    SampleStatusChangedEventView(
                        event_id=event_id,
                        sample_id=sample_id,
                        event_type="sample.status_changed",
                        target_type="sample",
                        target_id=sample_id,
                        status="completed",
                        timestamp=datetime(2026, 3, 1, 12, 3, tzinfo=UTC),
                    )
                ]
            )

        def get_sample_graph(self, requested_sample_id: UUID) -> SampleGraphView:
            assert requested_sample_id == sample_id
            return SampleGraphView()

    monkeypatch.setattr(sample_domain_service, "SampleReadService", FakeReadService)

    assert sample_cmd.show_sample_command(Namespace(sample_id=str(sample_id))) == 0
    assert sample_cmd.sample_events_command(Namespace(sample_id=str(sample_id))) == 0
    assert sample_cmd.sample_graph_command(Namespace(sample_id=str(sample_id))) == 0

    out = capsys.readouterr().out
    assert str(experiment_id) in out
    assert "sample.status_changed" in out
    assert "nodes:" in out
    assert "definition" not in out.lower()
