"""Tests for the ``ergon examples`` CLI domain."""

from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import ergon_cli.domains.examples.preflight as examples_preflight
import ergon_cli.domains.examples.runner as examples_runner
from ergon_cli.domains.examples.commands import handle_examples
from ergon_cli.main import build_parser
from ergon_cli.domains.examples.preflight import ExampleSetupError, PreflightResult


def test_examples_subcommands_are_registered_in_main_parser() -> None:
    parser = build_parser()

    list_args = parser.parse_args(["examples", "list"])
    info_args = parser.parse_args(["examples", "info", "minif2f-local-llamacpp"])
    check_args = parser.parse_args(
        [
            "examples",
            "check",
            "minif2f-local-llamacpp",
            "--base-url",
            "http://localhost:8080",
        ]
    )
    run_args = parser.parse_args(
        [
            "examples",
            "run",
            "minif2f-local-llamacpp",
            "--limit",
            "3",
            "--model",
            "local-proof-model",
            "--max-iterations",
            "4",
        ]
    )

    assert list_args.command == "examples"
    assert list_args.examples_action == "list"
    assert info_args.examples_action == "info"
    assert check_args.examples_action == "check"
    assert check_args.base_url == "http://localhost:8080"
    assert run_args.examples_action == "run"
    assert run_args.limit == 3
    assert run_args.model == "local-proof-model"
    assert run_args.max_iterations == 4


