import logging
from argparse import Namespace
from uuid import uuid4

import pytest
from ergon_cli.commands import experiment as experiment_cmd
from ergon_cli.main import build_parser
from ergon_core.core.application.read_models.experiments import (
    ExperimentDetailDto,
    ExperimentRunRowDto,
    ExperimentSummaryDto,
)


def _summary(**overrides) -> ExperimentSummaryDto:
    data = {
        "experiment_id": uuid4(),
        "cohort_id": None,
        "name": "ci experiment",
        "benchmark_type": "ci-benchmark",
        "sample_count": 2,
        "status": "defined",
        "created_at": "2026-04-27T12:00:00Z",
        "run_count": 0,
    }
    data.update(overrides)
    return ExperimentSummaryDto.model_validate(data)


def test_experiment_subcommands_are_registered_in_main_parser() -> None:
    """After PR 8 Task 5: show, list, tags, and by-tag are all registered."""
    parser = build_parser()

    show_args = parser.parse_args(["experiment", "show", str(uuid4())])
    list_args = parser.parse_args(["experiment", "list", "--limit", "3"])
    tags_args = parser.parse_args(["experiment", "tags"])
    by_tag_args = parser.parse_args(["experiment", "by-tag", "alpha"])

    assert show_args.experiment_action == "show"
    assert list_args.experiment_action == "list"
    assert list_args.limit == 3
    assert tags_args.experiment_action == "tags"
    assert by_tag_args.experiment_action == "by-tag"
    assert by_tag_args.tag == "alpha"


def test_experiment_define_subcommand_is_no_longer_registered() -> None:
    """``experiment define`` was removed in PR 6.5 Phase 2."""
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "experiment",
                "define",
                "ci-benchmark",
                "--limit",
                "1",
                "--worker",
                "test-worker",
                "--model",
                "stub:constant",
                "--evaluator",
                "test-rubric",
                "--sandbox",
                "test-sandbox",
                "--extras",
                "test-extra",
            ]
        )


def test_experiment_run_subcommand_is_no_longer_registered() -> None:
    """``experiment run`` was removed in PR 6.5 Phase 2."""
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["experiment", "run", str(uuid4())])


def test_experiment_list_logs_rows_without_printing(monkeypatch, caplog, capsys):
    class FakeReadService:
        def list_experiments(self, *, limit: int):
            assert limit == 3
            return [_summary(name="alpha"), _summary(name="beta", status="running", run_count=2)]

    monkeypatch.setattr(experiment_cmd, "ExperimentReadService", FakeReadService)
    caplog.set_level(logging.INFO, logger=experiment_cmd.__name__)

    rc = experiment_cmd.handle_experiment_list(Namespace(limit=3))

    assert rc == 0
    assert capsys.readouterr().out == ""
    assert "alpha" in caplog.text
    assert "beta" in caplog.text
    assert "running" in caplog.text


def test_experiment_show_logs_detail_without_printing(monkeypatch, caplog, capsys):
    run_id = uuid4()

    class FakeReadService:
        def get_experiment(self, experiment_id):
            return ExperimentDetailDto(
                experiment=_summary(experiment_id=experiment_id),
                runs=[
                    ExperimentRunRowDto(
                        run_id=run_id,
                        workflow_definition_id=uuid4(),
                        benchmark_type="ci-benchmark",
                        instance_key="sample-a",
                        status="completed",
                        created_at="2026-04-27T12:00:00Z",
                    )
                ],
                sample_selection={"instance_keys": ["sample-a"]},
            )

    experiment_id = uuid4()
    monkeypatch.setattr(experiment_cmd, "ExperimentReadService", FakeReadService)
    caplog.set_level(logging.INFO, logger=experiment_cmd.__name__)

    rc = experiment_cmd.handle_experiment_show(Namespace(experiment_id=str(experiment_id)))

    assert rc == 0
    assert capsys.readouterr().out == ""
    assert str(experiment_id) in caplog.text
    assert str(run_id) in caplog.text
    assert "sample-a" in caplog.text


# ---------------------------------------------------------------------------
# tags subcommand tests
# ---------------------------------------------------------------------------


class _FakeExecResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def test_experiment_tags_lists_distinct_tags(monkeypatch, caplog):
    class FakeRepo:
        def distinct_experiment_tags(self, session):
            return ["alpha", "beta"]

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    repo = FakeRepo()
    session = FakeSession()
    session.exec = lambda _query: _FakeExecResult(repo.distinct_experiment_tags(session))
    monkeypatch.setattr(experiment_cmd, "get_session", lambda: session)
    caplog.set_level(logging.INFO, logger=experiment_cmd.__name__)

    rc = experiment_cmd.handle_experiment_tags(Namespace())

    assert rc == 0
    assert "alpha" in caplog.text
    assert "beta" in caplog.text


def test_experiment_tags_handles_empty(monkeypatch, caplog):
    class FakeRepo:
        def distinct_experiment_tags(self, session):
            return []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    repo = FakeRepo()
    session = FakeSession()
    session.exec = lambda _query: _FakeExecResult(repo.distinct_experiment_tags(session))
    monkeypatch.setattr(experiment_cmd, "get_session", lambda: session)
    caplog.set_level(logging.INFO, logger=experiment_cmd.__name__)

    rc = experiment_cmd.handle_experiment_tags(Namespace())

    assert rc == 0
    # The handler logs a helpful message when no tags exist
    assert caplog.text != ""


# ---------------------------------------------------------------------------
# by-tag subcommand tests
# ---------------------------------------------------------------------------


def test_experiment_by_tag_lists_definitions_with_latest_run_status(monkeypatch, caplog):
    def_id_a = uuid4()
    def_id_b = uuid4()

    class FakeBdr:
        def __init__(self, ident, name):
            self.id = ident
            self.name = name
            self.benchmark_type = "ci-benchmark"
            self.status = "defined"

    fake_records = [FakeBdr(def_id_a, "exp-a"), FakeBdr(def_id_b, "exp-b")]

    class FakeRun:
        def __init__(self, status):
            self.status = status

    def fake_latest(definition_id):
        if definition_id == def_id_a:
            return FakeRun("completed")
        return None

    class FakeRepo:
        def list_by_experiment_tag(self, session, tag):
            assert tag == "my-tag"
            return fake_records

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    repo = FakeRepo()
    session = FakeSession()
    session.exec = lambda _query: _FakeExecResult(repo.list_by_experiment_tag(session, "my-tag"))
    monkeypatch.setattr(experiment_cmd, "get_session", lambda: session)
    monkeypatch.setattr(experiment_cmd, "latest_run_for_definition", fake_latest)
    caplog.set_level(logging.INFO, logger=experiment_cmd.__name__)

    rc = experiment_cmd.handle_experiment_by_tag(Namespace(tag="my-tag"))

    assert rc == 0
    assert "exp-a" in caplog.text
    assert "exp-b" in caplog.text
    assert "completed" in caplog.text
    assert "no runs" in caplog.text
