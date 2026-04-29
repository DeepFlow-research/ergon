"""FastAPI application with Inngest webhook registration."""

import logging
import os
import sys
from contextlib import asynccontextmanager
from importlib import import_module

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
from ergon_core.api.registry import registry
from ergon_core.core.rest_api.cohorts import router as cohorts_router
from ergon_core.core.rest_api.experiments import router as experiments_router
from ergon_core.core.rest_api.rollouts import router as rollouts_router
from ergon_core.core.rest_api.runs import router as runs_router
from ergon_core.core.rest_api.test_harness import router as _test_harness_router
from ergon_core.core.infrastructure.dashboard.provider import init_dashboard_emitter, reset_dashboard_emitter
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.infrastructure.sandbox.event_sink import (
    CompoundSandboxEventSink,
    DashboardEmitterSandboxEventSink,
    PostgresSandboxEventSink,
)
from ergon_core.core.infrastructure.sandbox.manager import DefaultSandboxManager
from ergon_core.core.rl.rollout_service import RolloutService
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.infrastructure.inngest.registry import ALL_FUNCTIONS
from ergon_core.core.shared.settings import Settings, settings
from fastapi import FastAPI

logger = logging.getLogger(__name__)


def _run_startup_plugins(plugin_specs: tuple[str, ...]) -> None:
    for spec in plugin_specs:
        module_name, sep, attr_name = spec.partition(":")
        if not sep or not module_name or not attr_name:
            raise RuntimeError(
                f"Invalid ERGON_STARTUP_PLUGINS entry {spec!r}; expected 'module:function'"
            )
        module = import_module(module_name)
        plugin = getattr(module, attr_name)  # slopcop: ignore[no-hasattr-getattr]
        plugin()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting ensure_db...")
    ensure_db()
    logger.info("ensure_db done, initializing RolloutService...")
    settings = Settings()
    app.state.rollout_service = RolloutService(
        session_factory=get_session,
        inngest_send=inngest_client.send_sync,
        tokenizer_name=settings.default_tokenizer,
    )
    app.state.vllm_manager = None
    dashboard_emitter = init_dashboard_emitter(enabled=True)
    app.state.dashboard_emitter = dashboard_emitter

    _run_startup_plugins(settings.startup_plugins)

    # Wire the dashboard event sink on every registered sandbox manager class.
    sink = CompoundSandboxEventSink(
        DashboardEmitterSandboxEventSink(dashboard_emitter),
        PostgresSandboxEventSink(),
    )
    DefaultSandboxManager.set_event_sink(sink)
    for manager_cls in registry.sandbox_managers.values():
        manager_cls.set_event_sink(sink)
    logger.info(
        "sandbox event sink wired on %d manager subclass(es)",
        1 + len(registry.sandbox_managers),
    )

    logger.info("app startup complete — all subsystems initialised")
    try:
        yield
    finally:
        reset_dashboard_emitter()


app = FastAPI(
    title="Ergon Core",
    description="Ergon experiment orchestration API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(runs_router)
app.include_router(cohorts_router)
app.include_router(experiments_router)
app.include_router(rollouts_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Test-only harness: mounted in CI + local-e2e only.
if settings.enable_test_harness:
    app.include_router(_test_harness_router)

inngest.fast_api.serve(app, inngest_client, ALL_FUNCTIONS)
