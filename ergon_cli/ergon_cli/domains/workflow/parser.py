import argparse

from ergon_cli.domains.workflow.commands import handle_workflow


def register_workflow_parser(subparsers: argparse._SubParsersAction) -> None:
    workflow = subparsers.add_parser("workflow", help="Workflow topology and resource operations")
    workflow.set_defaults(handler=handle_workflow)
    workflow.add_argument("--sample-id", default=None, help="Current run UUID")
    workflow.add_argument("--task-id", default=None, help="Current task UUID")
    workflow.add_argument("--execution-id", default=None, help="Current task execution UUID")
    workflow.add_argument("--sandbox-task-key", default=None, help="Sandbox task key UUID")
    workflow.add_argument(
        "--environment-type", default="default", help="Environment/sandbox manager slug"
    )
    workflow.add_argument("workflow_args", nargs=argparse.REMAINDER)
