import argparse

from ergon_cli.domains.runs.commands import handle_run


def register_run_parser(subparsers: argparse._SubParsersAction) -> None:
    run = subparsers.add_parser("run", help="Run management")
    run.set_defaults(handler=handle_run)
    run_sub = run.add_subparsers(dest="run_action")
    run_list_parser = run_sub.add_parser("list", help="List recent runs")
    run_list_parser.add_argument("--limit", type=int, default=20, help="Number of runs to show")
    run_list_parser.add_argument(
        "--status",
        default=None,
        help="Filter by status (pending, executing, completed, failed, cancelled)",
    )
    run_list_parser.add_argument(
        "--definition-id",
        default=None,
        help="Filter by definition UUID",
    )
    run_list_parser.add_argument(
        "--experiment",
        default=None,
        help="Filter by v2 experiment tag",
    )
    run_cancel_parser = run_sub.add_parser("cancel", help="Cancel a running experiment")
    run_cancel_parser.add_argument("run_id", help="Run ID (UUID) to cancel")
    run_status_parser = run_sub.add_parser("status", help="Show status of one run")
    run_status_parser.add_argument("run_id", help="Run ID (UUID)")
