"""FastAPI application for H-ARCANE experiments."""

import inngest.fast_api
from fastapi import FastAPI

from h_arcane.core._internal.api.cohorts import router as cohorts_router
from h_arcane.core._internal.api.runs import router as runs_router
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.inngest_registry import ALL_FUNCTIONS

# Create FastAPI app
app = FastAPI(
    title="H-ARCANE Experiments",
    description="API for running and managing H-ARCANE experiments",
    version="0.1.0",
)

app.include_router(cohorts_router)
app.include_router(runs_router)

# Register all Inngest functions with FastAPI
inngest.fast_api.serve(
    app,
    inngest_client,
    ALL_FUNCTIONS,
)
