"""FastAPI application with Inngest webhook registration."""

import inngest.fast_api
from fastapi import FastAPI

from h_arcane.core.api.cohorts import router as cohorts_router
from h_arcane.core.api.runs import router as runs_router
from h_arcane.core.runtime.inngest_client import inngest_client
from h_arcane.core.runtime.inngest_registry import ALL_FUNCTIONS

app = FastAPI(
    title="H-Arcane",
    description="Arcane experiment orchestration API",
    version="0.1.0",
)

app.include_router(runs_router)
app.include_router(cohorts_router)

inngest.fast_api.serve(app, inngest_client, ALL_FUNCTIONS)
