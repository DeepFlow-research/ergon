"""Run subcommand: list and cancel experiment runs."""

from argparse import Namespace
from uuid import UUID

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.application.workflows.runs import cancel_run as do_cancel
from sqlmodel import select

from ergon_cli.rendering import render_table


def handle_run(args: Namespace) -> int:
    if args.run_action == "list":
        return list_runs(args)
    elif args.run_action == "cancel":
        return cancel_run(args)
    elif args.run_action == "status":
        return status_run(args)
    else:
        print("Usage: ergon run {list|status|cancel}")
        return 1


def list_runs(args: Namespace) -> int:
    ensure_db()

    with get_session() as session:
        stmt = select(RunRecord).order_by(RunRecord.created_at.desc())  # type: ignore[attr-defined]
        if args.status:
            stmt = stmt.where(RunRecord.status == args.status)
        if args.experiment:
            stmt = stmt.join(
                ExperimentDefinition,
                RunRecord.workflow_definition_id == ExperimentDefinition.id,  # type: ignore[invalid-argument-type]
            ).where(ExperimentDefinition.name == args.experiment)
        stmt = stmt.limit(args.limit)
        runs = list(session.exec(stmt).all())

    if not runs:
        parts = ["No runs found"]
        if args.status:
            parts.append(f"with status={args.status!r}")
        if args.experiment:
            parts.append(f"for experiment={args.experiment!r}")
        print(" ".join(parts))
        return 0

    rows = []
    for r in runs:
        run_id = str(r.id)[:8]
        created = r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "-"
        duration = ""
        if r.started_at and r.completed_at:
            delta = r.completed_at - r.started_at
            duration = f"{int(delta.total_seconds())}s"
        rows.append([run_id, r.status, created, duration, str(r.id)])

    render_table(["ID (short)", "Status", "Created", "Duration", "Full ID"], rows)
    return 0


def cancel_run(args: Namespace) -> int:
    ensure_db()
    try:
        run_id = UUID(args.run_id)
    except ValueError:
        print(f"Invalid UUID: {args.run_id}")
        return 1

    try:
        run = do_cancel(run_id)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"Run {run.id} cancelled.")
    print(f"  Status:  {run.status}")
    print("  Inngest: run/cancelled event sent (in-flight functions will be killed)")
    print("  Cleanup: run/cleanup event sent (sandbox teardown scheduled)")
    return 0


def status_run(args: Namespace) -> int:
    ensure_db()
    try:
        run_id = UUID(args.run_id)
    except ValueError:
        print(f"Invalid UUID: {args.run_id}")
        return 1

    with get_session() as session:
        run = session.get(RunRecord, run_id)
        if run is None:
            print(f"No run found with id {args.run_id}")
            return 1

    print(f"run_id:                 {run.id}")
    print(f"status:                 {run.status}")
    print(f"benchmark_type:         {run.benchmark_type}")
    print(f"workflow_definition_id: {run.workflow_definition_id}")
    print(f"instance_key:           {run.instance_key}")
    if run.evaluator_slug is not None:
        print(f"evaluator:              {run.evaluator_slug}")
    if run.model_target is not None:
        print(f"model:                  {run.model_target}")
    created = run.created_at.strftime("%Y-%m-%d %H:%M:%S") if run.created_at else "-"
    print(f"created_at:             {created}")
    if run.started_at:
        print(f"started_at:             {run.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    if run.completed_at:
        print(f"completed_at:           {run.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
    if run.error_message:
        print(f"error:                  {run.error_message}")
    return 0
