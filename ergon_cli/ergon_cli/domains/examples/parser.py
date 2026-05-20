import argparse

from ergon_cli.domains.examples.commands import handle_examples
from ergon_cli.domains.examples.catalogue import (
    DEFAULT_LLAMA_CPP_BASE_URL,
    DEFAULT_MINIF2F_LIMIT,
    DEFAULT_MINIF2F_MAX_ITERATIONS,
)


def register_examples_parser(subparsers: argparse._SubParsersAction) -> None:
    examples_parser = subparsers.add_parser("examples", help="List and run shipped examples")
    examples_subparsers = examples_parser.add_subparsers(dest="examples_action", required=True)

    examples_subparsers.add_parser("list", help="List available examples").set_defaults(
        handler=handle_examples
    )

    info_parser = examples_subparsers.add_parser("info", help="Show example details")
    info_parser.add_argument("example", help="Example slug")
    info_parser.set_defaults(handler=handle_examples)

    check_parser = examples_subparsers.add_parser(
        "check", help="Validate example prerequisites without launching"
    )
    check_parser.add_argument("example", help="Example slug")
    _add_common_options(check_parser)
    check_parser.set_defaults(handler=handle_examples)

    run_parser = examples_subparsers.add_parser("run", help="Run an example script")
    run_parser.add_argument("example", help="Example slug")
    _add_common_options(run_parser)
    run_parser.set_defaults(handler=handle_examples)


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=DEFAULT_MINIF2F_LIMIT,
        help="Number of MiniF2F tasks to launch.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_LLAMA_CPP_BASE_URL,
        help="Base URL for the llama.cpp OpenAI-compatible server.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional llama.cpp model name; encoded as #<model> on the target.",
    )
    parser.add_argument(
        "--model-target",
        default=None,
        help="Optional full Ergon model target. Overrides --base-url and --model.",
    )
    parser.add_argument(
        "--max-iterations",
        type=_positive_int,
        default=DEFAULT_MINIF2F_MAX_ITERATIONS,
        help="Maximum ReAct tool iterations per MiniF2F task.",
    )


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"{value!r} is not a positive integer")
    return parsed
