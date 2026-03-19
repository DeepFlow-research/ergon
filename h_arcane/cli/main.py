"""`magym` CLI for local setup and benchmark workflows."""

from __future__ import annotations

import argparse
import sys

from h_arcane.services.setup.benchmark_preparation_service import BenchmarkPreparationService
from h_arcane.services.setup.benchmark_seed_service import BenchmarkSeedService
from h_arcane.services.setup.common import DEFAULT_RESEARCHRUBRICS_DATASET, SUPPORTED_BENCHMARKS
from h_arcane.services.setup.compose_service import ComposeService
from h_arcane.services.setup.readiness_service import ReadinessService


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""
    parser = argparse.ArgumentParser(prog="magym")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Interactive local setup flow")
    _add_shared_benchmark_args(init_parser)
    init_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
    init_parser.add_argument("--seed", action="store_true", help="Seed selected benchmarks")
    init_parser.add_argument(
        "--skip-compose",
        action="store_true",
        help="Do not start docker compose services during init",
    )

    doctor_parser = subparsers.add_parser("doctor", help="Show readiness information")
    doctor_parser.add_argument(
        "--researchrubrics-dataset-name",
        default=DEFAULT_RESEARCHRUBRICS_DATASET,
        help="Hugging Face dataset to validate for ResearchRubrics",
    )

    compose_parser = subparsers.add_parser("compose", help="Common docker compose actions")
    compose_subparsers = compose_parser.add_subparsers(dest="compose_command", required=True)
    compose_up = compose_subparsers.add_parser("up", help="Start docker compose services")
    compose_up.add_argument("services", nargs="*", help="Optional service names")
    compose_subparsers.add_parser("down", help="Stop docker compose services")
    compose_logs = compose_subparsers.add_parser("logs", help="Show docker compose logs")
    compose_logs.add_argument("services", nargs="*", help="Optional service names")
    compose_logs.add_argument("--tail", type=int, default=100, help="Number of log lines")

    benchmark_parser = subparsers.add_parser("benchmark", help="Benchmark workflows")
    benchmark_subparsers = benchmark_parser.add_subparsers(
        dest="benchmark_command",
        required=True,
    )
    benchmark_subparsers.add_parser("list", help="List supported benchmarks")

    benchmark_status = benchmark_subparsers.add_parser("status", help="Show benchmark readiness")
    benchmark_status.add_argument("benchmarks", nargs="*", choices=SUPPORTED_BENCHMARKS)
    benchmark_status.add_argument(
        "--researchrubrics-dataset-name",
        default=DEFAULT_RESEARCHRUBRICS_DATASET,
        help="Hugging Face dataset to validate for ResearchRubrics",
    )

    benchmark_prepare = benchmark_subparsers.add_parser("prepare", help="Prepare benchmark assets")
    benchmark_prepare.add_argument("benchmarks", nargs="+", choices=SUPPORTED_BENCHMARKS)
    benchmark_prepare.add_argument(
        "--researchrubrics-dataset-name",
        default=DEFAULT_RESEARCHRUBRICS_DATASET,
        help="Hugging Face dataset to cache for ResearchRubrics",
    )

    benchmark_seed = benchmark_subparsers.add_parser("seed", help="Seed benchmarks into Postgres")
    benchmark_seed.add_argument("benchmarks", nargs="+", choices=SUPPORTED_BENCHMARKS)
    benchmark_seed.add_argument("--limit", type=int, default=None, help="Maximum tasks to seed")
    benchmark_seed.add_argument(
        "--database",
        choices=("main", "test"),
        default="main",
        help="Database target to seed",
    )
    benchmark_seed.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="Worker model persisted on seeded runs",
    )
    benchmark_seed.add_argument(
        "--researchrubrics-dataset-name",
        default=DEFAULT_RESEARCHRUBRICS_DATASET,
        help="Hugging Face dataset to seed for ResearchRubrics",
    )

    return parser


