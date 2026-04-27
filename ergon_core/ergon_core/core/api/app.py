"""FastAPI application with Inngest webhook registration."""

import logging
import os
import sys
from contextlib import asynccontextmanager

# Root-logger handler so ``logger.exception`` / ``logger.error`` from
# anywhere in the app actually reach ``docker compose logs api``.
# Uvicorn configures its own ``uvicorn``/``uvicorn.error`` loggers but
# does not touch the root, which leaves every ``logging.getLogger(__
# name__)`` call effectively silent under default settings.  Without
# this handler, a worker_execute traceback becomes "silently failing"
# on the dashboard side without ever surfacing in logs.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)

import inngest.fast_api
from ergon_core.core.api.cohorts import router as cohorts_router
from ergon_core.core.api.experiments import router as experiments_router
from ergon_core.core.api.rollouts import init_service as init_rollout_service
from ergon_core.core.api.rollouts import router as rollouts_router
from ergon_core.core.api.runs import router as runs_router
from ergon_core.core.api.startup_plugins import run_startup_plugins
from ergon_core.core.api.test_harness import router as _test_harness_router
from ergon_core.core.dashboard.emitter import dashboard_emitter
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.providers.sandbox.event_sink import (
    CompoundSandboxEventSink,
    DashboardEmitterSandboxEventSink,
    PostgresSandboxEventSink,
)
from ergon_core.core.providers.sandbox.manager import DefaultSandboxManager
from ergon_core.core.rl.rollout_service import RolloutService
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.inngest_registry import ALL_FUNCTIONS
from ergon_core.core.settings import Settings, settings
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
    from ergon_builtins.registry import SANDBOX_MANAGERS

    sink = CompoundSandboxEventSink(
        DashboardEmitterSandboxEventSink(dashboard_emitter),
        PostgresSandboxEventSink(),
    )
    DefaultSandboxManager.set_event_sink(sink)
    for manager_cls in SANDBOX_MANAGERS.values():
        manager_cls.set_event_sink(sink)
    logger.info(
        "sandbox event sink wired on %d manager subclass(es)",
        1 + len(SANDBOX_MANAGERS),
    )

    logger.info("app startup complete — all subsystems initialised")
    yield


app = FastAPI(
    title="Ergon Core",
    description="Ergon experiment orchestration API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(runs_router)
app.include_router(experiments_router)
app.include_router(cohorts_router)
app.include_router(rollouts_router)

# Test-only harness: mounted in CI + local-e2e only.
if settings.enable_test_harness:
    app.include_router(_test_harness_router)

run_startup_plugins(settings.startup_plugins)

inngest.fast_api.serve(app, inngest_client, ALL_FUNCTIONS)
