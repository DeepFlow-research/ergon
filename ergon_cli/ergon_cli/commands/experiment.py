"""Experiment lifecycle commands."""

from argparse import Namespace
from dataclasses import dataclass
import logging
from uuid import UUID

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.views.experiments.service import ExperimentReadService
from sqlmodel import select

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
    detail = ExperimentReadService().get_experiment(UUID(args.definition_id))
    if detail is None:
        logger.error("Experiment not found: %s", args.definition_id)
        return 1

    experiment = detail.experiment
    logger.info("DEFINITION_ID=%s", experiment.definition_id)
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

    logger.info("DEFINITION_ID\tNAME\tBENCHMARK\tSTATUS\tSAMPLES\tRUNS\tMODEL")
    for experiment in experiments:
        logger.info(
            "%s\t%s\t%s\t%s\t%s\t%s\t%s",
            experiment.definition_id,
            experiment.name,
            experiment.benchmark_type,
            experiment.status,
            experiment.sample_count,
            experiment.run_count,
            "" if experiment.default_model_target is None else experiment.default_model_target,
        )
    return 0


@dataclass(frozen=True)
class ExperimentTagDefinitionRow:
    definition_id: UUID
    name: str
    benchmark_type: str
    latest_run_status: str | None = None


class ExperimentTagService:
    """Read v2 experiment grouping tags from ``RunRecord.experiment``."""

    def distinct_tags(self) -> list[str]:
        ensure_db()
        with get_session() as session:
            tags = {
                tag
                for tag in session.exec(select(RunRecord.experiment)).all()
                if isinstance(tag, str) and tag
            }
        return sorted(tags)

    def definitions_by_tag(self, tag: str) -> list[ExperimentTagDefinitionRow]:
        ensure_db()
        with get_session() as session:
            runs = list(
                session.exec(
                    select(RunRecord)
                    .where(RunRecord.experiment == tag)
                    .order_by(RunRecord.created_at.desc())
                ).all()
            )
            latest_by_definition: dict[UUID, RunRecord] = {}
            for run in runs:
                latest_by_definition.setdefault(run.definition_id, run)

            rows: list[ExperimentTagDefinitionRow] = []
            for definition_id, latest_run in latest_by_definition.items():
                definition = session.get(ExperimentDefinition, definition_id)
                if definition is None:
                    continue
                rows.append(
                    ExperimentTagDefinitionRow(
                        definition_id=definition.id,
                        name=definition.name,
                        benchmark_type=definition.benchmark_type,
                        latest_run_status=str(latest_run.status),
                    )
                )
        return rows


def handle_experiment_tags(args: Namespace) -> int:
    _ensure_cli_logging()
    tags = ExperimentTagService().distinct_tags()
    if not tags:
        logger.info("No experiment tags found.")
        return 0
    for tag in tags:
        logger.info("%s", tag)
    return 0


def handle_experiment_by_tag(args: Namespace) -> int:
    _ensure_cli_logging()
    rows = ExperimentTagService().definitions_by_tag(args.tag)
    if not rows:
        logger.info("No definitions found for experiment tag %r.", args.tag)
        return 0

    logger.info("DEFINITION_ID\tNAME\tBENCHMARK\tLATEST_RUN_STATUS")
    for row in rows:
        logger.info(
            "%s\t%s\t%s\t%s",
            row.definition_id,
            row.name,
            row.benchmark_type,
            "" if row.latest_run_status is None else row.latest_run_status,
        )
    return 0


def _ensure_cli_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
