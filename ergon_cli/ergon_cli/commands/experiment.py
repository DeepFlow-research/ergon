"""Experiment lifecycle commands."""

from argparse import Namespace
import logging
from uuid import UUID

from ergon_core.core.application.read_models.experiments import ExperimentReadService
from ergon_core.core.application.workflows.runs import latest_run_for_definition
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord
from sqlmodel import col, select

logger = logging.getLogger(__name__)


async def handle_experiment(args: Namespace) -> int:
    _ensure_cli_logging()
    if args.experiment_action == "show":
        return handle_experiment_show(args)
    if args.experiment_action == "list":
        return handle_experiment_list(args)
    if args.experiment_action == "tags":
        return handle_experiment_tags(args)
    if args.experiment_action == "by-tag":
        return handle_experiment_by_tag(args)
    logger.error("Usage: ergon experiment {show|list|tags|by-tag}")
    return 1


def handle_experiment_show(args: Namespace) -> int:
    _ensure_cli_logging()
    detail = ExperimentReadService().get_experiment(UUID(args.experiment_id))
    if detail is None:
        logger.error("Experiment not found: %s", args.experiment_id)
        return 1

    experiment = detail.experiment
    logger.info("EXPERIMENT_ID=%s", experiment.experiment_id)
    if experiment.cohort_id is not None:
        logger.info("COHORT_ID=%s", experiment.cohort_id)
    logger.info("NAME=%s", experiment.name)
    logger.info("BENCHMARK=%s", experiment.benchmark_type)
    logger.info("STATUS=%s", experiment.status)
    logger.info("SAMPLE_COUNT=%s", experiment.sample_count)
    logger.info("RUN_COUNT=%s", experiment.run_count)
    if experiment.default_model_target is not None:
        logger.info("DEFAULT_MODEL=%s", experiment.default_model_target)
    if experiment.default_evaluator_slug is not None:
        logger.info("DEFAULT_EVALUATOR=%s", experiment.default_evaluator_slug)

    if detail.sample_selection:
        logger.info("SAMPLE_SELECTION=%s", detail.sample_selection)
    if detail.runs:
        logger.info("RUNS")
        for run in detail.runs:
            logger.info(
                "%s\t%s\t%s\t%s",
                run.run_id,
                run.instance_key,
                run.status,
                "" if run.model_target is None else run.model_target,
            )
    return 0


def handle_experiment_list(args: Namespace) -> int:
    _ensure_cli_logging()
    experiments = ExperimentReadService().list_experiments(limit=args.limit)
    if not experiments:
        logger.info("No experiments found.")
        return 0

    logger.info("EXPERIMENT_ID\tNAME\tBENCHMARK\tSTATUS\tSAMPLES\tRUNS\tMODEL")
    for experiment in experiments:
        logger.info(
            "%s\t%s\t%s\t%s\t%s\t%s\t%s",
            experiment.experiment_id,
            experiment.name,
            experiment.benchmark_type,
            experiment.status,
            experiment.sample_count,
            experiment.run_count,
            "" if experiment.default_model_target is None else experiment.default_model_target,
        )
    return 0


def handle_experiment_tags(args: Namespace) -> int:
    _ensure_cli_logging()
    with get_session() as session:
        tags = list(
            session.exec(
                select(BenchmarkDefinitionRecord.experiment)
                .where(BenchmarkDefinitionRecord.experiment.is_not(None))
                .distinct()
                .order_by(col(BenchmarkDefinitionRecord.experiment).asc())
            ).all()
        )
    if not tags:
        logger.info(
            "No experiment tags yet.  Tag definitions by setting "
            "`experiment` on the underlying record (cohort harness)."
        )
        return 0
    for tag in tags:
        logger.info("%s", tag)
    return 0


def handle_experiment_by_tag(args: Namespace) -> int:
    _ensure_cli_logging()
    with get_session() as session:
        records = list(
            session.exec(
                select(BenchmarkDefinitionRecord)
                .where(BenchmarkDefinitionRecord.experiment == args.tag)
                .order_by(col(BenchmarkDefinitionRecord.created_at).desc())
            ).all()
        )
    if not records:
        logger.info("No definitions tagged with experiment=%r", args.tag)
        return 0
    logger.info("DEFINITION_ID\tNAME\tBENCHMARK\tSTATUS\tLATEST_RUN_STATUS")
    for record in records:
        latest = latest_run_for_definition(record.id)
        latest_status = latest.status if latest else "no runs"
        logger.info(
            "%s\t%s\t%s\t%s\t%s",
            record.id,
            record.name,
            record.benchmark_type,
            record.status,
            latest_status,
        )
    return 0


def _ensure_cli_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
