from argparse import Namespace
import sys

from ergon_cli.domains.examples.catalogue import get_example, list_examples
from ergon_cli.domains.examples.models import ExampleCommand, ExampleDefinition
from ergon_cli.domains.examples.preflight import (
    LLAMA_SERVER_TEMPLATE,
    ExampleSetupError,
    check_example_setup,
)
from ergon_cli.domains.examples.runner import ExampleRunError, run_example_script
from ergon_cli.shared import exit_codes
from ergon_cli.shared.output import render_table, render_text


def handle_examples(args: Namespace) -> int:
    command = _command_from_args(args)
    if command.action == "list":
        print(render_examples_list())
        return exit_codes.OK

    if command.example is None:
        print("Example slug is required.", file=sys.stderr)
        return exit_codes.USAGE

    example = get_example(command.example)
    if example is None:
        print(f"Unknown example: {command.example}", file=sys.stderr)
        return exit_codes.NOT_FOUND

    if command.action == "info":
        print(render_example_info(example))
        return exit_codes.OK
    if command.action == "check":
        return _handle_check(command)
    if command.action == "run":
        return _handle_run(example, command)

    print(f"Unknown examples action: {command.action}", file=sys.stderr)
    return exit_codes.USAGE


def render_examples_list() -> str:
    rows = [(example.slug, example.short_description) for example in list_examples()]
    return render_table(("Example", "Description"), rows)


def render_example_info(example: ExampleDefinition) -> str:
    lines: list[object] = [
        example.display_name,
        "",
        "Purpose:",
        f"  {example.purpose}",
        "",
        "Prerequisites:",
    ]
    lines.extend(f"  - {prerequisite}" for prerequisite in example.prerequisites)
    lines.extend(("", "Supported options:"))
    for option in example.options:
        default = f" (default: {option.default})" if option.default is not None else ""
        lines.append(f"  {option.flag}: {option.description}{default}")
    lines.extend(("", "Python path:", f"  {example.script_path}"))
    return render_text(lines)


def _handle_check(command: ExampleCommand) -> int:
    try:
        result = check_example_setup(command)
    except ExampleSetupError as exc:
        _print_setup_error(exc)
        return exit_codes.RUNTIME_ERROR

    lines = ["Preflight checks passed."]
    if result.discovered_model:
        lines.append(f"Discovered llama.cpp model: {result.discovered_model}")
    print(render_text(lines))
    return exit_codes.OK


def _handle_run(example: ExampleDefinition, command: ExampleCommand) -> int:
    try:
        check_example_setup(command)
    except ExampleSetupError as exc:
        _print_setup_error(exc)
        return exit_codes.RUNTIME_ERROR

    print(f"Launching {example.slug} via {example.script_path}")
    try:
        return run_example_script(example, command)
    except ExampleRunError as exc:
        print(f"Run error: {exc}", file=sys.stderr)
        return exit_codes.RUNTIME_ERROR


def _print_setup_error(exc: ExampleSetupError) -> None:
    print(f"Setup error: {exc}", file=sys.stderr)
    print(f"Start llama.cpp with: {LLAMA_SERVER_TEMPLATE}", file=sys.stderr)


def _command_from_args(args: Namespace) -> ExampleCommand:
    values = vars(args)
    return ExampleCommand(
        action=args.examples_action,
        example=values.get("example"),
        limit=values.get("limit"),
        base_url=values.get("base_url"),
        model=values.get("model"),
        model_target=values.get("model_target"),
        max_iterations=values.get("max_iterations"),
    )
