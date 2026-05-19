import logging
from argparse import Namespace
from uuid import uuid4

import pytest
from ergon_cli.commands import experiment as experiment_cmd
from ergon_cli.main import build_parser
from ergon_core.core.views.experiments.models import (
    ExperimentDetailDto,
    ExperimentRunRowDto,
    ExperimentSummaryDto,
)


def _summary(**overrides) -> ExperimentSummaryDto:
    data = {
        "definition_id": uuid4(),
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
    """Show and list are registered for current definition-backed experiments."""
    parser = build_parser()

    show_args = parser.parse_args(["experiment", "show", str(uuid4())])
    list_args = parser.parse_args(["experiment", "list", "--limit", "3"])
    assert show_args.experiment_action == "show"
    assert list_args.experiment_action == "list"
    assert list_args.limit == 3


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
        def get_experiment(self, definition_id):
            return ExperimentDetailDto(
                experiment=_summary(definition_id=definition_id),
                runs=[
                    ExperimentRunRowDto(
                        run_id=run_id,
                        definition_id=uuid4(),
                        benchmark_type="ci-benchmark",
                        instance_key="sample-a",
                        status="completed",
                        created_at="2026-04-27T12:00:00Z",
                    )
                ],
                sample_selection={"instance_keys": ["sample-a"]},
            )

    definition_id = uuid4()
    monkeypatch.setattr(experiment_cmd, "ExperimentReadService", FakeReadService)
    caplog.set_level(logging.INFO, logger=experiment_cmd.__name__)

    rc = experiment_cmd.handle_experiment_show(Namespace(definition_id=str(definition_id)))

    assert rc == 0
    assert capsys.readouterr().out == ""
    assert str(definition_id) in caplog.text
    assert str(run_id) in caplog.text
    assert "sample-a" in caplog.text


def test_experiment_tag_subcommands_are_not_registered() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["experiment", "tags"])
    with pytest.raises(SystemExit):
        parser.parse_args(["experiment", "by-tag", "alpha"])
