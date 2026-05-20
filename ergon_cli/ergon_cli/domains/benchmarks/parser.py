import argparse

from ergon_cli.domains.benchmarks.commands import handle_benchmark


def register_benchmark_parser(subparsers: argparse._SubParsersAction) -> None:
    bench = subparsers.add_parser("benchmark", help="Benchmark operations")
    bench.set_defaults(handler=handle_benchmark)
    bench_sub = bench.add_subparsers(dest="bench_action")
    bench_sub.add_parser("list", help="List available benchmarks")
