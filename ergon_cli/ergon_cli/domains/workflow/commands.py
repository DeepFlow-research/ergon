import argparse

from ergon_cli.domains.workflow.context import build_workflow_context
from ergon_cli.domains.workflow.executor import build_workflow_parser, execute_workflow_command
from ergon_core.core.application.runtime.run_lifecycle import WorkflowService
from ergon_core.core.persistence.shared.db import get_session


async def handle_workflow(args: argparse.Namespace) -> int:
    command_parts = args.workflow_args if args.workflow_args is not None else []
    command = " ".join(command_parts)
    if not command:
        build_workflow_parser().print_help()
        return 0
    missing = [
        name
        for name, value in {
            "--run-id": args.run_id,
            "--task-id": args.task_id,
            "--execution-id": args.execution_id,
            "--sandbox-task-key": args.sandbox_task_key,
        }.items()
        if value is None
    ]
    if missing:
        raise SystemExit(f"{', '.join(missing)} are required for local CLI workflow commands")
    output = execute_workflow_command(
        command,
        context=build_workflow_context(
            run_id=args.run_id,
            task_id=args.task_id,
            execution_id=args.execution_id,
            sandbox_task_key=args.sandbox_task_key,
            benchmark_type=args.benchmark_type,
        ),
        session_factory=get_session,
        service=WorkflowService(),
    )
    if output.stdout:
        print(output.stdout)
    if output.stderr:
        print(output.stderr)
    return output.exit_code
