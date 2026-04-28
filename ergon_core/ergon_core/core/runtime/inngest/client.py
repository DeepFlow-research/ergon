"""Inngest client singleton and shared configuration."""

import inngest
from ergon_core.core.settings import settings

inngest_client = inngest.Inngest(
    app_id="ergon-core",
    event_key=settings.inngest_event_key or "local-dev",
    is_production=not settings.inngest_dev,
    api_base_url=settings.inngest_api_base_url,
    event_api_base_url=settings.inngest_api_base_url,
    serializer=inngest.PydanticSerializer(),
)

# All orchestration functions carry run_id in their trigger event data.
# Sending a run/cancelled event with a matching run_id kills them in-flight.
RUN_CANCEL = [
    inngest.Cancel(
        event="run/cancelled",
        if_exp="event.data.run_id == async.data.run_id",
    )
]

# Per-node cancel matcher. Fires on task/cancelled for this exact node_id.
# Used by execute_task_fn to drop queued or terminate in-flight invocations
# when a parent terminates or the manager explicitly cancels.
TASK_CANCEL = [
    inngest.Cancel(
        event="task/cancelled",
        if_exp="event.data.node_id == async.data.node_id",
    ),
]
