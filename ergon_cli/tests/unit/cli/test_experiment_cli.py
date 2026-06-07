from argparse import Namespace
from uuid import uuid4

import pytest
import ergon_cli.domains.experiments.commands as experiment_cmd
import ergon_cli.domains.experiments.service as experiment_domain_service
from ergon_cli.main import build_parser
from ergon_core.core.views.experiments.models import (
    EnvironmentContributionView,
    ExperimentDetailView as CoreExperimentDetailView,
    ExperimentListView,
    ExperimentSampleSummaryView,
)


def _experiment_state(**overrides) -> CoreExperimentDetailView:
    data = {
        "experiment_id": uuid4(),
        "name": "ci experiment",
        "environments": [
            EnvironmentContributionView(
                environment_id=uuid4(),
                environment_name="mini-validation",
                source_mode="materialized",
                sample_count=2,
                selected_count=2,
            )
        ],
        "sample_count": 2,
        "samples": [],
        "sampler_invocations": [],
        "created_at": "2026-04-27T12:00:00Z",
    }
    data.update(overrides)
    return CoreExperimentDetailView.model_validate(data)


def test_experiment_subcommands_are_registered_in_main_parser() -> None:
    """Show and list are registered for current experiments."""
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


def test_experiment_list_prints_rows(monkeypatch, capsys):
    class FakeReadService:
        def list_experiment_states(self, *, limit: int):
            assert limit == 3
            return ExperimentListView(
                items=[
                    _experiment_state(name="alpha"),
                    _experiment_state(name="beta", sample_count=4),
                ]
            )

    monkeypatch.setattr(experiment_domain_service, "ExperimentReadService", FakeReadService)

    rc = experiment_cmd.handle_experiment_list(Namespace(limit=3))

    assert rc == 0
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "beta" in out
    assert "mini-validation" in out
    assert "DEFINITION_ID" not in out
    assert "EXPERIMENT_ID" in out


def test_experiment_show_prints_detail(monkeypatch, capsys):
    sample_id = uuid4()
    experiment_id = uuid4()
    environment_id = uuid4()

    class FakeReadService:
        def get_experiment_state(self, requested_experiment_id):
            assert requested_experiment_id == experiment_id
            return CoreExperimentDetailView(
                experiment_id=experiment_id,
                name="ci experiment",
                environments=[
                    EnvironmentContributionView(
                        environment_id=environment_id,
                        environment_name="mini-validation",
                        source_mode="materialized",
                        sample_count=1,
                        selected_count=1,
                    )
                ],
                sample_count=1,
                samples=[
                    ExperimentSampleSummaryView(
                        sample_id=sample_id,
                        experiment_id=experiment_id,
                        environment_id=environment_id,
                        environment_name="mini-validation",
                        sample_key="sample-a",
                        status="completed",
                        created_at="2026-04-27T12:00:00Z",
                    )
                ],
                created_at="2026-04-27T12:00:00Z",
            )

    monkeypatch.setattr(experiment_domain_service, "ExperimentReadService", FakeReadService)

    rc = experiment_cmd.handle_experiment_show(Namespace(experiment_id=str(experiment_id)))

    assert rc == 0
    out = capsys.readouterr().out
    assert str(experiment_id) in out
    assert str(sample_id) in out
    assert "sample-a" in out
    assert "definition" not in out.lower()


def test_experiment_tag_subcommands_are_no_longer_registered() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["experiment", "tags"])
    with pytest.raises(SystemExit):
        parser.parse_args(["experiment", "by-tag", "alpha"])
