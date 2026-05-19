"""CLI composition root."""

import argparse
import inspect

from ergon_cli.domains.benchmarks.parser import register_benchmark_parser
from ergon_cli.domains.doctor.parser import register_doctor_parser
from ergon_cli.domains.eval.parser import register_eval_parser
from ergon_cli.domains.evaluators.parser import register_evaluator_parser
from ergon_cli.domains.experiments.parser import register_experiment_parser
from ergon_cli.domains.ingestion.parser import register_ingest_parser
from ergon_cli.domains.onboarding.parser import register_onboard_parser
from ergon_cli.domains.runs.parser import register_run_parser
from ergon_cli.domains.stack.parser import register_stack_parser
from ergon_cli.domains.training.parser import register_train_parser
from ergon_cli.domains.workers.parser import register_worker_parser
from ergon_cli.domains.workflow.parser import register_workflow_parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ergon", description="Ergon experiment orchestration")
    subparsers = parser.add_subparsers(dest="command")

    register_benchmark_parser(subparsers)
    register_experiment_parser(subparsers)
    register_run_parser(subparsers)
    register_ingest_parser(subparsers)
    register_worker_parser(subparsers)
    register_workflow_parser(subparsers)
    register_evaluator_parser(subparsers)
    register_eval_parser(subparsers)
    register_onboard_parser(subparsers)
    register_doctor_parser(subparsers)
    register_stack_parser(subparsers)
    register_train_parser(subparsers)

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
