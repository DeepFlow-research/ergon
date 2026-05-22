import sys
from argparse import Namespace
from pathlib import Path

from ergon_cli.domains.stack.models import StackCommand, StackResult
from ergon_cli.domains.stack.service import run_stack_command
from ergon_cli.shared.output import render_text


def handle_start(args: Namespace) -> int:
    del args
    return _run(StackCommand(action="start", cwd=Path.cwd()))


def handle_stop(args: Namespace) -> int:
    del args
    return _run(StackCommand(action="stop", cwd=Path.cwd()))


def _run(command: StackCommand) -> int:
    result = run_stack_command(command)
    _print_result(result)
    return result.exit_code


def _print_result(result: StackResult) -> None:
    if result.stdout:
        print(render_text(result.stdout))
    if result.stderr:
        print(render_text(result.stderr), file=sys.stderr)
