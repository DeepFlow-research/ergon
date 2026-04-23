"""FastAPI application with Inngest webhook registration."""

import logging
import os
from contextlib import asynccontextmanager

import inngest.fast_api
from ergon_core.core.api.cohorts import router as cohorts_router
from ergon_core.core.api.rollouts import init_service as init_rollout_service
from ergon_core.core.api.rollouts import router as rollouts_router
from ergon_core.core.api.runs import router as runs_router
from ergon_core.core.api.test_harness import router as _test_harness_router
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.providers.sandbox.event_sink import DashboardEmitterSandboxEventSink
from ergon_core.core.providers.sandbox.manager import DefaultSandboxManager
from ergon_core.core.rl.rollout_service import RolloutService
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.inngest_registry import ALL_FUNCTIONS
from ergon_core.core.settings import Settings
from fastapi import FastAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting ensure_db...")
    ensure_db()
    logger.info("ensure_db done, initializing RolloutService...")
    settings = Settings()
    init_rollout_service(
        RolloutService(
            session_factory=get_session,
            inngest_send=inngest_client.send_sync,
            tokenizer_name=settings.default_tokenizer,
        )
    )

    # Wire the dashboard event sink on every sandbox manager subclass.
    # Import ergon_builtins here (deferred) to avoid a circular import at
    # module level; ergon_builtins imports ergon_core, not the reverse.
    from ergon_builtins.registry import SANDBOX_MANAGERS  # noqa: PLC0415

    sink = DashboardEmitterSandboxEventSink(dashboard_emitter)
    DefaultSandboxManager.set_event_sink(sink)
    for manager_cls in SANDBOX_MANAGERS.values():
        manager_cls.set_event_sink(sink)
    logger.info(
        "sandbox event sink wired on %d manager subclass(es)",
        1 + len(SANDBOX_MANAGERS),
    )

    logger.info("ready")
    yield


app = FastAPI(
    title="Ergon Core",
    description="Ergon experiment orchestration API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(runs_router)
app.include_router(cohorts_router)
app.include_router(rollouts_router)

# Test-only harness: mounted in CI + local-e2e only.
if os.environ.get("ENABLE_TEST_HARNESS") == "1":
    app.include_router(_test_harness_router)
    # Register the canonical-smoke WORKERS / EVALUATORS into this
    # process's registry dicts.  Inngest's ``worker_execute_fn`` runs
    # inside this container, so if the smoke fixtures are only imported
    # host-side (in pytest's process) the container's dicts stay empty
    # and every smoke run fails at worker resolution.  Gated on the
    # same env var as the router so production images with the harness
    # disabled don't import ``tests/`` at all.
    import tests.e2e._fixtures  # noqa: F401, PLC0415

inngest.fast_api.serve(app, inngest_client, ALL_FUNCTIONS)
