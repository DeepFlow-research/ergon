"""FastAPI application with Inngest webhook registration."""

from contextlib import asynccontextmanager

import inngest.fast_api
from fastapi import FastAPI

from ergon_core.core.api.cohorts import router as cohorts_router
from ergon_core.core.api.runs import router as runs_router
from ergon_core.core.persistence.shared.db import ensure_db
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.runtime.inngest_registry import ALL_FUNCTIONS


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_db()
    yield


app = FastAPI(
    title="Ergon Core",
    description="Ergon experiment orchestration API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(runs_router)
app.include_router(cohorts_router)

inngest.fast_api.serve(app, inngest_client, ALL_FUNCTIONS)
