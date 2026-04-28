import importlib
import subprocess
import sys


def test_telemetry_models_can_import_before_public_api() -> None:
    telemetry = importlib.import_module("ergon_core.core.persistence.telemetry.models")
    shared_enums = importlib.import_module("ergon_core.core.persistence.shared.enums")
    public_api = importlib.import_module("ergon_core.api")

    assert shared_enums.RunResourceKind.REPORT.value == "report"
    assert not hasattr(telemetry, "RunResourceKind")
    assert not hasattr(public_api, "RunResourceKind")


def test_public_api_root_stays_authoring_scoped() -> None:
    public_api = importlib.import_module("ergon_core.api")

    assert "__getattr__" not in public_api.__dict__
    assert not hasattr(public_api, "RunResourceView")
    assert not hasattr(public_api, "CriterionRuntime")
    assert not hasattr(public_api, "CommandResult")
    assert not hasattr(public_api, "SandboxResult")
    assert not hasattr(public_api, "Tool")


def test_object_first_experiment_run_api_is_retired() -> None:
    public_api = importlib.import_module("ergon_core.api")

    assert not hasattr(public_api, "ExperimentRunHandle")
    assert not hasattr(public_api.Experiment, "run")


def test_core_api_app_imports_without_context_payload_cycle() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", "import ergon_core.core.api.app; print('ok')"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout
