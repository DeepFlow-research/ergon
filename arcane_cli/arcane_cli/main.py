"""Arcane CLI entry point."""

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arcane", description="Arcane experiment orchestration"
    )
    sub = parser.add_subparsers(dest="command")

    bench = sub.add_parser("benchmark", help="Benchmark operations")
    bench_sub = bench.add_subparsers(dest="bench_action")
    bench_sub.add_parser("list", help="List available benchmarks")
    run_parser = bench_sub.add_parser("run", help="Run a benchmark")
    run_parser.add_argument("slug", help="Benchmark slug")
    run_parser.add_argument(
        "--model", default="openai:gpt-4o", help="Model to use"
    )
    run_parser.add_argument(
        "--worker", default="stub-worker", help="Worker slug"
    )
    run_parser.add_argument(
        "--evaluator", default="stub-rubric", help="Evaluator slug"
    )
    run_parser.add_argument(
        "--workflow", default="single", help="Workflow variant"
    )
    run_parser.add_argument(
        "--limit", type=int, default=None,
        help="Number of samples/tasks to run (benchmark-specific)",
    )
    run_parser.add_argument(
        "--timeout", type=int, default=600,
        help="Timeout in seconds per run",
    )
    run_parser.add_argument(
        "--max-questions", type=int, default=10,
        help="Max questions workers can ask",
    )

    run = sub.add_parser("run", help="Run management")
    run_sub = run.add_subparsers(dest="run_action")
    run_list_parser = run_sub.add_parser("list", help="List recent runs")
    run_list_parser.add_argument(
        "--limit", type=int, default=20, help="Number of runs to show"
    )
    run_list_parser.add_argument(
        "--status", default=None,
        help="Filter by status (pending, executing, completed, failed, cancelled)",
    )
    run_cancel_parser = run_sub.add_parser("cancel", help="Cancel a running experiment")
    run_cancel_parser.add_argument("run_id", help="Run ID (UUID) to cancel")

    worker = sub.add_parser("worker", help="Worker operations")
    worker_sub = worker.add_subparsers(dest="worker_action")
    worker_sub.add_parser("list", help="List available workers")

    evaluator = sub.add_parser("evaluator", help="Evaluator operations")
    eval_sub = evaluator.add_subparsers(dest="eval_action")
    eval_sub.add_parser("list", help="List available evaluators")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "benchmark":
        from arcane_cli.commands.benchmark import handle_benchmark

        return handle_benchmark(args)
    elif args.command == "run":
        from arcane_cli.commands.run import handle_run

        return handle_run(args)
    elif args.command == "worker":
        from arcane_cli.commands.worker import handle_worker

        return handle_worker(args)
    elif args.command == "evaluator":
        from arcane_cli.commands.evaluator import handle_evaluator

        return handle_evaluator(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
