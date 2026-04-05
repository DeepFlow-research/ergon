"""Inngest client singleton and shared configuration."""

import inngest
from h_arcane.core.settings import settings

inngest_client = inngest.Inngest(
    app_id="h-arcane",
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
