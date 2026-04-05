"""Benchmark subcommand: list and run benchmarks."""

import asyncio
import time
from argparse import Namespace

from arcane_cli.composition import build_experiment
from arcane_cli.discovery import list_benchmarks
from arcane_cli.rendering import render_run_result, render_table


def handle_benchmark(args: Namespace) -> int:
    if args.bench_action == "list":
        benchmarks = list_benchmarks()
        render_table(["Slug", "Name", "Description"], benchmarks)
        return 0
    elif args.bench_action == "run":
        return run_benchmark(args)
    else:
        print("Usage: arcane benchmark {list|run}")
        return 1


def run_benchmark(args: Namespace) -> int:
    import h_arcane.core.persistence.definitions.models  # noqa: F401
    import h_arcane.core.persistence.saved_specs.models  # noqa: F401
    import h_arcane.core.persistence.telemetry.models  # noqa: F401
    from h_arcane.core.persistence.shared.db import create_all_tables

    create_all_tables()

    experiment = build_experiment(
        benchmark_slug=args.slug,
        model=args.model,
        worker_slug=args.worker,
        evaluator_slug=args.evaluator,
        workflow=args.workflow,
        limit=args.limit,
    )
    experiment.validate()
    persisted = experiment.persist()
    render_run_result(persisted)
    print(f"\nExperiment persisted: {persisted.definition_id}")

    print("\nCreating run and dispatching via Inngest...")
    run_handle = asyncio.run(_create_and_dispatch(persisted, timeout=args.timeout))

    print(f"\nRun completed:")
    print(f"  Run ID:     {run_handle.run_id}")
    print(f"  Status:     {run_handle.status}")
    print(f"  Benchmark:  {run_handle.benchmark_type}")
    return 0 if run_handle.status == "completed" else 1


async def _create_and_dispatch(persisted, timeout: int = 600):
    import inngest

    from h_arcane.core.persistence.shared.db import get_session
    from h_arcane.core.persistence.shared.enums import TERMINAL_RUN_STATUSES, RunStatus
    from h_arcane.core.persistence.telemetry.models import RunRecord
    from h_arcane.core.runtime.events.task_events import WorkflowStartedEvent
    from h_arcane.core.runtime.inngest_client import inngest_client
    from h_arcane.core.runtime.services.run_service import create_run
    from h_arcane.api.handles import ExperimentRunHandle

    run = create_run(persisted)
    print(f"  Run ID: {run.id}")

    event = WorkflowStartedEvent(
        run_id=run.id,
        definition_id=persisted.definition_id,
    )
    await inngest_client.send(
        inngest.Event(
            name=WorkflowStartedEvent.name,
            data=event.model_dump(mode="json"),
        )
    )
    print("  WorkflowStartedEvent emitted. Polling for completion...")

    start = time.time()
    terminal = TERMINAL_RUN_STATUSES
    poll_interval = 2.0

    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            print(f"  TIMEOUT after {timeout}s")
            return ExperimentRunHandle(
                run_id=run.id,
                definition_id=persisted.definition_id,
                benchmark_type=persisted.benchmark_type,
                status="timeout",
            )

        session = get_session()
        try:
            current = session.get(RunRecord, run.id)
            if current and current.status in terminal:
                return ExperimentRunHandle(
                    run_id=run.id,
                    definition_id=persisted.definition_id,
                    benchmark_type=persisted.benchmark_type,
                    status=current.status,
                )
            status = current.status if current else "unknown"
        finally:
            session.close()

        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        print(f"  [{mins:02d}:{secs:02d}] status={status}")
        await asyncio.sleep(poll_interval)
