from argparse import Namespace

from ergon_cli.domains.benchmarks.models import BenchmarkCommand
from ergon_cli.domains.benchmarks.service import list_benchmark_rows
from ergon_cli.domains.benchmarks.service import setup_benchmark as setup_benchmark_service
from ergon_cli.rendering import render_table


async def handle_benchmark(args: Namespace) -> int:
    if args.bench_action not in {"list", "setup"}:
        print("Usage: ergon benchmark {list|setup}")
        return 1
    values = vars(args)
    command = BenchmarkCommand(
        action=args.bench_action,
        slug=values.get("slug"),
        force=values.get("force", False),
    )
    if command.action == "list":
        render_table(["Slug", "Name", "Description"], list_benchmark_rows())
        return 0
    return setup_benchmark_service(command)
