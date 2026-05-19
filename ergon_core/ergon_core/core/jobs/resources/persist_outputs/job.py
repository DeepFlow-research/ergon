"""Inngest child function: persist outputs from sandbox via resource service.

All resource row semantics go through :class:`RunResourcePublishService`.
Consumers read via
(``kind='report'``/``kind='artifact'`` rows whose ``file_path`` points at the
content-addressed blob store).
"""

import logging
from datetime import UTC, datetime

from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from .contract import PersistOutputsRequest, PersistOutputsResult
from .composition import publish_public_sandbox_resources
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    persist_outputs_context,
)

logger = logging.getLogger(__name__)


async def run_persist_outputs_job(payload: PersistOutputsRequest) -> PersistOutputsResult:
    """Sync sandbox publish dirs to the blob store and register resources."""
    run_id = payload.run_id
    task_id = payload.task_id
    execution_id = payload.execution_id
    span_start = datetime.now(UTC)
    sandbox_id = payload.sandbox_id

    logger.info(
        "persist-outputs run_id=%s task_id=%s sandbox_id=%s",
        run_id,
        task_id,
        sandbox_id,
    )

    if not sandbox_id:
        raise ContractViolationError(
            "persist-outputs invoked without sandbox_id",
            run_id=run_id,
            task_id=task_id,
        )

    with get_session() as session:
        view = await RuntimeGraphRepository().node(
            session,
            run_id=payload.run_id,
            task_id=payload.task_id,
            sandbox_id=sandbox_id,
        )

    outputs_count = await publish_public_sandbox_resources(view.task.sandbox, payload)

    get_trace_sink().emit_span(
        CompletedSpan(
            name="persist.outputs",
            context=persist_outputs_context(run_id, task_id, execution_id),
            start_time=span_start,
            end_time=datetime.now(UTC),
            attributes={
                "run_id": str(run_id),
                "task_id": str(task_id),
                "execution_id": str(execution_id),
                "outputs_count": outputs_count,
            },
        )
    )

    if outputs_count:
        logger.info(
            "persist-outputs: public sandbox publisher created %d resource(s) for run_id=%s",
            outputs_count,
            payload.run_id,
        )
    return PersistOutputsResult(outputs_count=outputs_count)
