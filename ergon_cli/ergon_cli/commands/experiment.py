"""Experiment lifecycle commands."""

from argparse import Namespace
import logging
from uuid import UUID

from ergon_core.core.persistence.shared.db import ensure_db
from ergon_core.core.runtime.services.cohort_service import experiment_cohort_service
from ergon_core.core.runtime.services.experiment_definition_service import (
    ExperimentDefinitionService,
)
from ergon_core.core.runtime.services.experiment_launch_service import ExperimentLaunchService
from ergon_core.core.runtime.services.experiment_read_service import ExperimentReadService
from ergon_core.core.runtime.services.experiment_schemas import (
    ExperimentDefineRequest,
    ExperimentRunRequest,
)

logger = logging.getLogger(__name__)


async def handle_experiment(args: Namespace) -> int:
    _ensure_cli_logging()
    if args.experiment_action == "define":
        return handle_experiment_define(args)
    if args.experiment_action == "run":
        return await handle_experiment_run(args)
    if args.experiment_action == "show":
        return handle_experiment_show(args)
    if args.experiment_action == "list":
        return handle_experiment_list(args)
    logger.error("Usage: ergon experiment {define|run|show|list}")
    return 1


def handle_experiment_define(args: Namespace) -> int:
    _ensure_cli_logging()
    ensure_db()
    cohort_id = None
    if args.cohort:
        cohort = experiment_cohort_service.resolve_or_create(
            name=args.cohort,
            description=f"CLI experiment folder for {args.benchmark_slug}",
            created_by="ergon-cli",
        )
        cohort_id = cohort.id

    sample_ids = args.sample_id or None
    request = ExperimentDefineRequest(
        benchmark_slug=args.benchmark_slug,
        name=args.name,
        cohort_id=cohort_id,
        limit=args.limit,
        sample_ids=sample_ids,
        default_model_target=args.model,
        default_worker_team={"primary": args.worker},
        default_evaluator_slug=args.evaluator,
        metadata={"workflow": args.workflow, "max_questions": args.max_questions},
    )
    result = ExperimentDefinitionService().define_benchmark_experiment(request)
    logger.info("EXPERIMENT_ID=%s", result.experiment_id)
    if result.cohort_id is not None:
        logger.info("COHORT_ID=%s", result.cohort_id)
    logger.info("BENCHMARK=%s", result.benchmark_type)
    logger.info("SAMPLES=%s", ",".join(result.selected_samples))
    return 0


async def handle_experiment_run(args: Namespace) -> int:
    _ensure_cli_logging()
    ensure_db()
    result = await ExperimentLaunchService().run_experiment(
        ExperimentRunRequest(
            experiment_id=UUID(args.experiment_id),
            timeout_seconds=args.timeout,
            wait=not args.no_wait,
        )
    )
    logger.info("EXPERIMENT_ID=%s", result.experiment_id)
    for run_id in result.run_ids:
        logger.info("RUN_ID=%s", run_id)
    return 0


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


def _ensure_cli_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
