"""FastAPI application for H-ARCANE experiments."""

import inngest
import inngest.fast_api
from fastapi import FastAPI

from h_arcane.core.infrastructure.inngest_client import inngest_client

# Import functions to ensure they're registered with the client
from h_arcane.core.orchestration.criteria_evaluator import evaluate_criterion_fn
from h_arcane.core.orchestration.task_evaluator import evaluate_task_run
from h_arcane.core.orchestration.run_cleanup import run_cleanup
from h_arcane.core.orchestration.run_evaluate import run_evaluate
from h_arcane.core.orchestration.worker_execute import worker_execute

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
        evaluate_criterion_fn,
    ],
)