def test_console_entrypoint_help_does_not_import_examples_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("examples"):
            raise ModuleNotFoundError("No module named 'examples'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    parser = build_parser()
    args = parser.parse_args(["examples", "list"])

    assert args.command == "examples"
    assert args.examples_action == "list"


def test_list_prints_minif2f_example(capsys: pytest.CaptureFixture[str]) -> None:
    rc = handle_examples(Namespace(examples_action="list"))

    assert rc == 0
    out = capsys.readouterr().out
    assert "minif2f-local-llamacpp" in out
    assert "MiniF2F" in out


def test_info_prints_prerequisites_options_and_script_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = handle_examples(Namespace(examples_action="info", example="minif2f-local-llamacpp"))

    assert rc == 0
    out = capsys.readouterr().out
    assert "Run three MiniF2F" in out
    assert "E2B_API_KEY" in out
    assert "--limit" in out
    assert "--base-url" in out
    assert "examples/getting_started/01_minif2f_local_llamacpp/run.py" in out


def test_check_runs_preflight_without_launching(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    def fake_preflight(*, base_url: str) -> PreflightResult:
        calls.append(base_url)
        return PreflightResult(discovered_model="mini-proof-local")

    monkeypatch.setattr(examples_preflight, "preflight_llamacpp_and_e2b", fake_preflight)

    rc = handle_examples(
        Namespace(
            examples_action="check",
            example="minif2f-local-llamacpp",
            base_url="http://localhost:8080",
            model=None,
            model_target=None,
            limit=None,
            max_iterations=None,
        )
    )

    assert rc == 0
    assert calls == ["http://localhost:8080"]
    out = capsys.readouterr().out
    assert "Preflight checks passed" in out
    assert "mini-proof-local" in out


def test_check_reports_llama_server_template_when_preflight_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_preflight(*, base_url: str) -> PreflightResult:
        raise ExampleSetupError("Could not reach the llama.cpp server")

    monkeypatch.setattr(examples_preflight, "preflight_llamacpp_and_e2b", fake_preflight)

    rc = handle_examples(
        Namespace(
            examples_action="check",
            example="minif2f-local-llamacpp",
            base_url="http://localhost:8080",
            model=None,
            model_target=None,
            limit=None,
            max_iterations=None,
        )
    )

    assert rc == 1
    err = capsys.readouterr().err
    assert "Could not reach the llama.cpp server" in err
    assert "llama-server --model /path/to/model.gguf --host 127.0.0.1 --port 8080" in err


def test_run_invokes_example_script_with_translated_args(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    def fake_preflight(*, base_url: str) -> PreflightResult:
        calls.append(base_url)
        return PreflightResult(discovered_model="mini-proof-local")

    completed = MagicMock(returncode=0)
    monkeypatch.setattr(examples_preflight, "preflight_llamacpp_and_e2b", fake_preflight)
    monkeypatch.setattr(examples_runner.subprocess, "run", MagicMock(return_value=completed))

    rc = handle_examples(
        Namespace(
            examples_action="run",
            example="minif2f-local-llamacpp",
            base_url="http://localhost:8080",
            model="local-proof-model",
            model_target=None,
            limit=3,
            max_iterations=4,
        )
    )

    assert rc == 0
    assert calls == ["http://localhost:8080"]
    subprocess_run = examples_runner.subprocess.run
    subprocess_run.assert_called_once()
    args, kwargs = subprocess_run.call_args
    command = args[0]
    assert (
        Path(command[1])
        .as_posix()
        .endswith("examples/getting_started/01_minif2f_local_llamacpp/run.py")
    )
    assert command[2:] == [
        "--limit",
        "3",
        "--base-url",
        "http://localhost:8080",
        "--model",
        "local-proof-model",
        "--max-iterations",
        "4",
    ]
    assert (kwargs["cwd"] / "pyproject.toml").is_file()
    assert "env" in kwargs
    assert "Launching minif2f-local-llamacpp" in capsys.readouterr().out


def test_run_reports_missing_source_checkout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_preflight(*, base_url: str) -> PreflightResult:
        return PreflightResult(discovered_model="mini-proof-local")

    monkeypatch.setattr(examples_preflight, "preflight_llamacpp_and_e2b", fake_preflight)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ERGON_REPO_ROOT", raising=False)

    rc = handle_examples(
        Namespace(
            examples_action="run",
            example="minif2f-local-llamacpp",
            base_url="http://localhost:8080",
            model=None,
            model_target=None,
            limit=3,
            max_iterations=4,
        )
    )

    assert rc == 1
    assert "ERGON_REPO_ROOT" in capsys.readouterr().err


def test_run_can_use_configured_repo_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_repo = tmp_path / "repo"
    script = fake_repo / "examples/getting_started/01_minif2f_local_llamacpp/run.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('ok')\n")

    def fake_preflight(*, base_url: str) -> PreflightResult:
        return PreflightResult(discovered_model="mini-proof-local")

    completed = MagicMock(returncode=0)
    monkeypatch.setenv("ERGON_REPO_ROOT", str(fake_repo))
    monkeypatch.setattr(examples_preflight, "preflight_llamacpp_and_e2b", fake_preflight)
    monkeypatch.setattr(examples_runner.subprocess, "run", MagicMock(return_value=completed))

    rc = handle_examples(
        Namespace(
            examples_action="run",
            example="minif2f-local-llamacpp",
            base_url="http://localhost:8080",
            model=None,
            model_target=None,
            limit=3,
            max_iterations=4,
        )
    )

    assert rc == 0
    assert examples_runner.subprocess.run.call_args.kwargs["cwd"] == fake_repo


def test_run_uses_model_target_for_preflight_and_script_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_preflight(*, base_url: str) -> PreflightResult:
        calls.append(base_url)
        return PreflightResult(discovered_model="mini-proof-local")

    completed = MagicMock(returncode=0)
    monkeypatch.setattr(examples_preflight, "preflight_llamacpp_and_e2b", fake_preflight)
    monkeypatch.setattr(examples_runner.subprocess, "run", MagicMock(return_value=completed))

    rc = handle_examples(
        Namespace(
            examples_action="run",
            example="minif2f-local-llamacpp",
            base_url="http://localhost:8080",
            model="ignored-model",
            model_target="llamacpp:http://model-router:9090#served-model",
            limit=2,
            max_iterations=5,
        )
    )

    assert rc == 0
    assert calls == ["http://model-router:9090"]
    command = examples_runner.subprocess.run.call_args.args[0]
    assert command[2:] == [
        "--limit",
        "2",
        "--model-target",
        "llamacpp:http://model-router:9090#served-model",
        "--max-iterations",
        "5",
    ]
