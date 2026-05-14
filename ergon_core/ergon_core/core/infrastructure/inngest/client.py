"""Inngest client singleton and shared configuration."""

import logging

import inngest
from ergon_core.core.shared.settings import settings

InngestEvent = inngest.Event

# Pass a Python logger to the Inngest SDK so handler exceptions reach
# stdout (and therefore `docker compose logs api` + the CI log dump
# step). Without this, the SDK swallows every `@create_function`
# handler exception into the Inngest function-output payload and never
# re-emits it through Python logging — leaving operators to query the
# Inngest GraphQL endpoint at `http://localhost:8289/v0/gql` to even
# discover that anything failed. CI's
# `docker compose logs api --tail 200` step is silent in exactly the
# same way without this wiring.
inngest_client = inngest.Inngest(
    app_id="ergon-core",
    event_key=settings.inngest_event_key or "local-dev",
    is_production=not settings.inngest_dev,
    api_base_url=settings.inngest_api_base_url,
    event_api_base_url=settings.inngest_api_base_url,
    serializer=inngest.PydanticSerializer(),
    logger=logging.getLogger("ergon_core.inngest"),
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
