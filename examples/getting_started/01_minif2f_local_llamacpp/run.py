"""Launch the MiniF2F getting-started example against local llama.cpp."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ergon_core.api import Worker, persist_benchmark
from ergon_core.core.application.experiments.service import launch_run

from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from ergon_builtins.benchmarks.minif2f.worker_factory import make_minif2f_worker

from examples.getting_started._shared.env import (
    DEFAULT_LLAMA_CPP_BASE_URL,
    DEFAULT_MINIF2F_LIMIT,
    DEFAULT_MINIF2F_MAX_ITERATIONS,
    ExampleSetupError,
    base_url_from_model_target,
    build_llamacpp_model_target,
    env_optional_str,
    env_positive_int,
    env_str,
    preflight_llamacpp_and_e2b,
)
from examples.getting_started._shared.launch import first_run_id
from examples.getting_started._shared.observe import cli_status_command, dashboard_run_url


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the example."""
    parser = argparse.ArgumentParser(
        description="Run three MiniF2F Lean proof tasks with local llama.cpp and E2B."
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=env_positive_int("ERGON_MINIF2F_LIMIT", DEFAULT_MINIF2F_LIMIT),
        help="Number of MiniF2F tasks to launch.",
    )
    parser.add_argument(
        "--base-url",
        default=env_str("ERGON_LLAMA_CPP_BASE_URL", DEFAULT_LLAMA_CPP_BASE_URL),
        help="Base URL for the llama.cpp OpenAI-compatible server.",
    )
    parser.add_argument(
        "--model",
        default=env_optional_str("ERGON_LLAMA_CPP_MODEL"),
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
        default=env_positive_int(
            "ERGON_MINIF2F_MAX_ITERATIONS",
            DEFAULT_MINIF2F_MAX_ITERATIONS,
        ),
        help="Maximum ReAct tool iterations per MiniF2F task.",
    )
    return parser.parse_args(argv)


def model_target_from_args(args: argparse.Namespace) -> str:
    """Build the worker model target from parsed CLI args."""
    return build_llamacpp_model_target(
        base_url=args.base_url,
        model_name=args.model,
        model_target=args.model_target,
    )


def preflight_base_url_from_args(args: argparse.Namespace) -> str:
    """Choose the llama.cpp-compatible endpoint to check before launch."""
    if args.model_target is None:
        return args.base_url
    base_url = base_url_from_model_target(args.model_target)
    if base_url is None:
        raise ExampleSetupError(
            "--model-target must include an http(s) endpoint for this local llama.cpp example."
        )
    return base_url


async def async_main(argv: Sequence[str] | None = None) -> int:
    """Run the example and return a process exit code."""
    try:
        args = parse_args(argv)
        model_target = model_target_from_args(args)
        preflight_llamacpp_and_e2b(base_url=preflight_base_url_from_args(args))
    except ExampleSetupError as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2

    def make_worker() -> Worker:
        return make_minif2f_worker(
            model=model_target,
            max_iterations=args.max_iterations,
        )

    benchmark = MiniF2FBenchmark(limit=args.limit, worker_factory=make_worker)
    handle = persist_benchmark(benchmark)
    run_result = await launch_run(handle.definition_id)
    run_id = first_run_id(run_result)
    _print_launch_summary(
        definition_id=handle.definition_id,
        run_id=run_id,
        model_target=model_target,
        limit=args.limit,
        max_iterations=args.max_iterations,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Synchronous entrypoint for direct script execution."""
    return asyncio.run(async_main(argv))


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"{value!r} is not a positive integer")
    return parsed


def _print_launch_summary(
    *,
    definition_id: object,
    run_id: UUID,
    model_target: str,
    limit: int,
    max_iterations: int,
) -> None:
    print("MiniF2F llama.cpp run launched")
    print(f"Definition id: {definition_id}")
    print(f"Run id: {run_id}")
    print(f"Model target: {model_target}")
    print(f"Limit: {limit}")
    print(f"Max iterations: {max_iterations}")
    print(f"CLI status: {cli_status_command(run_id)}")
    url = dashboard_run_url(run_id)
    if url:
        print(f"Dashboard: {url}")


if __name__ == "__main__":
    raise SystemExit(main())
