"""Run subcommand: list and cancel experiment runs."""

from argparse import Namespace
from uuid import UUID

from ergon_core.core.persistence.shared.db import ensure_db, get_session
from ergon_core.core.persistence.telemetry.models import RunRecord
from ergon_core.core.application.runtime.run_records import cancel_run as do_cancel
from sqlmodel import select

from ergon_cli.rendering import render_table


def _run_definition_filter(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid UUID: {value}") from exc


def _no_runs_message(args: Namespace) -> str:
    parts = ["No runs found"]
    if args.status:
        parts.append(f"with status={args.status!r}")
    if args.definition_id:
        parts.append(f"for definition_id={args.definition_id!r}")
    if args.experiment:
        parts.append(f"for experiment={args.experiment!r}")
    return " ".join(parts)


def _run_table_rows(runs: list[RunRecord]) -> list[list[str]]:
    rows = []
    for run in runs:
        run_id = str(run.id)[:8]
        created = run.created_at.strftime("%Y-%m-%d %H:%M") if run.created_at else "-"
        duration = ""
        if run.started_at and run.completed_at:
            delta = run.completed_at - run.started_at
            duration = f"{int(delta.total_seconds())}s"
        rows.append([run_id, run.status, created, duration, str(run.id)])
    return rows


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
    try:
        definition_id = _run_definition_filter(args.definition_id)
    except ValueError as exc:
        print(str(exc))
        return 1

    with get_session() as session:
        stmt = select(RunRecord).order_by(RunRecord.created_at.desc())  # type: ignore[attr-defined]
        if args.status:
            stmt = stmt.where(RunRecord.status == args.status)
        if args.experiment:
            stmt = stmt.where(RunRecord.experiment == args.experiment)
        if definition_id is not None:
            stmt = stmt.where(RunRecord.definition_id == definition_id)
        stmt = stmt.limit(args.limit)
        runs = list(session.exec(stmt).all())

    if not runs:
        print(_no_runs_message(args))
        return 0

    render_table(["ID (short)", "Status", "Created", "Duration", "Full ID"], _run_table_rows(runs))
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
    print(f"definition_id:          {run.definition_id}")
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
