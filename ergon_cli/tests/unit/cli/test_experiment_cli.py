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
from ergon_core.core.application.experiments.models import (
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
            "--evaluator",
            "test-rubric",
            "--sandbox",
            "test-sandbox",
            "--extras",
            "test-extra",
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


@pytest.mark.parametrize(
    "missing_flag", ["--worker", "--model", "--evaluator", "--sandbox", "--extras"]
)
def test_experiment_define_requires_explicit_runtime_choices(missing_flag: str) -> None:
    parser = build_parser()
    argv = [
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
    flag_index = argv.index(missing_flag)
    del argv[flag_index : flag_index + 2]

    with pytest.raises(SystemExit):
        parser.parse_args(argv)


def test_experiment_define_validates_explicit_registry_choices(monkeypatch) -> None:
    class BenchmarkWithNoExtras:
        onboarding_deps = type(
            "Deps",
            (),
            {"extras": (), "optional_keys": (), "e2b": False},
        )()

    monkeypatch.setattr(
        experiment_cmd,
        "_load_registry",
        lambda: (
            {"ci-benchmark": BenchmarkWithNoExtras},
            {"test-worker": object()},
            {"test-rubric": object()},
            {"test-sandbox": object()},
            {"openai": object()},
        ),
    )

    valid_args = Namespace(
        benchmark_slug="ci-benchmark",
        worker="test-worker",
        evaluator="test-rubric",
        sandbox="test-sandbox",
        model="openai:gpt-4o",
        extras=["none"],
    )
    assert experiment_cmd.validate_explicit_runtime_choices(valid_args) == ("none",)

    invalid_args = Namespace(
        benchmark_slug="ci-benchmark",
        worker="missing-worker",
        evaluator="test-rubric",
        sandbox="test-sandbox",
        model="openai:gpt-4o",
        extras=["none"],
    )
    with pytest.raises(ValueError, match="Unknown worker slug"):
        experiment_cmd.validate_explicit_runtime_choices(invalid_args)


def test_benchmark_run_is_registered_as_experiment_wrapper() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "benchmark",
            "run",
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

    assert args.bench_action == "run"
    assert args.slug == "ci-benchmark"
    assert args.worker == "test-worker"
    assert args.evaluator == "test-rubric"
    assert args.sandbox == "test-sandbox"
    assert args.extras == ["test-extra"]


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
    captured_request = None

    class FakeExperimentService:
        def define_benchmark_experiment(self, request):
            nonlocal captured_request
            captured_request = request
            return ExperimentDefineResult(
                experiment_id=experiment_id,
                cohort_id=None,
                benchmark_type=request.benchmark_slug,
                sample_count=1,
                selected_samples=["sample-a"],
            )

        async def run_experiment(self, request):
            return ExperimentRunResult(
                experiment_id=request.experiment_id,
                run_ids=[run_id],
                workflow_definition_ids=[uuid4()],
            )

    monkeypatch.setattr(experiment_cmd, "ensure_db", lambda: None)
    monkeypatch.setattr(experiment_cmd, "ExperimentService", FakeExperimentService)
    monkeypatch.setattr(
        experiment_cmd,
        "_load_registry",
        lambda: (
            {
                "ci-benchmark": type(
                    "BenchmarkWithTestExtra",
                    (),
                    {
                        "onboarding_deps": type(
                            "Deps",
                            (),
                            {"extras": ("test-extra",), "optional_keys": (), "e2b": False},
                        )()
                    },
                )
            },
            {"test-worker": object()},
            {"test-rubric": object()},
            {"test-sandbox": object()},
            {"openai": object()},
        ),
    )
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
            evaluator="test-rubric",
            sandbox="test-sandbox",
            extras=["test-extra"],
            workflow="single",
            max_questions=10,
        )
    )

    assert define_rc == 0
    assert captured_request is not None
    assert captured_request.sandbox_slug == "test-sandbox"
    assert captured_request.dependency_extras == ("test-extra",)

    run_rc = await experiment_cmd.handle_experiment_run(
        Namespace(experiment_id=str(experiment_id), timeout=60, no_wait=False)
    )

    assert run_rc == 0
    assert capsys.readouterr().out == ""
    assert f"EXPERIMENT_ID={experiment_id}" in caplog.text
    assert f"RUN_ID={run_id}" in caplog.text
