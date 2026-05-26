import importlib
from pathlib import Path


def test_authoring_modules_do_not_import_persistence_or_sqlmodel() -> None:
    forbidden = ("ergon_core.core.persistence", "sqlmodel", "get_session", "definition_writer")
    for module_name in (
        "ergon_core.api.experiment.sample",
        "ergon_core.api.experiment.environment",
        "ergon_core.api.experiment.sampling",
        "ergon_core.api.experiment.experiment",
        "ergon_core.api.experiment.persistence",
    ):
        source = Path(importlib.import_module(module_name).__file__).read_text()
        for token in forbidden:
            assert token not in source


def test_public_api_exports_new_names_and_not_retired_names() -> None:
    import ergon_core.api as public_api

    assert "Task" in public_api.__all__
    assert "Sample" in public_api.__all__
    assert "Environment" in public_api.__all__
    assert "Experiment" in public_api.__all__
    assert "ExperimentRef" in public_api.__all__
    assert "ExperimentSubmitResult" in public_api.__all__
    assert "RandomSampler" in public_api.__all__
    assert "Sampler" in public_api.__all__
    assert "SamplingContext" in public_api.__all__
    assert "SamplingHistory" in public_api.__all__
    assert "persist_experiment" in public_api.__all__
    assert "SourceDescriptor" not in public_api.__all__
    assert "EnvironmentSource" not in public_api.__all__
    assert "Episode" not in public_api.__all__
    assert "ExperimentRunHandle" not in public_api.__all__


def test_environment_and_experiment_are_not_replay_contracts() -> None:
    from ergon_core.api import Environment, Experiment

    assert not hasattr(Environment, "from_definition")
    assert not hasattr(Experiment, "from_definition")


def test_authoring_api_uses_grouped_experiment_package() -> None:
    root = Path(__file__).resolve().parents[3] / "ergon_core" / "api"

    assert (root / "experiment" / "sample.py").exists()
    assert not (root / "sample.py").exists()
    assert not (root / "environment.py").exists()
    assert not (root / "sampling.py").exists()
