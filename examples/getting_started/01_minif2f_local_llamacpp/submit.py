"""Submit the MiniF2F getting-started example against local llama.cpp."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from uuid import UUID

from ergon_builtins.benchmarks.minif2f.sandbox import LeanSandbox
from ergon_builtins.benchmarks.minif2f.worker_factory import (
    make_minif2f_rubric,
    make_minif2f_worker,
)
from ergon_builtins.environments import MiniF2FEnvironment
from ergon_core.api import Experiment, RandomSampler
from ergon_core.api.worker import Worker
from ergon_core.core.application.experiments.submission import ExperimentSubmissionService
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from getting_started._shared.env import (
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
from getting_started._shared.llamacpp import ManagedLlamaServer, start_llama_server
from getting_started._shared.launch import print_submission_summary
from getting_started._shared.model_cache import resolve_base_model
from getting_started._shared.observe import cli_status_command, dashboard_sample_url


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the example."""
    parser = argparse.ArgumentParser(
        description="Submit three MiniF2F Lean proof samples with local llama.cpp and E2B."
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=env_positive_int("ERGON_MINIF2F_LIMIT", DEFAULT_MINIF2F_LIMIT),
        help="Number of MiniF2F samples to submit.",
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
        help="Maximum ReAct tool iterations per MiniF2F sample.",
    )
    parser.add_argument(
        "--base-model",
        default=None,
        help=(
            "Local GGUF path or Hugging Face '<repo-id>:<filename.gguf>' ref. "
            "Starts a managed llama.cpp server for this sample."
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
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable submission output.",
    )
    args = parser.parse_args(argv)
    _validate_model_routing(args, parser)
    return args


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


def experiment_submission_service() -> ExperimentSubmissionService:
    """Create the concrete service behind this Python composition example."""
    ensure_db()
    return ExperimentSubmissionService.for_session(get_session())


async def async_main(argv: Sequence[str] | None = None) -> int:
    """Run the example and return a process exit code."""
    server: ManagedLlamaServer | None = None
    keep_llama_server = False
    try:
        args = parse_args(argv)
        keep_llama_server = args.keep_llama_server
        if args.base_model is not None:
            print(f"Resolving base model: {args.base_model}")
            base_model_path = resolve_base_model(
                args.base_model,
                cache_dir=args.model_cache_dir,
            )
            print(f"Using base model: {base_model_path}")
            print(f"Starting llama.cpp on {args.host}:{args.port}")
            server = start_llama_server(
                base_model=str(base_model_path),
                llama_server_bin=args.llama_server_bin,
                host=args.host,
                port=args.port,
                startup_timeout=args.startup_timeout,
            )
            args.base_url = server.base_url
            args.model = server.discovered_model

        model_target = model_target_from_args(args)
        preflight_llamacpp_and_e2b(base_url=preflight_base_url_from_args(args))
    except ExampleSetupError as exc:
        if server is not None:
            server.close(keep_running=keep_llama_server)
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2

    def make_worker() -> Worker:
        return make_minif2f_worker(
            model=model_target,
            max_iterations=args.max_iterations,
        )

    try:
        env = MiniF2FEnvironment(
            name="mini-validation",
            split="validation",
            limit=args.limit,
            worker=make_worker(),
            evaluators=[make_minif2f_rubric()],
            sandbox=LeanSandbox(),
        )
        experiment = Experiment(name="minif2f-local-llamacpp", environments=[env])
        result = await experiment.submit(
            service=experiment_submission_service(),
            k=args.limit,
            sampler=RandomSampler(seed=0),
        )
        _print_submission_summary(
            experiment_id=result.experiment_id,
            sampler_invocation_id=result.sampler_invocation_id,
            batch_id=result.batch_id,
            sample_ids=result.sample_ids,
            model_target=model_target,
            limit=args.limit,
            max_iterations=args.max_iterations,
            as_json=args.json,
        )
        return 0
    finally:
        if server is not None:
            server.close(keep_running=keep_llama_server)


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


def _validate_model_routing(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.base_model is None:
        return
    conflicts = {
        "--model": args.model is not None,
        "--model-target": args.model_target is not None,
    }
    for flag, is_set in conflicts.items():
        if is_set:
            parser.error(f"--base-model cannot be combined with {flag}")


def _print_submission_summary(
    *,
    experiment_id: UUID,
    sampler_invocation_id: UUID | None,
    batch_id: UUID | None,
    sample_ids: Sequence[UUID],
    model_target: str,
    limit: int,
    max_iterations: int,
    as_json: bool,
) -> None:
    if as_json:
        print_submission_summary(
            experiment_id=experiment_id,
            sampler_invocation_id=sampler_invocation_id,
            batch_id=batch_id,
            sample_ids=sample_ids,
            as_json=True,
        )
        return

    print("MiniF2F llama.cpp samples submitted")
    print_submission_summary(
        experiment_id=experiment_id,
        sampler_invocation_id=sampler_invocation_id,
        batch_id=batch_id,
        sample_ids=sample_ids,
        as_json=False,
    )
    print(f"Model target: {model_target}")
    print(f"Limit: {limit}")
    print(f"Max iterations: {max_iterations}")
    if sample_ids:
        first_sample_id = sample_ids[0]
        print(f"CLI status: {cli_status_command(first_sample_id)}")
        url = dashboard_sample_url(first_sample_id)
        if url:
            print(f"Dashboard: {url}")


if __name__ == "__main__":
    raise SystemExit(main())
