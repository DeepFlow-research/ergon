import os
import subprocess
from collections.abc import Callable

from ergon_cli.domains.tests.catalog import (
    BACKEND_E2E,
    BACKEND_INTEGRATION,
    BACKEND_SMOKE,
    DASHBOARD_CONTRACTS,
    DASHBOARD_SMOKE,
    DASHBOARD_UNIT,
    ENVIRONMENT_SMOKE_ALL,
    ENVIRONMENT_SMOKE_COMMANDS,
    PYTHON_UNIT_ALL,
    PYTHON_UNIT_COMMANDS,
    REAL_LLM,
)
from ergon_cli.domains.tests.models import ResolvedTestCommand, TestCommand
from ergon_cli.shared import exit_codes
from ergon_core.core.shared.settings import settings


def resolve_test_command(command: TestCommand) -> ResolvedTestCommand:
    if command.suite == "list":
        return ResolvedTestCommand(label="Available test suites", commands=())
    if command.domain == "smoke":
        commands = _environment_smoke_commands(command.suite)
    elif command.suite == "unit":
        commands = _unit_commands(command.domain)
    elif command.suite == "integration":
        _require_domain(command, "backend")
        commands = (BACKEND_INTEGRATION,)
    elif command.suite == "smoke":
        commands = _smoke_commands(command.domain)
    elif command.suite == "e2e":
        _require_domain(command, "backend")
        commands = (BACKEND_E2E,)
    elif command.domain == "real-llm" and command.suite == "full":
        commands = (REAL_LLM,)
    elif command.domain == "full" and command.suite == "full":
        commands = (PYTHON_UNIT_ALL, BACKEND_INTEGRATION, DASHBOARD_UNIT, DASHBOARD_CONTRACTS)
    else:
        raise ValueError(f"unsupported test target: {command.domain} {command.suite}")
    return ResolvedTestCommand(
        label=f"{command.domain}:{command.suite}",
        commands=tuple(_append_extra_args(cmd, command.extra_args) for cmd in commands),
    )


def run_test_command(command: TestCommand, emit: Callable[[str], None] | None = None) -> int:
    resolved = resolve_test_command(command)
    if command.suite == "list":
        _emit_lines(available_suites(), emit)
        return exit_codes.OK
    for argv in resolved.commands:
        _emit_lines((f"$ {' '.join(argv)}",), emit)
        if command.dry_run:
            continue
        env = os.environ.copy()
        if command.domain == "real-llm":
            env["ERGON_REAL_LLM"] = "1"
        if _needs_local_stack_env(command):
            _apply_local_stack_env(env)
        result = subprocess.run(argv, check=False, env=env)
        if result.returncode != 0:
            return result.returncode
    return exit_codes.OK


def available_suites() -> tuple[str, ...]:
    return (
        "smoke: full, researchrubrics, minif2f, swebench-verified",
        "full: unit, smoke, full",
        "core: unit",
        "builtins: unit",
        "cli: unit",
        "ingestion: unit",
        "dashboard: unit, smoke",
        "backend: integration, smoke, e2e",
        "real-llm: full",
    )


def _emit_lines(lines: tuple[str, ...], emit: Callable[[str], None] | None) -> None:
    if emit is None:
        return
    for line in lines:
        emit(line)


def _unit_commands(domain: str) -> tuple[tuple[str, ...], ...]:
    if domain == "full":
        return (PYTHON_UNIT_ALL,)
    if domain == "dashboard":
        return (DASHBOARD_UNIT,)
    if domain in PYTHON_UNIT_COMMANDS:
        return (PYTHON_UNIT_COMMANDS[domain],)
    raise ValueError(f"unit tests do not support domain {domain!r}")


def _smoke_commands(domain: str) -> tuple[tuple[str, ...], ...]:
    if domain == "full":
        return (BACKEND_SMOKE, DASHBOARD_SMOKE)
    if domain == "backend":
        return (BACKEND_SMOKE,)
    if domain == "dashboard":
        return (DASHBOARD_SMOKE,)
    raise ValueError(f"smoke tests do not support domain {domain!r}")


def _environment_smoke_commands(target: str) -> tuple[tuple[str, ...], ...]:
    if target == "full":
        return (ENVIRONMENT_SMOKE_ALL,)
    if target in ENVIRONMENT_SMOKE_COMMANDS:
        return (ENVIRONMENT_SMOKE_COMMANDS[target],)
    raise ValueError(f"environment smoke tests do not support target {target!r}")


def _require_domain(command: TestCommand, expected: str) -> None:
    if command.domain != expected:
        raise ValueError(f"{command.suite} tests require domain {expected!r}")


def _append_extra_args(command: tuple[str, ...], extra_args: tuple[str, ...]) -> tuple[str, ...]:
    if not extra_args:
        return command
    if command[:2] == ("pnpm", "run"):
        return (*command, "--", *extra_args)
    return (*command, *extra_args)


def _needs_local_stack_env(command: TestCommand) -> bool:
    return command.domain in {"smoke", "real-llm"} or command.suite in {
        "e2e",
        "full",
        "integration",
        "smoke",
    }


def _apply_local_stack_env(env: dict[str, str]) -> None:
    env.setdefault("ERGON_DATABASE_URL", settings.database_url)
    env.setdefault("ERGON_API_BASE_URL", settings.api_base_url)
    env.setdefault("ERGON_DASHBOARD_URL", settings.dashboard_base_url)
    env.setdefault("PLAYWRIGHT_BASE_URL", settings.dashboard_base_url)
    env.setdefault("INNGEST_API_BASE_URL", settings.inngest_api_base_url)
    env.setdefault("INNGEST_DEV", "1" if settings.inngest_dev else "0")
    env.setdefault("INNGEST_EVENT_KEY", settings.inngest_event_key)
