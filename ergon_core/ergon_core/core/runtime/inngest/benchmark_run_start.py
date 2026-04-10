"""Inngest function triggered by benchmark/run-request from CLI.

Reconstructs the full Experiment object graph server-side, persists it,
creates a RunRecord, and emits workflow/started to kick off execution.
"""

import logging
from typing import ClassVar

import inngest
from ergon_builtins.registry import BENCHMARKS, EVALUATORS, WORKERS
from ergon_core.core.runtime.errors import RegistryLookupError
from ergon_core.api.experiment import Experiment
from ergon_core.core.runtime.events.base import InngestEventContract
from ergon_core.core.runtime.events.task_events import WorkflowStartedEvent
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.services.inngest_function_results import (
    BenchmarkRunStartResult,
)
from ergon_core.core.runtime.services.run_service import create_run

logger = logging.getLogger(__name__)


class BenchmarkRunRequest(InngestEventContract):
    """CLI sends this to request a full benchmark run."""

    name: ClassVar[str] = "benchmark/run-request"

    benchmark_slug: str
    model: str
    worker_slug: str = "stub-worker"
    evaluator_slug: str = "stub-rubric"
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

    benchmark_cls = BENCHMARKS.get(payload.benchmark_slug)
    if benchmark_cls is None:
        raise RegistryLookupError("benchmark", payload.benchmark_slug)
    worker_cls = WORKERS.get(payload.worker_slug)
    if worker_cls is None:
        raise RegistryLookupError("worker", payload.worker_slug)
    evaluator_cls = EVALUATORS.get(payload.evaluator_slug)
    if evaluator_cls is None:
        raise RegistryLookupError("evaluator", payload.evaluator_slug)

    benchmark = benchmark_cls()
    worker = worker_cls(name="worker", model=payload.model)
    evaluator = evaluator_cls(name="evaluator")

    experiment = Experiment.from_single_worker(
        benchmark=benchmark,
        worker=worker,
        evaluators={"default": evaluator},
    )
    persisted = experiment.persist()

    run = create_run(persisted)

    event = WorkflowStartedEvent(
        run_id=run.id,
        definition_id=persisted.definition_id,
    )
    await inngest_client.send(
        inngest.Event(
            name=WorkflowStartedEvent.name,
            data=event.model_dump(mode="json"),
        )
    )

    return BenchmarkRunStartResult(
        run_id=run.id,
        definition_id=persisted.definition_id,
        benchmark=payload.benchmark_slug,
    )
