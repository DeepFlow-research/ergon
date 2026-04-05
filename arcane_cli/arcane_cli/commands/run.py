"""Run subcommand: list and cancel experiment runs."""

from argparse import Namespace
from uuid import UUID

from arcane_cli.rendering import render_table


def handle_run(args: Namespace) -> int:
    if args.run_action == "list":
        return list_runs(args)
    elif args.run_action == "cancel":
        return cancel_run(args)
    else:
        print("Usage: arcane run {list|cancel}")
        return 1


def list_runs(args: Namespace) -> int:
    import h_arcane.core.persistence.definitions.models  # noqa: F401
    import h_arcane.core.persistence.saved_specs.models  # noqa: F401
    import h_arcane.core.persistence.telemetry.models  # noqa: F401
    from h_arcane.core.persistence.shared.db import create_all_tables, get_session
    from h_arcane.core.persistence.telemetry.models import RunRecord
    from sqlmodel import select

    create_all_tables()

    with get_session() as session:
        stmt = select(RunRecord).order_by(RunRecord.created_at.desc())  # type: ignore[attr-defined]
        if args.status:
            stmt = stmt.where(RunRecord.status == args.status)
        stmt = stmt.limit(args.limit)
        runs = list(session.exec(stmt).all())

    if not runs:
        print("No runs found.")
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
    import h_arcane.core.persistence.definitions.models  # noqa: F401
    import h_arcane.core.persistence.saved_specs.models  # noqa: F401
    import h_arcane.core.persistence.telemetry.models  # noqa: F401
    from h_arcane.core.persistence.shared.db import create_all_tables
    from h_arcane.core.runtime.services.run_service import cancel_run as do_cancel

    create_all_tables()

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
    print(f"  Inngest: run/cancelled event sent (in-flight functions will be killed)")
    print(f"  Cleanup: run/cleanup event sent (sandbox teardown scheduled)")
    return 0
