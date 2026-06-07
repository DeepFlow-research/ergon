"""CLI composition root."""

import argparse
import inspect

from ergon_cli.domains.benchmarks.parser import register_benchmark_parser
from ergon_cli.domains.doctor.parser import register_doctor_parser
from ergon_cli.domains.evaluators.parser import register_evaluator_parser
from ergon_cli.domains.examples.parser import register_examples_parser
from ergon_cli.domains.experiments.parser import register_experiment_parser
from ergon_cli.domains.ingestion.parser import register_ingest_parser
from ergon_cli.domains.onboarding.parser import register_onboard_parser
from ergon_cli.domains.samples.parser import register_sample_parser
from ergon_cli.domains.stack.parser import register_stack_parser
from ergon_cli.domains.tests.parser import register_test_parser
from ergon_cli.domains.workers.parser import register_worker_parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ergon", description="Ergon experiment orchestration")
    subparsers = parser.add_subparsers(dest="command")

    register_benchmark_parser(subparsers)
    register_experiment_parser(subparsers)
    register_sample_parser(subparsers)
    register_ingest_parser(subparsers)
    register_worker_parser(subparsers)
    register_evaluator_parser(subparsers)
    register_examples_parser(subparsers)
    register_onboard_parser(subparsers)
    register_doctor_parser(subparsers)
    register_stack_parser(subparsers)
    register_test_parser(subparsers)

    return parser


async def dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    handler = vars(args).get("handler")
    if handler is None:
        parser.print_help()
        return 0
    result = handler(args)
    if inspect.isawaitable(result):
        return await result
    return result
