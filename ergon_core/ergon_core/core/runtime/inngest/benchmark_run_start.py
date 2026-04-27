"""Inngest function triggered by benchmark/run-request from CLI.

Reconstructs the full Experiment object graph server-side, persists it,
creates a RunRecord, and emits workflow/started to kick off execution.
"""

import logging
from typing import ClassVar

import inngest
from ergon_builtins.registry import BENCHMARKS, EVALUATORS, WORKERS
from ergon_core.core.runtime.errors import RegistryLookupError
from ergon_core.core.runtime.events.base import InngestEventContract
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.cohort_service import experiment_cohort_service
from ergon_core.core.runtime.services.experiment_definition_service import (
    ExperimentDefinitionService,
)
from ergon_core.core.runtime.services.experiment_launch_service import ExperimentLaunchService
from ergon_core.core.runtime.services.experiment_schemas import (
    ExperimentDefineRequest,
    ExperimentRunRequest,
)
from ergon_core.core.runtime.services.inngest_function_results import (
    BenchmarkRunStartResult,
)

logger = logging.getLogger(__name__)


class BenchmarkRunRequest(InngestEventContract):
    """CLI sends this to request a full benchmark run."""

    name: ClassVar[str] = "benchmark/run-request"

    benchmark_slug: str
    model: str
    worker_slug: str
    evaluator_slug: str
    cohort_name: str = ""  # slopcop: ignore[no-str-empty-default]


@inngest_client.create_function(
    fn_id="benchmark-run-start",
    trigger=inngest.TriggerEvent(event="benchmark/run-request"),
    retries=1,
    output_type=BenchmarkRunStartResult,
)
async def benchmark_run_start_fn(ctx: inngest.Context) -> BenchmarkRunStartResult:
    """Initialise a benchmark run from a CLI request.

    Steps
    -----
    1. Parse event payload into ``BenchmarkRunRequest``.
    2. Look up benchmark / worker / evaluator classes in the builtins registry.
    3. Build an ``Experiment``, persist it, create a ``RunRecord``.
    4. Emit ``workflow/started`` so the orchestration pipeline takes over.
    """
    payload = BenchmarkRunRequest.model_validate(ctx.event.data)
    logger.info(
        "benchmark-run-start: slug=%s model=%s worker=%s evaluator=%s",
        payload.benchmark_slug,
        payload.model,
        payload.worker_slug,
        payload.evaluator_slug,
    )

    if BENCHMARKS.get(payload.benchmark_slug) is None:
        raise RegistryLookupError("benchmark", payload.benchmark_slug)

    # reason: RFC 2026-04-22 §1 — config-time composition uses ``WorkerSpec``;
    # the registry is only hit here to validate the slug so we fail fast with
    # a ``RegistryLookupError`` instead of a late ``KeyError`` at execute.
    if payload.worker_slug not in WORKERS:
        raise RegistryLookupError("worker", payload.worker_slug)

    if EVALUATORS.get(payload.evaluator_slug) is None:
        raise RegistryLookupError("evaluator", payload.evaluator_slug)

    cohort_id = None
    if payload.cohort_name:
        cohort = experiment_cohort_service.resolve_or_create(
            name=payload.cohort_name,
            description=f"benchmark run request: {payload.benchmark_slug}",
            created_by="inngest",
        )
        cohort_id = cohort.id

    defined = ExperimentDefinitionService().define_benchmark_experiment(
        ExperimentDefineRequest(
            benchmark_slug=payload.benchmark_slug,
            cohort_id=cohort_id,
            limit=1,
            default_model_target=payload.model,
            default_worker_team={"primary": payload.worker_slug},
            default_evaluator_slug=payload.evaluator_slug,
            metadata={"source": BenchmarkRunRequest.name},
        )
    )
    launched = await ExperimentLaunchService().run_experiment(
        ExperimentRunRequest(experiment_id=defined.experiment_id)
    )
    run_id = launched.run_ids[0]
    definition_id = launched.workflow_definition_ids[0]

    return BenchmarkRunStartResult(
        run_id=run_id,
        definition_id=definition_id,
        benchmark=payload.benchmark_slug,
    )
