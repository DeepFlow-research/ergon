"""FastAPI application for H-ARCANE experiments."""

import inngest.fast_api
from fastapi import FastAPI

from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.inngest_registry import ALL_FUNCTIONS

# Create FastAPI app
app = FastAPI(
    title="H-ARCANE Experiments",
    description="API for running and managing H-ARCANE experiments",
    version="0.1.0",
)

# Register all Inngest functions with FastAPI
inngest.fast_api.serve(
    app,
    inngest_client,
    ALL_FUNCTIONS,
)
