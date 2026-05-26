import argparse

from ergon_cli.domains.samples.commands import handle_sample


def register_sample_parser(subparsers: argparse._SubParsersAction) -> None:
    sample = subparsers.add_parser("sample", help="Sample management")
    sample.set_defaults(handler=handle_sample)
    sample_sub = sample.add_subparsers(dest="sample_action")
    sample_list_parser = sample_sub.add_parser("list", help="List recent samples")
    sample_list_parser.add_argument(
        "--limit", type=int, default=20, help="Number of samples to show"
    )
    sample_list_parser.add_argument(
        "--status",
        default=None,
        help="Filter by status (pending, executing, completed, failed, cancelled)",
    )
    sample_list_parser.add_argument(
        "--definition-id",
        default=None,
        help="Filter by definition UUID",
    )
    sample_list_parser.add_argument(
        "--experiment",
        default=None,
        help="Filter by v2 experiment tag",
    )
    sample_cancel_parser = sample_sub.add_parser("cancel", help="Cancel a running sample")
    sample_cancel_parser.add_argument("sample_id", help="Sample ID (UUID) to cancel")
    sample_status_parser = sample_sub.add_parser("status", help="Show status of one sample")
    sample_status_parser.add_argument("sample_id", help="Sample ID (UUID)")
    sample_show_parser = sample_sub.add_parser("show", help="Show sample detail")
    sample_show_parser.add_argument("sample_id", help="Sample ID (UUID)")
    sample_events_parser = sample_sub.add_parser("events", help="List typed WAL events for a sample")
    sample_events_parser.add_argument("sample_id", help="Sample ID (UUID)")
    sample_graph_parser = sample_sub.add_parser("graph", help="Show sample graph projection")
    sample_graph_parser.add_argument("sample_id", help="Sample ID (UUID)")
