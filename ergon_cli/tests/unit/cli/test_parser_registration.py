from collections.abc import Sequence

import pytest

from ergon_cli.main import build_parser


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["environment", "list"], {"command": "environment", "env_action": "list"}),
        (
            ["experiment", "show", "00000000-0000-0000-0000-000000000000"],
            {"command": "experiment", "experiment_action": "show"},
        ),
        (["sample", "list", "--limit", "3"], {"command": "sample", "sample_action": "list"}),
        (["ingest", "list"], {"command": "ingest", "ingest_action": "list"}),
        (["worker", "list"], {"command": "worker", "worker_action": "list"}),
        (["evaluator", "list"], {"command": "evaluator", "evaluator_action": "list"}),
        (["onboard"], {"command": "onboard"}),
        (["doctor"], {"command": "doctor"}),
        (["examples", "list"], {"command": "examples", "examples_action": "list"}),
        (["start"], {"command": "start"}),
        (["stop"], {"command": "stop"}),
        (["test", "cli", "unit"], {"command": "test", "test_domain": "cli", "test_suite": "unit"}),
    ],
)
def test_domain_parsers_register_representative_commands(
    argv: Sequence[str],
    expected: dict[str, object],
) -> None:
    args = build_parser().parse_args(list(argv))

    assert callable(args.handler)
    for key, value in expected.items():
        assert getattr(args, key) == value


@pytest.mark.parametrize("command", ["workflow", "eval", "train"])
def test_experimental_domains_are_not_public_top_level_commands(command: str) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([command, "--help"])

    assert exc_info.value.code == 2


def test_benchmark_command_is_not_public() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["benchmark", "setup", "minif2f"])

    assert exc_info.value.code == 2


def test_public_help_excludes_experimental_domains(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])

    out = capsys.readouterr().out
    assert "workflow" not in out
    assert "eval                " not in out
    assert "train" not in out


def test_test_command_is_public() -> None:
    args = build_parser().parse_args(["test", "cli", "unit"])

    assert callable(args.handler)
    assert args.command == "test"
    assert args.test_domain == "cli"
    assert args.test_suite == "unit"
