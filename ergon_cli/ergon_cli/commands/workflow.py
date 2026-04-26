import argparse
import asyncio
import json
import shlex
from typing import cast
from uuid import UUID

from ergon_core.api.json_types import JsonObject
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.runtime.services.workflow_service import WorkflowService
from pydantic import BaseModel
from sqlmodel import Session

_FORBIDDEN_CONTEXT_FLAGS = {
    "--run-id",
    "--node-id",
    "--execution-id",
    "--sandbox-id",
    "--sandbox-task-key",
    "--benchmark-type",
}


class WorkflowCommandContext(BaseModel):
    model_config = {"frozen": True}

    run_id: UUID
    node_id: UUID | None = None
    execution_id: UUID | None = None
    sandbox_task_key: UUID | None = None
    benchmark_type: str = "default"


class WorkflowCommandOutput(BaseModel):
    model_config = {"frozen": True}

    stdout: str
    stderr: str | None = None
    exit_code: int = 0


def build_workflow_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workflow")
    sub = parser.add_subparsers(dest="group", required=True)

    inspect = sub.add_parser("inspect")
    inspect_sub = inspect.add_subparsers(dest="action", required=True)
    resource_list = inspect_sub.add_parser("resource-list")
    resource_list.add_argument("--scope", required=True)
    resource_list.add_argument("--kind", default=None)
    resource_list.add_argument("--limit", type=int, default=50)
    resource_list.add_argument("--max-depth", type=int, default=3)
    resource_list.add_argument("--format", choices=["text", "json"], default="text")
    resource_list.add_argument("--explain", action="store_true")

    resource_content = inspect_sub.add_parser("resource-content")
    resource_content.add_argument("--resource-id", required=True)
    resource_content.add_argument("--max-bytes", type=int, default=100_000)
    resource_content.add_argument("--format", choices=["text", "json"], default="text")

    task_tree = inspect_sub.add_parser("task-tree")
    task_tree.add_argument("--format", choices=["text", "json"], default="text")
    task_tree.add_argument("--parent-node-id", default=None)

    dependencies = inspect_sub.add_parser("task-dependencies")
    dependencies.add_argument(
        "--direction", choices=["upstream", "downstream", "both"], default="both"
    )
    dependencies.add_argument("--format", choices=["text", "json"], default="text")

    next_action = inspect_sub.add_parser("next-actions")
    next_action.add_argument("--manager-capable", action="store_true")
    next_action.add_argument("--format", choices=["text", "json"], default="text")

    manage = sub.add_parser("manage")
    manage_sub = manage.add_subparsers(dest="action", required=True)
    materialize = manage_sub.add_parser("materialize-resource")
    materialize.add_argument("--resource-id", required=True)
    materialize.add_argument("--destination", default=None)
    materialize.add_argument("--dry-run", action="store_true")
    materialize.add_argument("--format", choices=["text", "json"], default="text")

    for action in ("add-task", "add-edge", "restart-task", "abandon-task"):
        parser_for_action = manage_sub.add_parser(action)
        parser_for_action.add_argument("--dry-run", action="store_true")
        parser_for_action.add_argument("--format", choices=["text", "json"], default="text")
        parser_for_action.add_argument("--reason", default=None)

    return parser


def execute_workflow_command(
    command: str,
    *,
    context: WorkflowCommandContext,
    session_factory=get_session,
    service: WorkflowService | None = None,
) -> WorkflowCommandOutput:
    argv = shlex.split(command)
    _reject_context_flags(argv)
    args = build_workflow_parser().parse_args(argv)
    workflow_service = service or WorkflowService()
    session = (session_factory or get_session)()
    try:
        if args.group == "inspect":
            return _handle_inspect(args, context=context, session=session, service=workflow_service)
        if args.group == "manage":
            return asyncio.run(  # slopcop: ignore[no-async-from-sync] -- CLI/tool sync bridge
                _handle_manage(args, context=context, session=session, service=workflow_service)
            )
    finally:
        _close_session(session)
    raise ValueError(f"unsupported workflow command group: {args.group}")


async def handle_workflow(args: argparse.Namespace) -> int:
    command_parts = args.workflow_args if args.workflow_args is not None else []
    command = " ".join(command_parts)
    if not command:
        build_workflow_parser().print_help()
        return 0
    if args.run_id is None:
        raise SystemExit("--run-id is required for local CLI workflow commands")
    context = WorkflowCommandContext(
        run_id=UUID(args.run_id),
        node_id=UUID(args.node_id) if args.node_id else None,
        execution_id=UUID(args.execution_id) if args.execution_id else None,
        sandbox_task_key=UUID(args.sandbox_task_key) if args.sandbox_task_key else None,
        benchmark_type=args.benchmark_type,
    )
    output = execute_workflow_command(command, context=context)
    if output.stdout:
        print(output.stdout)
    if output.stderr:
        print(output.stderr)
    return output.exit_code


