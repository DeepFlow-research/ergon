import logging
from argparse import Namespace
from uuid import uuid4

import pytest
from ergon_cli.commands import experiment as experiment_cmd
from ergon_cli.main import build_parser
from ergon_core.core.runtime.services.experiment_read_service import (
    ExperimentDetailDto,
    ExperimentRunRowDto,
    ExperimentSummaryDto,
)
from ergon_core.core.runtime.services.experiment_schemas import (
    ExperimentDefineResult,
    ExperimentRunResult,
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
    parser = build_parser()

    define_args = parser.parse_args(
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
        ]
    )
    run_args = parser.parse_args(["experiment", "run", str(uuid4())])
    show_args = parser.parse_args(["experiment", "show", str(uuid4())])
    list_args = parser.parse_args(["experiment", "list", "--limit", "3"])

    assert define_args.experiment_action == "define"
    assert run_args.experiment_action == "run"
    assert show_args.experiment_action == "show"
    assert list_args.experiment_action == "list"
    assert list_args.limit == 3


def test_benchmark_run_is_not_registered_as_launch_command() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["benchmark", "run", "ci-benchmark"])


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


@pytest.mark.asyncio
async def test_experiment_define_and_run_log_machine_ids_without_printing(
    monkeypatch, caplog, capsys
):
    experiment_id = uuid4()
    run_id = uuid4()

    class FakeDefinitionService:
        def define_benchmark_experiment(self, request):
            return ExperimentDefineResult(
                experiment_id=experiment_id,
                cohort_id=None,
                benchmark_type=request.benchmark_slug,
                sample_count=1,
                selected_samples=["sample-a"],
            )

    class FakeLaunchService:
        async def run_experiment(self, request):
            return ExperimentRunResult(
                experiment_id=request.experiment_id,
                run_ids=[run_id],
                workflow_definition_ids=[uuid4()],
            )

    monkeypatch.setattr(experiment_cmd, "ensure_db", lambda: None)
    monkeypatch.setattr(experiment_cmd, "ExperimentDefinitionService", FakeDefinitionService)
    monkeypatch.setattr(experiment_cmd, "ExperimentLaunchService", FakeLaunchService)
    caplog.set_level(logging.INFO, logger=experiment_cmd.__name__)

    define_rc = experiment_cmd.handle_experiment_define(
        Namespace(
            benchmark_slug="ci-benchmark",
            cohort=None,
            sample_id=None,
            limit=1,
            name=None,
            model="openai:gpt-4o",
            worker="test-worker",
            evaluator=None,
            workflow="single",
            max_questions=10,
        )
    )

    assert define_rc == 0

    run_rc = await experiment_cmd.handle_experiment_run(
        Namespace(experiment_id=str(experiment_id), timeout=60, no_wait=False)
    )

    assert run_rc == 0
    assert capsys.readouterr().out == ""
    assert f"EXPERIMENT_ID={experiment_id}" in caplog.text
    assert f"RUN_ID={run_id}" in caplog.text
