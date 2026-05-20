import argparse

from ergon_cli.domains.benchmarks.commands import handle_benchmark


def register_benchmark_parser(subparsers: argparse._SubParsersAction) -> None:
    bench = subparsers.add_parser("benchmark", help="Benchmark operations")
    bench.set_defaults(handler=handle_benchmark)
    bench_sub = bench.add_subparsers(dest="bench_action")
    bench_sub.add_parser("list", help="List available benchmarks")
    setup_parser = bench_sub.add_parser(
        "setup", help="Build and register the E2B sandbox template for a benchmark"
    )
    setup_parser.add_argument("slug", help="Benchmark slug (e.g., 'minif2f')")
    setup_parser.add_argument(
        "--force", action="store_true", help="Rebuild even if the template already exists"
    )
