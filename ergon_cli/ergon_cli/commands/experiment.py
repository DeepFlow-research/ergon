"""Experiment lifecycle commands."""

from argparse import Namespace
from uuid import UUID

from ergon_core.core.persistence.shared.db import ensure_db
from ergon_core.core.runtime.services.cohort_service import experiment_cohort_service
from ergon_core.core.runtime.services.experiment_definition_service import (
    ExperimentDefinitionService,
)
from ergon_core.core.runtime.services.experiment_launch_service import ExperimentLaunchService
from ergon_core.core.runtime.services.experiment_schemas import (
    ExperimentDefineRequest,
    ExperimentRunRequest,
)


async def handle_experiment(args: Namespace) -> int:
    if args.experiment_action == "define":
        return handle_experiment_define(args)
    if args.experiment_action == "run":
        return await handle_experiment_run(args)
    if args.experiment_action == "show":
        return handle_experiment_show(args)
    if args.experiment_action == "list":
        return handle_experiment_list(args)
    print("Usage: ergon experiment {define|run|show|list}")
    return 1


def handle_experiment_define(args: Namespace) -> int:
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
    print(f"EXPERIMENT_ID={result.experiment_id}")
    if result.cohort_id is not None:
        print(f"COHORT_ID={result.cohort_id}")
    print(f"BENCHMARK={result.benchmark_type}")
    print(f"SAMPLES={','.join(result.selected_samples)}")
    return 0


async def handle_experiment_run(args: Namespace) -> int:
    ensure_db()
    result = await ExperimentLaunchService().run_experiment(
        ExperimentRunRequest(
            experiment_id=UUID(args.experiment_id),
            timeout_seconds=args.timeout,
            wait=not args.no_wait,
        )
    )
    print(f"EXPERIMENT_ID={result.experiment_id}")
    for run_id in result.run_ids:
        print(f"RUN_ID={run_id}")
    return 0


def handle_experiment_show(args: Namespace) -> int:
    print("Experiment show is not yet implemented.")
    return 1


def handle_experiment_list(args: Namespace) -> int:
    print("Experiment list is not yet implemented.")
    return 1
