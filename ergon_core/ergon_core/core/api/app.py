"""FastAPI application with Inngest webhook registration."""

from contextlib import asynccontextmanager

import inngest.fast_api
from fastapi import FastAPI

from ergon_core.core.api.cohorts import router as cohorts_router
from ergon_core.core.api.rollouts import init_service as init_rollout_service
from ergon_core.core.api.rollouts import router as rollouts_router
from ergon_core.core.api.runs import router as runs_router
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.rl.rollout_service import RolloutService
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.inngest_registry import ALL_FUNCTIONS
from ergon_core.core.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[LIFESPAN] starting ensure_db...", flush=True)
    ensure_db()
    print("[LIFESPAN] ensure_db done, initializing RolloutService...", flush=True)
    settings = Settings()
    init_rollout_service(RolloutService(
        session_factory=get_session,
        inngest_send=inngest_client.send_sync,
        tokenizer_name=settings.default_tokenizer,
    ))
    print("[LIFESPAN] ready", flush=True)
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

inngest.fast_api.serve(app, inngest_client, ALL_FUNCTIONS)
