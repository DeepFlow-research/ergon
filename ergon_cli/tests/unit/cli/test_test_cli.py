from argparse import Namespace

import ergon_cli.domains.tests.service as test_service
import ergon_cli.domains.tests.commands as test_commands
from ergon_cli.domains.tests.commands import handle_test
from ergon_cli.domains.tests.models import TestCommand as CliTestCommand


def test_unit_cli_resolves_to_cli_pytest_command() -> None:
    command = test_service.resolve_test_command(
        CliTestCommand(suite="unit", domain="cli", dry_run=True, extra_args=())
    )

    assert command.commands == (("pnpm", "run", "test:cli:unit"),)


def test_extra_args_are_appended_to_each_resolved_command() -> None:
    command = test_service.resolve_test_command(
        CliTestCommand(suite="unit", domain="cli", dry_run=True, extra_args=("-k", "parser"))
    )

    assert command.commands[0] == ("pnpm", "run", "test:cli:unit", "--", "-k", "parser")


def test_dry_run_prints_command_without_executing(monkeypatch, capsys) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run must not execute subprocesses")

    monkeypatch.setattr(test_service.subprocess, "run", fail_if_called)

    rc = handle_test(Namespace(test_suite="unit", test_domain="cli", dry_run=True, extra_args=[]))

    assert rc == 0
    assert "pnpm run test:cli:unit" in capsys.readouterr().out


def test_handler_strips_pass_through_separator(monkeypatch) -> None:
    captured = {}

    def fake_run(command, emit=None):
        del emit
        captured["command"] = command
        return 0

    monkeypatch.setattr(test_commands, "run_test_command", fake_run)

    rc = handle_test(
        Namespace(
            test_suite="unit",
            test_domain="cli",
            dry_run=False,
            extra_args=["--", "-k", "parser"],
        )
    )

    assert rc == 0
    assert captured["command"].extra_args == ("-k", "parser")


def test_handler_allows_dry_run_after_smoke_target(monkeypatch) -> None:
    captured = {}

    def fake_run(command, emit=None):
        del emit
        captured["command"] = command
        return 0

    monkeypatch.setattr(test_commands, "run_test_command", fake_run)

    rc = handle_test(
        Namespace(
            test_suite="swebench-verified",
            test_domain="smoke",
            dry_run=False,
            extra_args=["--dry-run", "--", "--timeout=330"],
        )
    )

    assert rc == 0
    assert captured["command"].dry_run is True
    assert captured["command"].extra_args == ("--timeout=330",)


def test_handler_treats_smoke_passthrough_as_full_target(monkeypatch) -> None:
    captured = {}

    def fake_run(command, emit=None):
        del emit
        captured["command"] = command
        return 0

    monkeypatch.setattr(test_commands, "run_test_command", fake_run)

    rc = handle_test(
        Namespace(
            test_suite="--maxfail=1",
            test_domain="smoke",
            dry_run=False,
            extra_args=[],
        )
    )

    assert rc == 0
    assert captured["command"].suite == "full"
    assert captured["command"].extra_args == ("--maxfail=1",)


def test_full_unit_is_explicit_all_unit_command() -> None:
    command = test_service.resolve_test_command(
        CliTestCommand(suite="unit", domain="full", dry_run=True, extra_args=())
    )

    assert command.commands == (("pnpm", "run", "test:full:unit"),)


def test_benchmark_smoke_target_resolves_to_one_e2e_file() -> None:
    command = test_service.resolve_test_command(
        CliTestCommand(domain="smoke", suite="swebench-verified", dry_run=True, extra_args=())
    )

    assert command.commands == (("uv", "run", "pytest", "tests/e2e/test_swebench_smoke.py", "-v"),)


def test_test_command_collects_unknown_pytest_flags() -> None:
    from ergon_cli.main import _parse_args

    parser, args = _parse_args(["test", "cli", "unit", "--dry-run", "-vvv"])

    assert parser.prog == "ergon"
    assert args.command == "test"
    assert args.extra_args == ["-vvv"]


def test_smoke_tests_receive_local_stack_environment(monkeypatch) -> None:
    captured = {}
    for name in (
        "ERGON_DATABASE_URL",
        "ERGON_API_BASE_URL",
        "ERGON_DASHBOARD_URL",
        "PLAYWRIGHT_BASE_URL",
        "INNGEST_API_BASE_URL",
        "INNGEST_DEV",
        "INNGEST_EVENT_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    def fake_run(argv, *, check, env):
        captured["argv"] = argv
        captured["check"] = check
        captured["env"] = env

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(test_service.subprocess, "run", fake_run)

    rc = test_service.run_test_command(
        CliTestCommand(domain="smoke", suite="minif2f", extra_args=())
    )

    assert rc == 0
    assert captured["argv"] == ("uv", "run", "pytest", "tests/e2e/test_minif2f_smoke.py", "-v")
    assert captured["check"] is False
    assert (
        captured["env"]["ERGON_DATABASE_URL"] == "postgresql://ergon:ergon_dev@localhost:5433/ergon"
    )
    assert captured["env"]["ERGON_API_BASE_URL"] == "http://127.0.0.1:9000"
    assert captured["env"]["ERGON_DASHBOARD_URL"] == "http://127.0.0.1:3001"
    assert captured["env"]["PLAYWRIGHT_BASE_URL"] == "http://127.0.0.1:3001"
    assert captured["env"]["INNGEST_API_BASE_URL"] == "http://localhost:8289"
    assert captured["env"]["INNGEST_DEV"] == "1"
    assert captured["env"]["INNGEST_EVENT_KEY"] == "dev"


def test_smoke_tests_preserve_explicit_environment(monkeypatch) -> None:
    captured = {}
    monkeypatch.setenv("ERGON_DATABASE_URL", "postgresql://custom/db")
    monkeypatch.setenv("PLAYWRIGHT_BASE_URL", "http://localhost:3999")

    def fake_run(argv, *, check, env):
        del argv, check
        captured["env"] = env

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(test_service.subprocess, "run", fake_run)

    rc = test_service.run_test_command(
        CliTestCommand(domain="smoke", suite="minif2f", extra_args=())
    )

    assert rc == 0
    assert captured["env"]["ERGON_DATABASE_URL"] == "postgresql://custom/db"
    assert captured["env"]["PLAYWRIGHT_BASE_URL"] == "http://localhost:3999"
