from argparse import Namespace

from ergon_cli.domains.runs.models import CancelRunCommand, ListRunsCommand, RunStatusCommand
from ergon_cli.domains.runs.service import cancel_existing_run, get_run_status, list_runs
from ergon_cli.shared import exit_codes
from ergon_cli.shared.errors import CliError
from ergon_cli.shared.output import render_table, render_text
from ergon_cli.shared.parsing import parse_uuid


def handle_run(args: Namespace) -> int:
    if args.run_action == "list":
        return list_runs_command(args)
    if args.run_action == "cancel":
        return cancel_run_command(args)
    if args.run_action == "status":
        return status_run_command(args)
    print("Usage: ergon run {list|status|cancel}")
    return exit_codes.RUNTIME_ERROR


def list_runs_command(args: Namespace) -> int:
    try:
        definition_id = (
            parse_uuid(args.definition_id, field_name="definition_id")
            if args.definition_id
            else None
        )
        result = list_runs(
            ListRunsCommand(
                limit=args.limit,
                status=args.status,
                definition_id=definition_id,
                experiment=args.experiment,
            )
        )
    except CliError as exc:
        print(exc.message)
        return exc.exit_code

    if not result.runs:
        parts = ["No runs found"]
        if result.status:
            parts.append(f"with status={result.status!r}")
        if result.definition_id:
            parts.append(f"for definition_id={str(result.definition_id)!r}")
        if result.experiment:
            parts.append(f"for experiment={result.experiment!r}")
        print(" ".join(parts))
        return exit_codes.OK

    print(
        render_table(
            ["ID (short)", "Status", "Created", "Duration", "Full ID"],
            [
                [str(run.id)[:8], run.status, run.created, run.duration, str(run.id)]
                for run in result.runs
            ],
        )
    )
    return exit_codes.OK


def cancel_run_command(args: Namespace) -> int:
    try:
        result = cancel_existing_run(CancelRunCommand(run_id=parse_uuid(args.run_id)))
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    print(
        render_text(
            [
                f"Run {result.run.id} cancelled.",
                f"  Status:  {result.run.status}",
                "  Inngest: run/cancelled event sent (in-flight functions will be killed)",
                "  Cleanup: run/cleanup event sent (sandbox teardown scheduled)",
            ]
        )
    )
    return exit_codes.OK


def status_run_command(args: Namespace) -> int:
    try:
        run = get_run_status(RunStatusCommand(run_id=parse_uuid(args.run_id)))
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    lines = [
        f"run_id:                 {run.id}",
        f"status:                 {run.status}",
        f"benchmark_type:         {run.benchmark_type}",
        f"definition_id:          {run.definition_id}",
        f"instance_key:           {run.instance_key}",
    ]
    if run.evaluator_slug is not None:
        lines.append(f"evaluator:              {run.evaluator_slug}")
    if run.model_target is not None:
        lines.append(f"model:                  {run.model_target}")
    lines.append(f"created_at:             {run.created}")
    if run.started:
        lines.append(f"started_at:             {run.started}")
    if run.completed:
        lines.append(f"completed_at:           {run.completed}")
    if run.error_message:
        lines.append(f"error:                  {run.error_message}")
    print(render_text(lines))
    return exit_codes.OK