def _handle_inspect(
    args: argparse.Namespace,
    *,
    context: WorkflowCommandContext,
    session: Session,
    service: WorkflowService,
) -> WorkflowCommandOutput:
    if args.action == "resource-list":
        resources = service.list_resources(
            session,
            run_id=context.run_id,
            node_id=context.node_id,
            scope=args.scope,
            kind=args.kind,
            max_depth=args.max_depth,
            limit=args.limit,
        )
        return _format_output(
            {"resources": [_dump(resource) for resource in resources]},
            text_lines=[
                f"{resource.resource_id} {resource.kind} {resource.name} "
                f"task={resource.task_slug or '-'} bytes={resource.size_bytes}"
                for resource in resources
            ],
            output_format=args.format,
        )
    if args.action == "resource-content":
        content = service.read_resource_bytes(
            session,
            run_id=context.run_id,
            resource_id=UUID(args.resource_id),
            max_bytes=args.max_bytes,
        )
        if args.format == "json":
            return _format_output({"content": content.decode(errors="replace")}, [], "json")
        return WorkflowCommandOutput(stdout=content.decode(errors="replace"))
    if args.action == "task-tree":
        parent = UUID(args.parent_node_id) if args.parent_node_id else None
        tasks = service.list_tasks(session, run_id=context.run_id, parent_node_id=parent)
        return _format_output(
            {"tasks": [_dump(task) for task in tasks]},
            text_lines=[
                f"{'  ' * task.level}{task.task_slug} {task.status} {task.node_id}"
                for task in tasks
            ],
            output_format=args.format,
        )
    if args.action == "task-dependencies":
        node_id = _node_id(context)
        deps = service.list_dependencies(
            session,
            run_id=context.run_id,
            node_id=node_id,
            direction=args.direction,
        )
        return _format_output(
            {"dependencies": [_dump(dep) for dep in deps]},
            text_lines=[
                f"{dep.source.task_slug} -> {dep.target.task_slug} status={dep.edge_status}"
                for dep in deps
            ],
            output_format=args.format,
        )
    if args.action == "next-actions":
        node_id = _node_id(context)
        actions = service.get_next_actions(
            session,
            run_id=context.run_id,
            node_id=node_id,
            manager_capable=args.manager_capable,
        )
        return _format_output(
            {"next_actions": [_dump(action) for action in actions]},
            text_lines=[action.summary for action in actions],
            output_format=args.format,
        )
    raise ValueError(f"unsupported inspect action: {args.action}")


async def _handle_manage(
    args: argparse.Namespace,
    *,
    context: WorkflowCommandContext,
    session: Session,
    service: WorkflowService,
) -> WorkflowCommandOutput:
    if args.action == "materialize-resource":
        node_id = _node_id(context)
        if context.execution_id is None or context.sandbox_task_key is None:
            raise ValueError(
                "execution_id and sandbox_task_key are required to materialize resources"
            )
        result = await service.materialize_resource(
            session,
            run_id=context.run_id,
            current_node_id=node_id,
            current_execution_id=context.execution_id,
            sandbox_task_key=context.sandbox_task_key,
            benchmark_type=context.benchmark_type,
            resource_id=UUID(args.resource_id),
            destination=args.destination,
            dry_run=args.dry_run,
        )
        return _format_output(
            {"materialized_resource": _dump(result)},
            text_lines=[f"{result.source_resource_id} -> {result.sandbox_path}"],
            output_format=args.format,
        )
    try:
        dry_run = args.dry_run
    except AttributeError:
        dry_run = False
    if dry_run:
        payload: JsonObject = {
            "action": args.action,
            "dry_run": True,
            "message": "Graph lifecycle command validated; no changes applied.",
        }
        return _format_output(payload, [str(payload["message"])], args.format)
    raise ValueError(f"{args.action} requires --dry-run in workflow CLI v1")


def _format_output(
    payload: JsonObject,
    text_lines: list[str],
    output_format: str,
) -> WorkflowCommandOutput:
    if output_format == "json":
        return WorkflowCommandOutput(stdout=json.dumps(payload, indent=2, sort_keys=True))
    return WorkflowCommandOutput(stdout="\n".join(text_lines))


def _dump(value: BaseModel | JsonObject) -> JsonObject:
    if isinstance(value, BaseModel):
        return cast(JsonObject, value.model_dump(mode="json"))
    if isinstance(value, dict):
        return value
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _node_id(context: WorkflowCommandContext) -> UUID:
    if context.node_id is None:
        raise ValueError("node_id is required for this workflow command")
    return context.node_id


def _close_session(session: Session) -> None:
    session.close()


def _reject_context_flags(argv: list[str]) -> None:
    if any(arg in _FORBIDDEN_CONTEXT_FLAGS for arg in argv):
        raise ValueError("scope/context flags are injected by the worker and cannot be supplied")
