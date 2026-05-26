from uuid import uuid4

from ergon_cli.domains.experiments.commands import handle_experiment_show
from ergon_cli.domains.experiments.models import (
    ExperimentCliState,
    ExperimentEnvironmentCliState,
)
from ergon_cli.domains.samples.commands import sample_events_command
from ergon_cli.domains.samples.models import SampleEventCliState
from argparse import Namespace


def test_experiment_state_rendering_uses_environment_and_sample_vocabulary(
    monkeypatch,
    capsys,
) -> None:
    experiment_id = uuid4()

    def fake_show(command):
        return ExperimentCliState(
            experiment_id=command.experiment_id,
            name="mixed-training",
            environments=(
                ExperimentEnvironmentCliState(
                    environment_id=uuid4(),
                    environment_name="mini-validation",
                    source_mode="materialized",
                    sample_count=3,
                    selected_count=3,
                ),
            ),
            sample_count=3,
            sampler_invocation_count=1,
        )

    monkeypatch.setattr("ergon_cli.domains.experiments.commands.show_experiment", fake_show)

    rc = handle_experiment_show(Namespace(experiment_id=str(experiment_id)))

    assert rc == 0
    text = capsys.readouterr().out
    assert "mixed-training" in text
    assert "mini-validation" in text
    assert "SAMPLE_COUNT" in text
    assert "RUN_COUNT" not in text
    assert "DEFINITION" not in text


def test_sample_event_rendering_uses_typed_wal_events(monkeypatch, capsys) -> None:
    sample_id = uuid4()

    def fake_events(command):
        return (
            SampleEventCliState(
                event_type="sample.status_changed",
                target="sample",
                timestamp="2026-05-26T00:00:00Z",
            ),
            SampleEventCliState(
                event_type="task.added",
                target="task",
                timestamp="2026-05-26T00:00:01Z",
            ),
            SampleEventCliState(
                event_type="worker.added",
                target="task",
                timestamp="2026-05-26T00:00:02Z",
            ),
        )

    monkeypatch.setattr("ergon_cli.domains.samples.commands.list_sample_events", fake_events)

    rc = sample_events_command(Namespace(sample_id=str(sample_id)))

    assert rc == 0
    text = capsys.readouterr().out
    assert "sample.status_changed" in text
    assert "task.added" in text
    assert "worker.added" in text
    assert "GraphMutation" not in text