def _add_shared_benchmark_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--benchmarks",
        nargs="*",
        choices=SUPPORTED_BENCHMARKS,
        help="Benchmarks to prepare during init",
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum tasks to seed")
    parser.add_argument(
        "--database",
        choices=("main", "test"),
        default="main",
        help="Database target to seed",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="Worker model persisted on seeded runs",
    )
    parser.add_argument(
        "--researchrubrics-dataset-name",
        default=DEFAULT_RESEARCHRUBRICS_DATASET,
        help="Hugging Face dataset to use for ResearchRubrics",
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    match args.command:
        case "doctor":
            return _handle_doctor(args)
        case "compose":
            return _handle_compose(args)
        case "benchmark":
            return _handle_benchmark(args)
        case "init":
            return _handle_init(args)
        case _:
            parser.error(f"Unknown command: {args.command}")
            return 2


def _handle_doctor(args: argparse.Namespace) -> int:
    report = ReadinessService().build_report(args.researchrubrics_dataset_name)

    print("Environment:")
    for env_check in report.env_checks:
        status = "present" if env_check.present else "missing"
        print(f"- {env_check.name}: {status} ({env_check.source})")

    print("\nServices:")
    for service_check in report.service_checks:
        print(f"- {service_check.name}: {service_check.detail}")

    print("\nDatabases:")
    for database_check in report.database_checks:
        print(f"- {database_check.name}: {database_check.detail}")

    print("\nBenchmarks:")
    for benchmark_check in report.benchmark_checks:
        print(f"- {benchmark_check.benchmark}: {benchmark_check.detail}")

    return 0


def _handle_compose(args: argparse.Namespace) -> int:
    compose = ComposeService()

    if args.compose_command == "up":
        result = compose.up(args.services)
    elif args.compose_command == "down":
        result = compose.down()
    elif args.compose_command == "logs":
        result = compose.logs(args.services, tail=args.tail)
    else:
        raise ValueError(f"Unknown compose command: {args.compose_command}")

    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def _handle_benchmark(args: argparse.Namespace) -> int:
    preparation_service = BenchmarkPreparationService()
    seed_service = BenchmarkSeedService()

    if args.benchmark_command == "list":
        for benchmark in preparation_service.supported_benchmarks():
            print(benchmark)
        return 0

    if args.benchmark_command == "status":
        benchmarks = args.benchmarks or list(preparation_service.supported_benchmarks())
        for benchmark in benchmarks:
            status = preparation_service.status(
                benchmark,
                researchrubrics_dataset_name=args.researchrubrics_dataset_name,
            )
            print(f"{status.benchmark}: {status.detail}")
        return 0

    if args.benchmark_command == "prepare":
        for benchmark in args.benchmarks:
            prepare_result = preparation_service.prepare(
                benchmark,
                researchrubrics_dataset_name=args.researchrubrics_dataset_name,
            )
            print(f"{prepare_result.benchmark}: {prepare_result.detail}")
        return 0

    if args.benchmark_command == "seed":
        for benchmark in args.benchmarks:
            seed_result = seed_service.seed(
                benchmark,
                limit=args.limit,
                database_target=args.database,
                model=args.model,
                researchrubrics_dataset_name=args.researchrubrics_dataset_name,
            )
            print(
                f"{seed_result.benchmark}: {seed_result.detail} "
                f"({seed_result.database_target} database)"
            )
        return 0

    raise ValueError(f"Unknown benchmark command: {args.benchmark_command}")


def _handle_init(args: argparse.Namespace) -> int:
    compose = ComposeService()
    preparation_service = BenchmarkPreparationService()
    seed_service = BenchmarkSeedService()

    if not args.skip_compose:
        if args.yes or _confirm("Start docker compose services? [Y/n] ", default=True):
            compose_result = compose.up()
            if compose_result.stdout.strip():
                print(compose_result.stdout.strip())
            if compose_result.stderr.strip():
                print(compose_result.stderr.strip(), file=sys.stderr)
            if compose_result.returncode != 0:
                return compose_result.returncode

    print("\nReadiness report:")
    _handle_doctor(
        argparse.Namespace(researchrubrics_dataset_name=args.researchrubrics_dataset_name)
    )

    benchmarks = args.benchmarks or list(preparation_service.supported_benchmarks())
    if not args.yes and args.benchmarks is None:
        benchmarks = _prompt_for_benchmarks()

    for benchmark in benchmarks:
        prepare_result = preparation_service.prepare(
            benchmark,
            researchrubrics_dataset_name=args.researchrubrics_dataset_name,
        )
        print(f"{prepare_result.benchmark}: {prepare_result.detail}")

    if args.seed or (not args.yes and _confirm("\nSeed prepared benchmarks now? [y/N] ", default=False)):
        for benchmark in benchmarks:
            seed_result = seed_service.seed(
                benchmark,
                limit=args.limit,
                database_target=args.database,
                model=args.model,
                researchrubrics_dataset_name=args.researchrubrics_dataset_name,
            )
            print(
                f"{seed_result.benchmark}: {seed_result.detail} "
                f"({seed_result.database_target} database)"
            )

    return 0


def _confirm(prompt: str, default: bool) -> bool:
    reply = input(prompt).strip().lower()
    if not reply:
        return default
    return reply in {"y", "yes"}


def _prompt_for_benchmarks() -> list[str]:
    print("\nSelect benchmarks to prepare:")
    print("1. minif2f")
    print("2. researchrubrics")
    reply = input("Enter comma-separated numbers [1,2]: ").strip()
    if not reply:
        return list(SUPPORTED_BENCHMARKS)

    selected: list[str] = []
    for item in [part.strip() for part in reply.split(",")]:
        if item == "1":
            selected.append("minif2f")
        elif item == "2":
            selected.append("researchrubrics")
    return selected or list(SUPPORTED_BENCHMARKS)


if __name__ == "__main__":
    raise SystemExit(main())
