"""FastAPI application for H-ARCANE experiments."""

import inngest
import inngest.fast_api
from fastapi import FastAPI

from h_arcane.inngest.client import inngest_client

# Import functions to ensure they're registered with the client
from h_arcane.evaluation.task_evaluator import evaluate_task_run  # noqa: F401
from h_arcane.inngest.functions import run_cleanup, run_evaluate, worker_execute  # noqa: F401

# Create FastAPI app
app = FastAPI(
    title="H-ARCANE Experiments",
    description="API for running and managing H-ARCANE experiments",
    version="0.1.0",
)


# Register Inngest functions with FastAPI
inngest.fast_api.serve(
    app,
    inngest_client,
    [
        worker_execute,
        run_evaluate,
        run_cleanup,
        evaluate_task_run,
    ],
)
