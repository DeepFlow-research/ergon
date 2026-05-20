import argparse
from collections.abc import Sequence

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
        action=_BaseModelConflictAction,
        default=None,
        help="Base URL for the llama.cpp OpenAI-compatible server.",
    )
    parser.add_argument(
        "--model",
        action=_BaseModelConflictAction,
        default=None,
        help="Optional llama.cpp model name; encoded as #<model> on the target.",
    )
    parser.add_argument(
        "--model-target",
        action=_BaseModelConflictAction,
        default=None,
        help="Optional full Ergon model target. Overrides --base-url and --model.",
    )
    parser.add_argument(
        "--max-iterations",
        type=_positive_int,
        default=DEFAULT_MINIF2F_MAX_ITERATIONS,
        help="Maximum ReAct tool iterations per MiniF2F task.",
    )
    parser.add_argument(
        "--base-model",
        action=_BaseModelConflictAction,
        default=None,
        help=(
            "Local GGUF path or Hugging Face '<repo-id>:<filename.gguf>' ref; "
            "the example starts a managed llama.cpp server for this run."
        ),
    )
    parser.add_argument(
        "--model-cache-dir",
        default=None,
        help="Directory for downloaded Hugging Face GGUF files.",
    )
    parser.add_argument(
        "--llama-server-bin",
        default="llama-server",
        help="llama.cpp server command to run with --base-model.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for the managed llama.cpp server.",
    )
    parser.add_argument(
        "--port",
        type=_positive_int,
        default=8080,
        help="Port for the managed llama.cpp server.",
    )
    parser.add_argument(
        "--startup-timeout",
        type=_positive_int,
        default=60,
        help="Seconds to wait for a managed llama.cpp server to become ready.",
    )
    parser.add_argument(
        "--keep-llama-server",
        action="store_true",
        help="Leave the managed llama.cpp server running after the example exits.",
    )


class _BaseModelConflictAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[object] | None,
        option_string: str | None = None,
    ) -> None:
        if not isinstance(values, str):
            parser.error(f"{option_string} requires a single value")
        if self.dest == "base_model":
            conflicts = ("base_url", "model", "model_target")
            namespace_values = vars(namespace)
            for conflict in conflicts:
                if namespace_values.get(conflict) is not None:
                    parser.error(
                        f"--base-model cannot be combined with --{conflict.replace('_', '-')}"
                    )
        elif vars(namespace).get("base_model") is not None:
            parser.error(f"--base-model cannot be combined with {option_string}")
        setattr(namespace, self.dest, values)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"{value!r} is not a positive integer")
    return parsed
