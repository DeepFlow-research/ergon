"""Compatibility wrappers for benchmark CLI commands."""

from argparse import Namespace

from ergon_cli.domains.benchmarks.commands import handle_benchmark
from ergon_cli.domains.benchmarks.models import BenchmarkCommand
from ergon_cli.domains.benchmarks.service import setup_benchmark as setup_benchmark_service


def setup_benchmark(args: Namespace) -> int:
    return setup_benchmark_service(
        BenchmarkCommand(action="setup", slug=args.slug, force=args.force)
    )
